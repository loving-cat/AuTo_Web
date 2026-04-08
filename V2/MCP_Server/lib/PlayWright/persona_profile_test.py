# -*- coding: utf-8 -*-
"""
用户画像构建测试主模块
包含完整的测试流程和指标计算逻辑

集成画像接口：
- 调用 /stream_response_procedure/test/user_profile 获取真实画像
- 对比 Bot 构建的画像与真实画像
- 计算画像构建准确率
"""
import os
import sys
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, TypedDict, Callable

# 处理导入
try:
    from .persona_question_generator import generate_persona_test_cases, PersonaTestCase
    from .persona_profile_judge import evaluate_persona_profile, load_rules
    from .user_profile_client import UserProfileClient, UserProfileConfig
except ImportError:
    _project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from MCP_Server.lib.PlayWright.persona_question_generator import generate_persona_test_cases, PersonaTestCase
    from MCP_Server.lib.PlayWright.persona_profile_judge import evaluate_persona_profile, load_rules
    from MCP_Server.lib.PlayWright.user_profile_client import UserProfileClient, UserProfileConfig  # type: ignore


class PersonaTestResult(TypedDict):
    """单个画像测试结果"""
    test_case_id: str
    user_input: str
    expected_profile: Dict[str, Any]
    actual_profile: Dict[str, Any]
    evaluation: Dict[str, Any]
    bot_response: str
    response_time: float
    timestamp: str
    # 接口模式相关字段
    api_source: str  # "local" 或 "api"
    user_id: str  # 卖家 ID（接口模式）
    tenant_outer_id: str  # 买家 ID（接口模式）


class PersonaTestReport(TypedDict):
    """画像测试报告"""
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_field_recall: float
    avg_field_precision: float
    avg_value_accuracy: float
    avg_overall_score: float
    grade_distribution: Dict[str, int]
    field_stats: Dict[str, Dict[str, Any]]
    results: List[PersonaTestResult]
    config: Dict[str, Any]
    timestamp: str
    # 接口模式统计
    api_mode: bool  # 是否使用接口模式
    api_success_count: int  # 接口调用成功数
    api_fail_count: int  # 接口调用失败数


class PersonaProfileTester:
    """用户画像构建测试器
    
    支持两种模式：
    1. 本地模式：使用测试用例中的 expected_profile
    2. 接口模式：调用 /stream_response_procedure/test/user_profile 获取真实画像
    """
    
    def __init__(
        self,
        rules_path: str | None = None,
        knowledge_content: str = "",
        user_profile_config: Optional[UserProfileConfig] = None
    ):
        """
        初始化测试器
        
        Args:
            rules_path: 规则配置文件路径
            knowledge_content: 知识库内容
            user_profile_config: 画像接口配置（可选，启用接口模式）
        """
        self.rules_path = rules_path
        self.rules = load_rules(rules_path)
        self.knowledge_content = knowledge_content
        self.results: List[PersonaTestResult] = []
        
        # 画像接口客户端
        self.user_profile_client: Optional[UserProfileClient] = None
        if user_profile_config:
            self.user_profile_client = UserProfileClient(user_profile_config)
        
        # 接口调用统计
        self.api_success_count = 0
        self.api_fail_count = 0
    
    def set_user_profile_client(self, config: UserProfileConfig) -> None:
        """设置画像接口客户端"""
        self.user_profile_client = UserProfileClient(config)
    
    def get_expected_profile_from_api(
        self,
        user_id: str,
        tenant_outer_id: str
    ) -> tuple[bool, Dict[str, Any], str]:
        """
        从画像接口获取期望画像
        
        Args:
            user_id: 卖家 ID
            tenant_outer_id: 买家 ID
        
        Returns:
            (success, expected_profile, error_message)
        """
        if not self.user_profile_client:
            return False, {}, "画像接口客户端未配置"
        
        profile_data = self.user_profile_client.get_user_profile(user_id, tenant_outer_id)
        
        if not profile_data.get("success"):
            self.api_fail_count += 1
            return False, {}, profile_data.get("error", "未知错误")
        
        self.api_success_count += 1
        expected = self.user_profile_client.extract_expected_profile(profile_data)
        return True, expected, ""
    
    def generate_test_cases(
        self,
        count: int = 10,
        complexity: str = "medium",
        categories: List[str] | None = None,
        scenario_types: List[str] | None = None
    ) -> List[PersonaTestCase]:
        """
        生成测试用例
        
        Args:
            count: 数量
            complexity: 复杂度
            categories: 品类列表
            scenario_types: 场景类型列表
            
        Returns:
            测试用例列表
        """
        return generate_persona_test_cases(
            count=count,
            complexity=complexity,
            categories=categories,
            scenario_types=scenario_types,
            knowledge_content=self.knowledge_content,
            rules_path=self.rules_path
        )
    
    def run_single_test(
        self,
        test_case: PersonaTestCase,
        bot_profile_extractor: Callable | None = None,
        bot_response: str = "",
        # 接口模式参数
        user_id: str = "",
        tenant_outer_id: str = "",
        use_api: bool = False
    ) -> PersonaTestResult:
        """
        运行单个测试
        
        Args:
            test_case: 测试用例
            bot_profile_extractor: Bot画像提取函数（可选）
            bot_response: Bot回复内容
            user_id: 卖家 ID（接口模式必需）
            tenant_outer_id: 买家 ID（接口模式必需）
            use_api: 是否使用接口获取期望画像
            
        Returns:
            测试结果
        """
        start_time = time.time()
        
        # 确定期望画像来源
        if use_api and user_id and tenant_outer_id:
            # 接口模式：从 API 获取真实画像
            success, expected_profile, error = self.get_expected_profile_from_api(
                user_id, tenant_outer_id
            )
            api_source = "api"
            if not success:
                print(f"[WARN] 接口获取画像失败: {error}，使用本地期望画像")
                expected_profile = test_case.get("expected_profile", {})
                api_source = "local_fallback"
        else:
            # 本地模式：使用测试用例中的期望画像
            expected_profile = test_case.get("expected_profile", {})
            api_source = "local"
        
        # 获取Bot构建的画像
        if bot_profile_extractor:
            actual_profile = bot_profile_extractor(test_case["user_input"], bot_response)
        else:
            # 如果没有提供提取函数，尝试从回复中解析
            actual_profile = self._extract_profile_from_response(bot_response)
        
        # 评估画像
        evaluation = evaluate_persona_profile(
            user_input=test_case["user_input"],
            expected_profile=expected_profile,
            actual_profile=actual_profile,
            rules=self.rules
        )
        
        end_time = time.time()
        
        return PersonaTestResult(
            test_case_id=test_case["test_case_id"],
            user_input=test_case["user_input"],
            expected_profile=expected_profile,
            actual_profile=actual_profile,
            evaluation={
                "field_recall": evaluation["field_recall"],
                "field_precision": evaluation["field_precision"],
                "value_accuracy": evaluation["value_accuracy"],
                "overall_score": evaluation["overall_score"],
                "is_pass": evaluation["is_pass"],
                "grade": evaluation["grade"],
                "reason": evaluation["reason"],
                "consensus_rate": evaluation["consensus_rate"],
                "field_stats": evaluation["field_stats"]
            },
            bot_response=bot_response,
            response_time=round(end_time - start_time, 2),
            timestamp=datetime.now().isoformat(),
            api_source=api_source,
            user_id=user_id,
            tenant_outer_id=tenant_outer_id
        )
    
    def run_tests(
        self,
        test_cases: List[PersonaTestCase],
        bot_profile_extractor: Callable | None = None,
        bot_responses: List[str] | None = None,
        progress_callback: Callable | None = None,
        # 接口模式参数
        user_ids: List[str] | None = None,
        tenant_outer_ids: List[str] | None = None,
        use_api: bool = False
    ) -> List[PersonaTestResult]:
        """
        批量运行测试
        
        Args:
            test_cases: 测试用例列表
            bot_profile_extractor: Bot画像提取函数
            bot_responses: Bot回复列表（与test_cases一一对应）
            progress_callback: 进度回调函数
            user_ids: 卖家 ID 列表（接口模式）
            tenant_outer_ids: 买家 ID 列表（接口模式）
            use_api: 是否使用接口获取期望画像
            
        Returns:
            测试结果列表
        """
        self.results = []
        self.api_success_count = 0
        self.api_fail_count = 0
        total = len(test_cases)
        
        mode_str = "接口模式" if use_api else "本地模式"
        print(f"\n[PersonaTest] 开始执行 {total} 个画像测试用例 ({mode_str})...")
        
        for i, test_case in enumerate(test_cases):
            bot_response = ""
            if bot_responses and i < len(bot_responses):
                bot_response = bot_responses[i]
            
            # 获取接口模式参数
            user_id = user_ids[i] if user_ids and i < len(user_ids) else ""
            tenant_outer_id = tenant_outer_ids[i] if tenant_outer_ids and i < len(tenant_outer_ids) else ""
            
            result = self.run_single_test(
                test_case=test_case,
                bot_profile_extractor=bot_profile_extractor,
                bot_response=bot_response,
                user_id=user_id,
                tenant_outer_id=tenant_outer_id,
                use_api=use_api
            )
            
            self.results.append(result)
            
            # 进度显示
            status = "✓" if result["evaluation"]["is_pass"] else "✗"
            api_status = f"[API:{result['api_source']}]" if use_api else ""
            print(f"  [{i+1}/{total}] {status} {test_case['test_case_id']} - 得分: {result['evaluation']['overall_score']} {api_status}")
            
            # 进度回调
            if progress_callback:
                progress_callback(i + 1, total, result)
        
        # 打印接口统计
        if use_api:
            print(f"\n[API统计] 成功: {self.api_success_count}, 失败: {self.api_fail_count}")
        
        return self.results
    
    def generate_report(self) -> PersonaTestReport:
        """
        生成测试报告
        
        Returns:
            测试报告
        """
        if not self.results:
            return PersonaTestReport(
                total=0,
                passed=0,
                failed=0,
                pass_rate=0.0,
                avg_field_recall=0.0,
                avg_field_precision=0.0,
                avg_value_accuracy=0.0,
                avg_overall_score=0.0,
                grade_distribution={},
                field_stats={},
                results=[],
                config={},
                timestamp=datetime.now().isoformat(),
                api_mode=False,
                api_success_count=0,
                api_fail_count=0
            )
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["evaluation"]["is_pass"])
        failed = total - passed
        
        # 计算平均指标
        avg_field_recall = sum(r["evaluation"]["field_recall"] for r in self.results) / total
        avg_field_precision = sum(r["evaluation"]["field_precision"] for r in self.results) / total
        avg_value_accuracy = sum(r["evaluation"]["value_accuracy"] for r in self.results) / total
        avg_overall_score = sum(r["evaluation"]["overall_score"] for r in self.results) / total
        
        # 等级分布
        grade_distribution = {"excellent": 0, "good": 0, "pass": 0, "fail": 0}
        for r in self.results:
            grade = r["evaluation"]["grade"]
            if grade in grade_distribution:
                grade_distribution[grade] += 1
        
        # 字段统计汇总
        field_stats = self._aggregate_field_stats()
        
        # 判断是否使用接口模式
        api_mode = any(r.get("api_source") == "api" for r in self.results)
        
        return PersonaTestReport(
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=round(passed / total * 100, 2) if total > 0 else 0,
            avg_field_recall=round(avg_field_recall, 4),
            avg_field_precision=round(avg_field_precision, 4),
            avg_value_accuracy=round(avg_value_accuracy, 4),
            avg_overall_score=round(avg_overall_score, 2),
            grade_distribution=grade_distribution,
            field_stats=field_stats,
            results=self.results,
            config={
                "rules_version": self.rules.get("version", "unknown"),
                "test_count": total,
                "api_mode": api_mode
            },
            timestamp=datetime.now().isoformat(),
            api_mode=api_mode,
            api_success_count=self.api_success_count,
            api_fail_count=self.api_fail_count
        )
    
    def _extract_profile_from_response(self, bot_response: str) -> Dict[str, Any]:
        """
        从Bot回复中提取画像（简单实现）
        
        Args:
            bot_response: Bot回复内容
            
        Returns:
            提取的画像字典
        """
        # 尝试从回复中解析JSON格式的画像
        try:
            # 查找JSON块
            json_start = bot_response.find("{")
            json_end = bot_response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = bot_response[json_start:json_end]
                return json.loads(json_str)
        except:
            pass
        
        # 如果无法解析，返回空字典
        return {}
    
    def _aggregate_field_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        汇总字段统计
        
        Returns:
            字段统计字典
        """
        all_field_stats: Dict[str, Dict[str, Any]] = {}
        
        for result in self.results:
            field_stats = result["evaluation"].get("field_stats", {})
            for field_name, stats in field_stats.items():
                if field_name not in all_field_stats:
                    all_field_stats[field_name] = {
                        "match_types": [],
                        "scores": [],
                        "count": 0
                    }
                
                all_field_stats[field_name]["match_types"].append(stats.get("match_type", "no_match"))
                all_field_stats[field_name]["scores"].append(stats.get("avg_score", 0))
                all_field_stats[field_name]["count"] += 1
        
        # 计算汇总指标
        for field_name, data in all_field_stats.items():
            from collections import Counter
            type_counter = Counter(data["match_types"])
            
            data["most_common_type"] = type_counter.most_common(1)[0][0] if type_counter else "no_match"
            data["avg_score"] = round(sum(data["scores"]) / len(data["scores"]), 2) if data["scores"] else 0
            data["accuracy_rate"] = round(
                sum(1 for t in data["match_types"] if t in ["exact", "partial", "semantic"]) / len(data["match_types"]),
                4
            ) if data["match_types"] else 0
            
            # 清理临时数据
            del data["match_types"]
            del data["scores"]
        
        return all_field_stats


def run_persona_profile_test(
    count: int = 10,
    complexity: str = "medium",
    categories: List[str] | None = None,
    scenario_types: List[str] | None = None,
    knowledge_content: str = "",
    bot_profile_extractor: Callable | None = None,
    bot_responses: List[str] | None = None,
    rules_path: str | None = None,
    # 接口模式参数
    user_profile_config: Optional[UserProfileConfig] = None,
    user_ids: List[str] | None = None,
    tenant_outer_ids: List[str] | None = None,
    use_api: bool = False
) -> PersonaTestReport:
    """
    运行画像测试的便捷函数
    
    Args:
        count: 测试用例数量
        complexity: 复杂度
        categories: 品类列表
        scenario_types: 场景类型列表
        knowledge_content: 知识库内容
        bot_profile_extractor: Bot画像提取函数
        bot_responses: Bot回复列表
        rules_path: 规则配置文件路径
        user_profile_config: 画像接口配置
        user_ids: 卖家 ID 列表（接口模式）
        tenant_outer_ids: 买家 ID 列表（接口模式）
        use_api: 是否使用接口获取期望画像
        
    Returns:
        测试报告
    """
    tester = PersonaProfileTester(
        rules_path=rules_path,
        knowledge_content=knowledge_content,
        user_profile_config=user_profile_config
    )
    
    # 生成测试用例
    test_cases = tester.generate_test_cases(
        count=count,
        complexity=complexity,
        categories=categories,
        scenario_types=scenario_types
    )
    
    # 运行测试
    tester.run_tests(
        test_cases=test_cases,
        bot_profile_extractor=bot_profile_extractor,
        bot_responses=bot_responses,
        user_ids=user_ids,
        tenant_outer_ids=tenant_outer_ids,
        use_api=use_api
    )
    
    # 生成报告
    return tester.generate_report()


def save_persona_report(
    report: PersonaTestReport,
    output_dir: str,
    filename: str | None = None
) -> str:
    """
    保存画像测试报告
    
    Args:
        report: 测试报告
        output_dir: 输出目录
        filename: 文件名（可选）
        
    Returns:
        报告文件路径
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if filename is None:
        filename = f"persona_profile_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] 报告已保存: {filepath}")
    return filepath


def generate_persona_markdown_report(report: PersonaTestReport) -> str:
    """
    生成Markdown格式的报告
    
    Args:
        report: 测试报告
        
    Returns:
        Markdown格式报告
    """
    lines = [
        "# 用户画像构建准确率测试报告",
        "",
        f"**测试时间**: {report['timestamp']}",
        "",
        f"**模式**: {'接口模式' if report.get('api_mode') else '本地模式'}",
        "",
        "## 测试概览",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 总测试数 | {report['total']} |",
        f"| 通过数 | {report['passed']} |",
        f"| 失败数 | {report['failed']} |",
        f"| 通过率 | {report['pass_rate']}% |",
        ""
    ]
    
    # 接口模式统计
    if report.get("api_mode"):
        lines.extend([
            "## 接口调用统计",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 接口成功数 | {report.get('api_success_count', 0)} |",
            f"| 接口失败数 | {report.get('api_fail_count', 0)} |",
            ""
        ])
    
    lines.extend([
        "## 画像构建指标",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 字段召回率 | {report['avg_field_recall']:.2%} |",
        f"| 字段精确率 | {report['avg_field_precision']:.2%} |",
        f"| 值准确率 | {report['avg_value_accuracy']:.2%} |",
        f"| 综合得分 | {report['avg_overall_score']} |",
        "",
        "## 等级分布",
        ""
    ])
    
    grade_names = {
        "excellent": "优秀 (≥90)",
        "good": "良好 (≥80)",
        "pass": "合格 (≥60)",
        "fail": "不合格 (<60)"
    }
    
    for grade, count in report["grade_distribution"].items():
        lines.append(f"- {grade_names.get(grade, grade)}: {count} 个")
    
    # 字段统计
    if report["field_stats"]:
        lines.extend([
            "",
            "## 字段级统计",
            "",
            "| 字段 | 准确率 | 平均得分 | 最常见匹配类型 |",
            "|------|--------|----------|----------------|"
        ])
        
        for field_name, stats in report["field_stats"].items():
            lines.append(
                f"| {field_name} | {stats['accuracy_rate']:.2%} | {stats['avg_score']} | {stats['most_common_type']} |"
            )
    
    # 详细结果
    lines.extend([
        "",
        "## 详细测试结果",
        ""
    ])
    
    for i, result in enumerate(report["results"][:20], 1):  # 只显示前20个
        lines.append(f"### 测试用例 {i}: {result['test_case_id']}")
        lines.append("")
        lines.append(f"**用户输入**: {result['user_input']}")
        lines.append("")
        if result.get("api_source"):
            lines.append(f"**画像来源**: {result['api_source']}")
            lines.append("")
        lines.append(f"**期望画像**:")
        lines.append(f"```json")
        lines.append(json.dumps(result['expected_profile'], ensure_ascii=False, indent=2))
        lines.append(f"```")
        lines.append("")
        lines.append(f"**实际画像**:")
        lines.append(f"```json")
        lines.append(json.dumps(result['actual_profile'], ensure_ascii=False, indent=2))
        lines.append(f"```")
        lines.append("")
        lines.append(f"**评估结果**: 得分 {result['evaluation']['overall_score']} | 等级 {result['evaluation']['grade']} | {'✓ 通过' if result['evaluation']['is_pass'] else '✗ 未通过'}")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    if len(report["results"]) > 20:
        lines.append(f"*... 还有 {len(report['results']) - 20} 个测试用例未显示*")
    
    return "\n".join(lines)


if __name__ == "__main__":
    # 测试模块
    print("=" * 60)
    print("用户画像构建测试模块测试")
    print("=" * 60)
    
    # 模拟测试
    test_cases = [
        PersonaTestCase(
            test_case_id="test_001",
            user_input="我叫张三，25岁，想买个iPhone 15，觉得8000元有点贵了",
            expected_profile={
                "name": "张三",
                "age": 25,
                "product": "iPhone 15",
                "price_sensitivity": "expensive"
            },
            complexity="medium",
            scenario_type="price_negotiation",
            category="手机"
        )
    ]
    
    # 模拟Bot回复和画像
    bot_responses = ["好的张三先生，iPhone 15目前有优惠活动..."]
    
    def mock_extractor(user_input, bot_response):
        return {
            "name": "张三",
            "age": 25,
            "product": "iPhone",
            "price_sensitivity": "expensive"
        }
    
    tester = PersonaProfileTester()
    results = tester.run_tests(
        test_cases=test_cases,
        bot_profile_extractor=mock_extractor,
        bot_responses=bot_responses
    )
    
    report = tester.generate_report()
    
    print(f"\n测试完成:")
    print(f"  通过率: {report['pass_rate']}%")
    print(f"  平均得分: {report['avg_overall_score']}")
    print(f"  字段召回率: {report['avg_field_recall']:.2%}")
