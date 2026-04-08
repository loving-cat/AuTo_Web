# -*- coding: utf-8 -*-
"""
Prompt 管理模块 - 管理模拟用户测试的人设配置
支持：
1. 内部预设人设（默认）
2. 外部 prompt.py 文件（用户自定义）
3. 动态生成 prompt
"""
import os
import json
from typing import Dict, List, Optional, TypedDict
from dataclasses import dataclass, asdict
from datetime import datetime


# ============== 数据结构 ==============

@dataclass
class PersonaConfig:
    """人设配置"""
    id: str                    # 唯一标识
    name: str                  # 人设名称（显示用）
    description: str           # 人设描述
    persona: str               # 详细人设文本
    scenario: str              # 场景类型
    goal: str                  # 用户目标
    triggers: List[str]        # 触发语列表
    difficulty: str = "medium" # 难度：easy/medium/hard
    tags: List[str] | None = None     # 标签
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class PromptManager:
    """Prompt 管理器"""
    
    # 内部预设人设（默认）
    BUILTIN_PERSONAS = {
        "price_haggler": PersonaConfig(
            id="price_haggler",
            name="砍价达人",
            description="精打细算的买家，对价格非常敏感，喜欢砍价",
            persona="你是一个精打细算的买家，对价格非常敏感。你习惯货比三家，总想争取最低价格。你会用各种理由要求优惠，比如'别家更便宜'、'老客户了'、'量大能不能优惠'等。但你也通情达理，如果对方态度好，你也会适当妥协。",
            scenario="价格异议",
            goal="争取到最低价格或获得额外优惠",
            triggers=["太贵了", "能不能便宜点", "隔壁才卖XXX", "再优惠点我就买了", "老客户了给个折扣"],
            difficulty="medium",
            tags=["价格敏感", "砍价", "优惠"]
        ),
        "product_comparer": PersonaConfig(
            id="product_comparer",
            name="对比纠结型",
            description="正在对比多款产品的买家，犹豫不决",
            persona="你是一个正在对比多款产品的买家。你对A款有兴趣但嫌贵，对B款好奇但不确定。你会详细询问产品差异、优缺点，需要客服帮你分析。你的决策比较慢，需要更多信息才能下定决心。",
            scenario="多品对比",
            goal="对比两款产品的优劣，找到性价比最高的选择",
            triggers=["A款和B款哪个好", "A太贵了，B怎么样", "B有其他颜色吗", "两款有什么区别"],
            difficulty="medium",
            tags=["对比", "犹豫", "分析"]
        ),
        "angry_customer": PersonaConfig(
            id="angry_customer",
            name="投诉客户",
            description="遇到问题的客户，情绪激动，需要安抚",
            persona="你是一个遇到问题的客户，情绪有些激动。你购买的产品有问题（可以是质量问题、发货延迟、描述不符等），你很不满意。你需要对方给出合理的解决方案和补偿。如果对方态度好、解决及时，你的情绪会逐渐平复。",
            scenario="售后纠纷",
            goal="获得满意的售后解决方案",
            triggers=["我要投诉", "这质量太差了", "给我转人工", "我要退款", "这跟描述不一样"],
            difficulty="hard",
            tags=["投诉", "售后", "情绪化"]
        ),
        "hesitant_buyer": PersonaConfig(
            id="hesitant_buyer",
            name="犹豫不决型",
            description="犹豫不决的买家，需要被说服",
            persona="你是一个犹豫不决的买家。你对产品有兴趣，但有很多顾虑：价格是否合理？质量好不好？售后怎么样？你需要客服给你足够的信心和理由。你会提出各种担忧，希望得到专业的解答。",
            scenario="犹豫不决",
            goal="获得足够的信心和理由做出购买决定",
            triggers=["我再想想", "还是有点担心", "让我考虑一下", "万一不好用怎么办"],
            difficulty="easy",
            tags=["犹豫", "顾虑", "需要说服"]
        ),
        "competitor_aware": PersonaConfig(
            id="competitor_aware",
            name="竞品对比型",
            description="了解竞品的买家，需要看到优势",
            persona="你是一个对竞品有一定了解的买家。你知道XX品牌也有类似产品，而且价格更便宜。你想知道这个产品相比竞品有什么优势。你不会轻易被说服，需要看到实实在在的差异化价值。",
            scenario="竞品对比",
            goal="了解本产品相比竞品的优势",
            triggers=["为什么不买XX品牌", "XX品牌也有这个功能", "XX品牌更便宜", "你们有什么不同"],
            difficulty="hard",
            tags=["竞品", "对比", "挑剔"]
        ),
        "newbie": PersonaConfig(
            id="newbie",
            name="小白用户",
            description="对产品不了解的新手，需要详细解释",
            persona="你是一个对这类产品完全不了解的新手。你有很多基础问题，需要对方用简单易懂的语言解释。你可能会问一些'傻问题'，但你是真心想了解产品。",
            scenario="咨询",
            goal="了解产品的基本功能和使用方法",
            triggers=["这个怎么用", "我不太懂", "能详细说说吗", "适合新手吗"],
            difficulty="easy",
            tags=["新手", "咨询", "基础问题"]
        ),
        "loyal_customer": PersonaConfig(
            id="loyal_customer",
            name="老客户",
            description="熟悉产品的老客户，关注优惠和新品",
            persona="你是这个品牌的老客户，对产品比较满意。这次来主要是看看有没有新品或优惠活动。你对客服比较友好，但如果优惠力度不够，你也会表达失望。",
            scenario="复购",
            goal="了解新品和优惠活动，争取老客户专属优惠",
            triggers=["我是老客户", "上次买的不错", "有新品吗", "老客户有优惠吗"],
            difficulty="easy",
            tags=["老客户", "复购", "优惠"]
        )
    }
    
    def __init__(self, external_prompt_path: str | None = None):
        """
        初始化 Prompt 管理器
        
        Args:
            external_prompt_path: 外部 prompt.py 文件路径
        """
        # 如果未提供路径，使用默认路径
        if external_prompt_path is None:
            external_prompt_path = os.path.join(os.path.dirname(__file__), "prompt.py")
        self.external_prompt_path: str = external_prompt_path
        self.external_personas: Dict[str, PersonaConfig] = {}
        self._load_external_prompts()
    
    def _load_external_prompts(self):
        """加载外部 prompt.py 文件"""
        if os.path.exists(self.external_prompt_path):
            try:
                # 读取并执行 prompt.py
                with open(self.external_prompt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # 创建命名空间执行
                namespace = {}
                exec(content, namespace)
                
                # 提取 PERSONAS 变量
                if "PERSONAS" in namespace:
                    for p in namespace["PERSONAS"]:
                        if isinstance(p, dict):
                            persona = PersonaConfig(**p)
                        elif isinstance(p, PersonaConfig):
                            persona = p
                        else:
                            continue
                        self.external_personas[persona.id] = persona
                    
                    print(f"[PromptManager] 已加载 {len(self.external_personas)} 个外部人设")
            except Exception as e:
                print(f"[PromptManager] 加载外部 prompt.py 失败: {e}")
    
    def get_all_personas(self) -> Dict[str, PersonaConfig]:
        """获取所有人设（内部 + 外部）"""
        all_personas = dict(self.BUILTIN_PERSONAS)
        all_personas.update(self.external_personas)  # 外部覆盖内部
        return all_personas
    
    def get_persona(self, persona_id: str) -> Optional[PersonaConfig]:
        """获取指定人设"""
        # 优先外部
        if persona_id in self.external_personas:
            return self.external_personas[persona_id]
        return self.BUILTIN_PERSONAS.get(persona_id)
    
    def list_personas(self, include_external: bool = True) -> List[Dict]:
        """
        列出所有人设（供前端选择）
        
        Returns:
            人设列表，每个包含完整配置
        """
        result = []
        
        # 内部人设
        for p in self.BUILTIN_PERSONAS.values():
            result.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "persona": p.persona,
                "scenario": p.scenario,
                "goal": p.goal,
                "triggers": p.triggers,
                "difficulty": p.difficulty,
                "tags": p.tags,
                "is_builtin": True,
                "is_external": False
            })
        
        # 外部人设
        if include_external:
            for p in self.external_personas.values():
                result.append({
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "persona": p.persona,
                    "scenario": p.scenario,
                    "goal": p.goal,
                    "triggers": p.triggers,
                    "difficulty": p.difficulty,
                    "tags": p.tags,
                    "is_builtin": False,
                    "is_external": True
                })
        
        return result
    
    def has_external_prompts(self) -> bool:
        """检查是否有外部 prompt.py"""
        return len(self.external_personas) > 0
    
    def generate_prompt_file(
        self, 
        persona_id: str,
        name: str,
        description: str,
        persona_text: str,
        scenario: str,
        goal: str,
        triggers: List[str],
        difficulty: str = "medium",
        tags: List[str] | None = None
    ) -> str:
        """
        生成并保存 prompt.py 文件
        
        Args:
            persona_id: 人设ID
            name: 人设名称
            description: 人设描述
            persona_text: 详细人设文本
            scenario: 场景类型
            goal: 用户目标
            triggers: 触发语列表
            difficulty: 难度
            tags: 标签
            
        Returns:
            保存的文件路径
        """
        if tags is None:
            tags = []
        
        # 创建人设配置
        new_persona = PersonaConfig(
            id=persona_id,
            name=name,
            description=description,
            persona=persona_text,
            scenario=scenario,
            goal=goal,
            triggers=triggers,
            difficulty=difficulty,
            tags=tags
        )
        
        # 加载现有的外部人设
        existing_personas = list(self.external_personas.values())
        
        # 检查是否已存在，存在则更新
        updated = False
        for i, p in enumerate(existing_personas):
            if p.id == persona_id:
                existing_personas[i] = new_persona
                updated = True
                break
        
        if not updated:
            existing_personas.append(new_persona)
        
        # 生成 prompt.py 内容
        content = self._generate_prompt_py_content(existing_personas)
        
        # 保存文件
        with open(self.external_prompt_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        # 重新加载
        self._load_external_prompts()
        
        return self.external_prompt_path
    
    def _generate_prompt_py_content(self, personas: List[PersonaConfig]) -> str:
        """生成 prompt.py 文件内容"""
        lines = [
            '# -*- coding: utf-8 -*-',
            '"""',
            '自定义人设配置文件',
            f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '"""',
            '',
            'PERSONAS = ['
        ]
        
        for p in personas:
            p_dict = asdict(p)
            lines.append(f'    {{')
            lines.append(f'        "id": "{p_dict["id"]}",')
            lines.append(f'        "name": "{p_dict["name"]}",')
            lines.append(f'        "description": "{p_dict["description"]}",')
            # 多行文本处理
            persona_lines = p_dict["persona"].replace('\n', '\\n')
            lines.append(f'        "persona": "{persona_lines}",')
            lines.append(f'        "scenario": "{p_dict["scenario"]}",')
            goal_lines = p_dict["goal"].replace('\n', '\\n')
            lines.append(f'        "goal": "{goal_lines}",')
            lines.append(f'        "triggers": {json.dumps(p_dict["triggers"], ensure_ascii=False)},')
            lines.append(f'        "difficulty": "{p_dict["difficulty"]}",')
            lines.append(f'        "tags": {json.dumps(p_dict["tags"], ensure_ascii=False)}')
            lines.append(f'    }},')
        
        lines.append(']')
        lines.append('')
        
        return '\n'.join(lines)
    
    def generate_persona_from_input(
        self,
        direction: str,
        persona_description: str,
        additional_requirements: str = ""
    ) -> PersonaConfig:
        """
        根据用户输入动态生成人设配置
        
        Args:
            direction: 测试方向（如"价格异议"、"售后投诉"等）
            persona_description: 人设描述（如"一个挑剔的中年女性客户"）
            additional_requirements: 额外要求
            
        Returns:
            生成的 PersonaConfig
        """
        # 根据方向映射场景
        scenario_map = {
            "价格": "价格异议",
            "砍价": "价格异议",
            "优惠": "价格异议",
            "对比": "多品对比",
            "比较": "多品对比",
            "售后": "售后纠纷",
            "投诉": "售后纠纷",
            "退款": "售后纠纷",
            "犹豫": "犹豫不决",
            "纠结": "犹豫不决",
            "竞品": "竞品对比",
            "咨询": "咨询",
            "复购": "复购"
        }
        
        scenario = "咨询"  # 默认
        for key, value in scenario_map.items():
            if key in direction:
                scenario = value
                break
        
        # 生成人设ID
        import hashlib
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        persona_id = f"custom_{timestamp}"
        
        # 构建人设文本
        persona_text = f"{persona_description}。{additional_requirements}" if additional_requirements else persona_description
        
        # 生成默认触发语
        default_triggers = {
            "价格异议": ["太贵了", "能不能便宜点", "再优惠点"],
            "多品对比": ["A款和B款哪个好", "两款有什么区别"],
            "售后纠纷": ["我要投诉", "这质量太差了", "我要退款"],
            "犹豫不决": ["我再想想", "还是有点担心"],
            "竞品对比": ["为什么不买XX品牌", "XX品牌更便宜"],
            "咨询": ["这个怎么用", "能详细说说吗"],
            "复购": ["我是老客户", "有优惠吗"]
        }
        
        triggers = default_triggers.get(scenario, ["你好，我想了解一下"])
        
        return PersonaConfig(
            id=persona_id,
            name=f"自定义-{direction}",
            description=persona_description,
            persona=persona_text,
            scenario=scenario,
            goal=f"测试{direction}场景下的客服应对能力",
            triggers=triggers,
            difficulty="medium",
            tags=[direction, "自定义"]
        )


# ============== 全局实例 ==============
# 修复：使用线程本地存储实现会话隔离
import threading
_thread_local_pm = threading.local()
_prompt_managers = {}
_lock = threading.Lock()

def get_prompt_manager(session_id: str = "") -> PromptManager:
    """
    获取 PromptManager 实例 - 已修复会话隔离
    
    Args:
        session_id: 会话ID，用于隔离不同会话的PromptManager
    """
    # 优先从线程本地存储获取
    if hasattr(_thread_local_pm, 'manager') and _thread_local_pm.manager is not None:
        return _thread_local_pm.manager
    
    # 根据session_id从全局字典获取
    with _lock:
        if session_id not in _prompt_managers:
            _prompt_managers[session_id] = PromptManager()
        manager = _prompt_managers[session_id]
        # 同时设置到线程本地存储
        _thread_local_pm.manager = manager
        return manager

def clear_prompt_manager(session_id: str = ""):
    """清理指定会话的PromptManager - 用于会话结束清理"""
    with _lock:
        if session_id in _prompt_managers:
            del _prompt_managers[session_id]
    if hasattr(_thread_local_pm, 'manager'):
        _thread_local_pm.manager = None


def list_available_personas() -> List[Dict]:
    """列出所有可用的人设（供前端调用）"""
    return get_prompt_manager().list_personas()


def get_persona_by_id(persona_id: str) -> Optional[PersonaConfig]:
    """根据ID获取人设"""
    return get_prompt_manager().get_persona(persona_id)


def create_custom_persona(
    direction: str,
    persona_description: str,
    additional_requirements: str = "",
    save_to_file: bool = True
) -> PersonaConfig:
    """
    创建自定义人设
    
    Args:
        direction: 测试方向
        persona_description: 人设描述
        additional_requirements: 额外要求
        save_to_file: 是否保存到 prompt.py
        
    Returns:
        创建的 PersonaConfig
    """
    manager = get_prompt_manager()
    persona = manager.generate_persona_from_input(
        direction, 
        persona_description, 
        additional_requirements
    )
    
    if save_to_file:
        manager.generate_prompt_file(
            persona_id=persona.id,
            name=persona.name,
            description=persona.description,
            persona_text=persona.persona,
            scenario=persona.scenario,
            goal=persona.goal,
            triggers=persona.triggers,
            difficulty=persona.difficulty,
            tags=persona.tags
        )
    
    return persona


if __name__ == "__main__":
    # 测试
    manager = get_prompt_manager()
    
    print("=== 可用人设列表 ===")
    for p in manager.list_personas():
        source = "[外部]" if p["is_external"] else "[内置]"
        print(f"{source} {p['id']}: {p['name']} - {p['description']}")
    
    print("\n=== 创建自定义人设 ===")
    custom = create_custom_persona(
        direction="价格异议",
        persona_description="一个精明的中年女性，对价格非常敏感",
        additional_requirements="喜欢用'别家更便宜'来压价",
        save_to_file=False
    )
    print(f"创建的人设: {custom.name}")
    print(f"场景: {custom.scenario}")
    print(f"触发语: {custom.triggers}")
