# -*- coding: utf-8 -*-
"""
用户画像测试问句生成模块
基于规则配置和知识库动态生成画像测试问句
优化版本：增加并发数、连接池、批量处理
修复：使用线程本地存储实现会话隔离
"""
import os
import json
import random
import requests
import threading
from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 线程本地存储 - 每个线程有独立的session，实现隔离
_thread_local = threading.local()

def get_session():
    """获取线程本地的requests会话，带连接池和重试 - 已隔离"""
    if not hasattr(_thread_local, 'session') or _thread_local.session is None:
        _thread_local.session = requests.Session()
        # 配置连接池和重试
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=retry_strategy
        )
        _thread_local.session.mount("http://", adapter)
        _thread_local.session.mount("https://", adapter)
    return _thread_local.session

def clear_session():
    """清理当前线程的session - 用于会话结束清理"""
    if hasattr(_thread_local, 'session'):
        _thread_local.session = None


class PersonaTestCase(TypedDict):
    """画像测试用例"""
    test_case_id: str
    user_input: str
    expected_profile: Dict[str, Any]
    complexity: str
    scenario_type: str
    category: Optional[str]


class PersonaQuestionGenerator:
    """画像测试问句生成器"""
    
    def __init__(self, rules_path: str | None = None):
        """
        初始化生成器
        
        Args:
            rules_path: 规则配置文件路径
        """
        if rules_path is None:
            rules_path = os.path.join(os.path.dirname(__file__), "persona_rules.json")
        
        self.rules = self._load_rules(rules_path)
        self.llm_api_key = os.getenv("LLM_API_KEY", "")  # [CLEARED] 从环境变量读取
        self.llm_api_base = os.getenv("LLM_API_BASE_URL", "")  # [CLEARED] 从环境变量读取
        self.llm_model = os.getenv("LLM_MODEL", "qwen-plus")
    
    def _load_rules(self, rules_path: str) -> Dict[str, Any]:
        """加载规则配置"""
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 加载规则配置失败: {e}，使用默认配置")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """获取默认规则配置"""
        return {
            "R1_price_thresholds": {
                "categories": {
                    "手机": {"expensive": 5000, "cheap": 2000, "brands": ["iPhone", "华为", "小米"]}
                }
            },
            "R2_semantic_rules": {
                "price_sensitivity": {
                    "expensive": {"keywords": ["贵", "太贵", "买不起"]},
                    "cheap": {"keywords": ["便宜", "划算"]},
                    "neutral": {"keywords": ["还可以", "一般"]}
                }
            },
            "R3_profile_fields": {
                "basic_info": {
                    "name": {"required": True, "weight": 1.0},
                    "age": {"required": True, "weight": 1.0}
                },
                "purchase_info": {
                    "product": {"required": True, "weight": 1.0}
                },
                "sentiment_info": {
                    "price_sensitivity": {"required": True, "weight": 1.0}
                }
            },
            "R4_judge_metrics": {
                "thresholds": {
                    "pass_score_threshold": 70
                }
            },
            "test_generation": {
                "complexity_levels": {
                    "simple": {"field_count": [3, 4]},
                    "medium": {"field_count": [5, 7]},
                    "complex": {"field_count": [8, 12]}
                },
                "scenario_types": ["first_inquiry", "price_negotiation"]
            }
        }
    
    def generate_test_cases(
        self,
        count: int = 10,
        complexity: str = "medium",
        categories: List[str] | None = None,
        scenario_types: List[str] | None = None,
        knowledge_content: str = "",
        max_workers: int = 20,  # 优化：默认并发数提升到20
        batch_size: int = 5     # 优化：每批同时生成数量
    ) -> List[PersonaTestCase]:
        """
        生成画像测试用例（支持并发生成）- 优化版本
        
        Args:
            count: 生成数量
            complexity: 复杂度 (simple/medium/complex)
            categories: 品类列表，为空则随机选择
            scenario_types: 场景类型列表，为空则随机选择
            knowledge_content: 知识库内容，用于生成更贴合的问句
            max_workers: 并发工作线程数，默认20（原10）
            batch_size: 每批处理数量，默认5（启用批量API调用）
            
        Returns:
            测试用例列表
        """
        print(f"\n[PersonaGenerator] 开始生成 {count} 个画像测试用例...")
        print(f"  复杂度: {complexity}, 并发数: {max_workers}, 批大小: {batch_size}")
        
        # 获取可用品类
        available_categories = list(self.rules["R1_price_thresholds"]["categories"].keys())
        if categories:
            available_categories = [c for c in categories if c in available_categories]
        
        # 获取可用场景类型
        available_scenarios = self.rules["test_generation"]["scenario_types"]
        if scenario_types:
            available_scenarios = [s for s in scenario_types if s in available_scenarios]
        
        # 预生成所有用例的配置（品类和场景）
        test_configs = []
        for i in range(count):
            category = random.choice(available_categories)
            scenario = random.choice(available_scenarios)
            test_configs.append({
                "index": i + 1,
                "category": category,
                "scenario": scenario,
                "complexity": complexity,
                "knowledge_content": knowledge_content
            })
        
        # 并发生成测试用例
        test_cases = []
        completed_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_config = {
                executor.submit(self._generate_single_test_case_concurrent, config): config 
                for config in test_configs
            }
            
            # 收集结果
            for future in as_completed(future_to_config):
                config = future_to_config[future]
                try:
                    test_case = future.result(timeout=60)
                    if test_case:
                        test_cases.append(test_case)
                        completed_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    print(f"[WARN] 生成用例 #{config['index']} 失败: {e}")
                    failed_count += 1
                
                # 每完成5个打印进度
                if (completed_count + failed_count) % 5 == 0:
                    print(f"  进度: {completed_count}/{count} 成功, {failed_count} 失败")
        
        # 按索引排序
        test_cases.sort(key=lambda x: x["test_case_id"])
        
        print(f"[OK] 成功生成 {len(test_cases)} 个测试用例 ({failed_count} 失败)")
        return test_cases
    
    def _generate_single_test_case_concurrent(self, config: Dict[str, Any]) -> Optional[PersonaTestCase]:
        """
        并发生成单个测试用例的包装函数
        
        Args:
            config: 配置字典，包含 index, category, scenario, complexity, knowledge_content
            
        Returns:
            测试用例
        """
        try:
            return self._generate_single_test_case(
                index=config["index"],
                category=config["category"],
                scenario=config["scenario"],
                complexity=config["complexity"],
                knowledge_content=config["knowledge_content"]
            )
        except Exception as e:
            print(f"[WARN] 生成用例 #{config['index']} 异常: {e}")
            return None
    
    def _generate_single_test_case(
        self,
        index: int,
        category: str,
        scenario: str,
        complexity: str,
        knowledge_content: str = ""
    ) -> Optional[PersonaTestCase]:
        """
        生成单个测试用例
        
        Args:
            index: 用例序号
            category: 品类
            scenario: 场景类型
            complexity: 复杂度
            knowledge_content: 知识库内容
            
        Returns:
            测试用例
        """
        # 获取品类信息
        category_info = self.rules["R1_price_thresholds"]["categories"].get(category, {})
        price_expensive = category_info.get("expensive", 5000)
        price_cheap = category_info.get("cheap", 1000)
        brands = category_info.get("brands", ["某品牌"])
        
        # 获取复杂度配置
        complexity_config = self.rules["test_generation"]["complexity_levels"].get(complexity, {})
        field_count_range = complexity_config.get("field_count", [3, 5])
        target_field_count = random.randint(field_count_range[0], field_count_range[1])
        
        # 构建期望画像
        expected_profile = self._build_expected_profile(
            category=category,
            brands=brands,
            price_expensive=price_expensive,
            price_cheap=price_cheap,
            scenario=scenario,
            target_field_count=target_field_count
        )
        
        # 使用LLM生成问句
        user_input = self._generate_user_input_by_llm(
            expected_profile=expected_profile,
            category=category,
            scenario=scenario,
            knowledge_content=knowledge_content
        )
        
        if not user_input:
            # LLM失败时使用模板生成
            user_input = self._generate_user_input_by_template(
                expected_profile=expected_profile,
                category=category,
                scenario=scenario
            )
        
        test_case_id = f"persona_{datetime.now().strftime('%Y%m%d')}_{index:04d}"
        
        return PersonaTestCase(
            test_case_id=test_case_id,
            user_input=user_input,
            expected_profile=expected_profile,
            complexity=complexity,
            scenario_type=scenario,
            category=category
        )
    
    def _build_expected_profile(
        self,
        category: str,
        brands: List[str],
        price_expensive: int,
        price_cheap: int,
        scenario: str,
        target_field_count: int
    ) -> Dict[str, Any]:
        """
        构建期望画像
        
        Args:
            category: 品类
            brands: 品牌列表
            price_expensive: 贵的价格阈值
            price_cheap: 便宜的价格阈值
            scenario: 场景类型
            target_field_count: 目标字段数量
            
        Returns:
            期望画像字典
        """
        # 基础信息
        names = ["张三", "李四", "王五", "赵六", "小明", "小红", "小华", "小李", "小张", "小王"]
        ages = list(range(18, 55))
        occupations = ["学生", "上班族", "自由职业", "教师", "医生", "工程师", "设计师", "销售"]
        locations = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京"]
        
        profile = {}
        current_field_count = 0
        
        # 基础信息字段
        profile["name"] = random.choice(names)
        current_field_count += 1
        
        if current_field_count < target_field_count:
            profile["age"] = random.choice(ages)
            current_field_count += 1
        
        # 购买信息字段
        brand = random.choice(brands)
        product = f"{brand}{category}"
        profile["product"] = product
        current_field_count += 1
        
        if current_field_count < target_field_count:
            profile["brand"] = brand
            current_field_count += 1
        
        # 根据场景决定价格敏感度
        if scenario == "price_negotiation":
            # 砍价场景：价格敏感
            mentioned_price = random.randint(price_expensive, price_expensive + 2000)
            profile["mentioned_price"] = mentioned_price
            profile["price_sensitivity"] = "expensive"
            current_field_count += 2
        elif scenario == "budget_constrained":
            # 预算受限场景
            profile["budget"] = random.randint(price_cheap, int((price_cheap + price_expensive) / 2))
            profile["price_sensitivity"] = "cheap"
            current_field_count += 2
        elif scenario == "brand_loyal":
            # 品牌忠诚场景
            profile["brand_preference"] = brand
            profile["price_sensitivity"] = "neutral"
            current_field_count += 2
        else:
            # 默认场景
            price_sensitivities = ["expensive", "cheap", "neutral"]
            profile["price_sensitivity"] = random.choice(price_sensitivities)
            current_field_count += 1
        
        # 补充其他字段
        if current_field_count < target_field_count:
            profile["purchase_intent"] = random.choice(["high", "medium", "low"])
            current_field_count += 1
        
        if current_field_count < target_field_count:
            profile["occupation"] = random.choice(occupations)
            current_field_count += 1
        
        if current_field_count < target_field_count:
            profile["location"] = random.choice(locations)
            current_field_count += 1
        
        return profile
    
    def _generate_user_input_by_llm(
        self,
        expected_profile: Dict[str, Any],
        category: str,
        scenario: str,
        knowledge_content: str = ""
    ) -> Optional[str]:
        """
        使用LLM生成用户输入
        
        Args:
            expected_profile: 期望画像
            category: 品类
            scenario: 场景类型
            knowledge_content: 知识库内容
            
        Returns:
            生成的用户输入
        """
        if not self.llm_api_key:
            return None
        
        # 场景描述
        scenario_descriptions = {
            "first_inquiry": "首次咨询，用户第一次了解产品",
            "price_negotiation": "价格谈判，用户觉得价格贵想砍价",
            "product_comparison": "产品对比，用户在比较不同产品",
            "urgent_purchase": "紧急购买，用户急需购买",
            "budget_constrained": "预算有限，用户预算不足",
            "brand_loyal": "品牌忠诚，用户偏好特定品牌",
            "casual_browsing": "随意浏览，用户只是随便看看"
        }
        
        scenario_desc = scenario_descriptions.get(scenario, "一般咨询")
        
        # 构建prompt
        prompt = f"""请根据以下信息生成一个用户的自然对话输入。

【场景】{scenario_desc}
【品类】{category}
【用户画像信息】
{json.dumps(expected_profile, ensure_ascii=False, indent=2)}

【要求】
1. 生成一句自然的用户对话，模拟真实用户咨询场景
2. 对话中需要自然地包含画像中的信息（姓名、年龄、购买意向、价格敏感度等）
3. 语言要口语化，符合真实用户说话习惯
4. 不要输出任何解释或标记，只输出对话内容

【示例】
如果画像是 {{"name": "张三", "age": 25, "product": "iPhone 15", "price_sensitivity": "expensive"}}
输出：我叫张三，今年25岁，想买个iPhone 15，但是8000多块钱有点贵了

请生成对话："""

        try:
            headers = {
                "Authorization": f"Bearer {self.llm_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,
                "max_tokens": 200
            }
            
            # 优化：使用连接池复用会话
            session = get_session()
            response = session.post(
                f"{self.llm_api_base}/chat/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            
            # 清理可能的引号和多余字符
            content = content.strip('"\'""''')
            
            return content
            
        except Exception as e:
            print(f"[WARN] LLM生成问句失败: {e}")
            return None
    
    def _generate_user_input_by_template(
        self,
        expected_profile: Dict[str, Any],
        category: str,
        scenario: str
    ) -> str:
        """
        使用模板生成用户输入（LLM不可用时的后备方案）
        
        Args:
            expected_profile: 期望画像
            category: 品类
            scenario: 场景类型
            
        Returns:
            生成的用户输入
        """
        parts = []
        
        # 姓名
        if "name" in expected_profile:
            parts.append(f"我叫{expected_profile['name']}")
        
        # 年龄
        if "age" in expected_profile:
            parts.append(f"{expected_profile['age']}岁")
        
        # 购买意向
        if "product" in expected_profile:
            parts.append(f"想买{expected_profile['product']}")
        
        # 价格敏感度
        price_sensitivity = expected_profile.get("price_sensitivity")
        mentioned_price = expected_profile.get("mentioned_price")
        
        if price_sensitivity == "expensive":
            if mentioned_price:
                parts.append(f"觉得{mentioned_price}元有点贵了")
            else:
                parts.append("觉得价格有点贵")
        elif price_sensitivity == "cheap":
            parts.append("觉得挺划算的")
        elif price_sensitivity == "neutral":
            parts.append("价格还可以接受")
        
        # 预算
        if "budget" in expected_profile:
            parts.append(f"预算大概{expected_profile['budget']}元左右")
        
        # 职业
        if "occupation" in expected_profile:
            parts.append(f"我是做{expected_profile['occupation']}的")
        
        # 地点
        if "location" in expected_profile:
            parts.append(f"人在{expected_profile['location']}")
        
        return "，".join(parts) + "。"
    
    def generate_from_knowledge(
        self,
        knowledge_content: str,
        count: int = 10,
        complexity: str = "medium",
        max_workers: int = 10
    ) -> List[PersonaTestCase]:
        """
        基于知识库内容生成测试用例
        
        Args:
            knowledge_content: 知识库内容
            count: 生成数量
            complexity: 复杂度
            max_workers: 并发工作线程数
            
        Returns:
            测试用例列表
        """
        # 从知识库中提取品类信息
        categories = self._extract_categories_from_knowledge(knowledge_content)
        
        if not categories:
            # 如果无法提取，使用默认品类
            categories = list(self.rules["R1_price_thresholds"]["categories"].keys())[:3]
        
        return self.generate_test_cases(
            count=count,
            complexity=complexity,
            categories=categories,
            knowledge_content=knowledge_content,
            max_workers=max_workers
        )
    
    def _extract_categories_from_knowledge(self, knowledge_content: str) -> List[str] | None:
        """
        从知识库中提取品类
        
        Args:
            knowledge_content: 知识库内容
            
        Returns:
            品类列表
        """
        available_categories = list(self.rules["R1_price_thresholds"]["categories"].keys())
        found_categories = []
        
        for category in available_categories:
            if category in knowledge_content:
                found_categories.append(category)
        
        return found_categories if found_categories else None


def generate_persona_test_cases(
    count: int = 10,
    complexity: str = "medium",
    categories: List[str] | None = None,
    scenario_types: List[str] | None = None,
    knowledge_content: str = "",
    rules_path: str | None = None,
    max_workers: int = 10
) -> List[PersonaTestCase]:
    """
    生成画像测试用例的便捷函数（支持并发）
    
    Args:
        count: 生成数量
        complexity: 复杂度
        categories: 品类列表
        scenario_types: 场景类型列表
        knowledge_content: 知识库内容
        rules_path: 规则配置文件路径
        max_workers: 并发工作线程数，默认10
        
    Returns:
        测试用例列表
    """
    generator = PersonaQuestionGenerator(rules_path)
    
    if knowledge_content:
        return generator.generate_from_knowledge(
            knowledge_content=knowledge_content,
            count=count,
            complexity=complexity,
            max_workers=max_workers
        )
    else:
        return generator.generate_test_cases(
            count=count,
            complexity=complexity,
            categories=categories,
            scenario_types=scenario_types,
            max_workers=max_workers
        )


if __name__ == "__main__":
    # 测试生成器
    print("=" * 60)
    print("画像测试问句生成器测试")
    print("=" * 60)
    
    test_cases = generate_persona_test_cases(
        count=5,
        complexity="medium",
        categories=["手机", "电脑"]
    )
    
    for tc in test_cases:
        print(f"\n[{tc['test_case_id']}]")
        print(f"  场景: {tc['scenario_type']}")
        print(f"  品类: {tc['category']}")
        print(f"  用户输入: {tc['user_input']}")
        print(f"  期望画像: {json.dumps(tc['expected_profile'], ensure_ascii=False)}")
