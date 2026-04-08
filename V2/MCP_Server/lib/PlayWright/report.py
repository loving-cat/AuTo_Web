"""报告模块 - 已修复：REPORTS_DIR使用线程本地存储实现会话隔离"""

import os
import json
import sys
import threading
from datetime import datetime
from typing import TypedDict, Optional, Any, cast

# 获取脚本所在目录，然后拼接 reports 目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")

# 线程本地存储 - 每个线程有独立的报告目录
_thread_local = threading.local()
_lock = threading.Lock()

def get_reports_dir() -> str:
    """获取当前线程的报告目录 - 已隔离"""
    if hasattr(_thread_local, 'reports_dir') and _thread_local.reports_dir:
        return _thread_local.reports_dir
    return _DEFAULT_REPORTS_DIR

def set_reports_dir(report_dir: str):
    """设置当前线程的报告目录"""
    with _lock:
        _thread_local.reports_dir = report_dir

def get_session_reports_dir(session_id: str) -> str:
    """获取指定会话的报告目录"""
    if session_id:
        return os.path.join(SCRIPT_DIR, "reports", session_id)
    return _DEFAULT_REPORTS_DIR

# 兼容性：保留REPORTS_DIR但改为动态获取
@property
def REPORTS_DIR():
    """兼容性属性 - 实际使用get_reports_dir()"""
    return get_reports_dir()

# 导入裁判模块
try:
    from .judge import (
        batch_judge,
        calculate_accuracy,
        JudgeResult,
        calculate_epr,
        calculate_memory_recall_score,
    )
    from .human_like_eval import evaluate_human_like, HumanLikeResult
    from .chaos_matrix import (
        calculate_chaos_matrix,
        calculate_memory_metrics,
        format_chaos_matrix_report,
        format_memory_report,
    )
except ImportError:
    # 添加项目路径 (report.py -> PlayWright -> lib -> MCP_Server -> Auto_aiwa)
    _project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from MCP_Server.lib.PlayWright.judge import (
        batch_judge,
        calculate_accuracy,
        JudgeResult,
        calculate_epr,
        calculate_memory_recall_score,
    )  # type: ignore
    from MCP_Server.lib.PlayWright.human_like_eval import (
        evaluate_human_like,
        HumanLikeResult,
    )  # type: ignore
    from MCP_Server.lib.PlayWright.chaos_matrix import (
        calculate_chaos_matrix,
        calculate_memory_metrics,
        format_chaos_matrix_report,
        format_memory_report,
    )  # type: ignore


class ResponseTimeStats(TypedDict):
    """响应时间统计"""

    average: float
    min: float
    max: float
    first_token_avg: float  # 首字出现平均时间
    first_token_min: float  # 首字出现最短时间
    first_token_max: float  # 首字出现最长时间
    unit: str


class AccuracyStats(TypedDict):
    """精确率统计"""

    total: int
    correct: int
    incorrect: int
    accuracy_rate: float
    avg_score: float
    high_score_count: int
    medium_score_count: int
    low_score_count: int


class HumanLikeStats(TypedDict):
    """拟人化评估统计"""

    total: int  # 评估总数
    pass_count: int  # 通过数（>=70分）
    fail_count: int  # 未通过数
    pass_rate: float  # 通过率
    avg_score: float  # 平均总分
    avg_format_score: float  # 平均格式分
    avg_tone_score: float  # 平均语气分
    avg_persona_score: float  # 平均人设分
    avg_rhythm_score: float  # 平均节奏分


class ContextAccuracyStats(TypedDict):
    """多轮对话上下文准确率统计（单独计算）"""

    total_reference_questions: int  # 回问问题总数
    context_success_count: int  # 上下文处理成功数
    context_accuracy_rate: float  # 上下文准确率
    avg_context_score: float  # 平均上下文得分
    reference_turns: list[int]  # 回问轮次列表
    success_by_turn: dict[int, bool]  # 各轮回问成功情况


class PersonaAccuracyStats(TypedDict):
    """人设贴合度准确率统计（单独计算）"""

    total: int  # 评估总数
    persona_pass_count: int  # 人设贴合通过数（>=80分）
    persona_fail_count: int  # 人设贴合未通过数
    persona_accuracy_rate: float  # 人设贴合准确率
    avg_persona_score: float  # 平均人设得分
    high_persona_count: int  # 高分(>=90)数量
    medium_persona_count: int  # 中分(70-89)数量
    low_persona_count: int  # 低分(<70)数量


class EPRStats(TypedDict):
    """错误传播率统计"""

    epr: float  # EPR 值
    p_error_after_error: float  # 错误后下一轮错误概率
    p_error_after_correct: float  # 正确后下一轮错误概率
    error_transitions: int  # 错误传播统计样本数
    correct_transitions: int  # 正确传播统计样本数
    interpretation: str  # 风险等级解读


class MemoryRecallStats(TypedDict):
    """记忆召回统计"""

    total_reference_turns: int  # 回问总轮次数
    correct_reference_turns: int  # 正确处理的回问数
    memory_recall_rate: float  # 记忆召回率
    avg_reference_score: float  # 回问平均得分
    avg_context_coherence: float  # 平均上下文连贯性
    interpretation: str  # 能力等级解读


class PersonaProfileStats(TypedDict):
    """用户画像构建准确率统计"""

    total: int  # 测试总数
    passed: int  # 通过数
    failed: int  # 失败数
    pass_rate: float  # 通过率
    avg_field_recall: float  # 平均字段召回率
    avg_field_precision: float  # 平均字段精确率
    avg_value_accuracy: float  # 平均值准确率
    avg_overall_score: float  # 平均综合得分
    grade_distribution: dict  # 等级分布 {excellent, good, pass, fail}
    field_stats: dict  # 字段级统计


class ProductCatalogStats(TypedDict):
    """商品库评估统计"""

    total: int  # 商品相关问题总数
    price_accuracy_rate: float  # 商品价格准确率
    info_completeness_rate: float  # 商品信息完整度
    image_recognition_rate: float  # 图片问题识别率
    code_match_rate: float  # 商品编码匹配率
    product_questions: int  # 商品相关问题数
    image_questions: int  # 图片问题数
    price_correct: int  # 价格正确数
    info_complete: int  # 信息完整数
    image_recognized: int  # 图片识别成功数
    code_matched: int  # 编码匹配数


class TestResult(TypedDict):
    """测试结果"""

    question: str
    answer: str
    response_time: float
    first_token_time: float  # 首字出现时间
    success: bool
    judge_result: Optional[JudgeResult]
    human_like_result: Optional[HumanLikeResult]  # 拟人化评估结果


class TestReport(TypedDict):
    """测试报告"""

    timestamp: str
    total: int
    success: int
    failed: int
    success_rate: float
    response_time_stats: ResponseTimeStats
    accuracy_stats: Optional[AccuracyStats]
    human_like_stats: Optional[HumanLikeStats]  # 拟人化评估统计
    context_stats: Optional[
        dict
    ]  # 多轮对话上下文评估统计（新版集成在 accuracy_stats 中）
    context_accuracy_stats: Optional[
        ContextAccuracyStats
    ]  # 多轮对话上下文准确率统计（单独）
    persona_accuracy_stats: Optional[
        PersonaAccuracyStats
    ]  # 人设贴合度准确率统计（单独）
    epr_stats: Optional[EPRStats]  # 错误传播率统计
    memory_recall_stats: Optional[MemoryRecallStats]  # 记忆召回统计
    persona_profile_stats: Optional[PersonaProfileStats]  # 用户画像构建准确率统计
    product_catalog_stats: Optional[ProductCatalogStats]  # 商品库评估统计
    is_multi_turn: bool  # 是否是多轮对话测试
    results: list[TestResult]


def batch_evaluate_human_like(
    results: list[TestResult],
) -> tuple[list[TestResult], Optional[HumanLikeStats]]:
    """批量评估拟人化程度

    Args:
        results: 测试结果列表

    Returns:
        (更新后的结果列表, 拟人化统计)
    """
    valid_results = [r for r in results if r["success"] and r.get("answer")]

    if not valid_results:
        return results, None

    total_scores = []
    format_scores = []
    tone_scores = []
    persona_scores = []
    rhythm_scores = []
    pass_count = 0

    for result in results:
        if result["success"] and result.get("answer"):
            # 进行拟人化评估
            hl_result = evaluate_human_like(
                result["answer"], latency_ms=result.get("response_time", 0) * 1000
            )
            result["human_like_result"] = hl_result

            total_scores.append(hl_result["total_score"])
            format_scores.append(hl_result["format_score"]["score"])
            tone_scores.append(hl_result["tone_score"]["score"])
            persona_scores.append(hl_result["persona_score"]["score"])
            rhythm_scores.append(hl_result["rhythm_score"]["score"])

            if hl_result["is_human_like"]:
                pass_count += 1
        else:
            result["human_like_result"] = None

    if not total_scores:
        return results, None

    stats: HumanLikeStats = {
        "total": len(total_scores),
        "pass_count": pass_count,
        "fail_count": len(total_scores) - pass_count,
        "pass_rate": round(pass_count / len(total_scores) * 100, 1),
        "avg_score": round(sum(total_scores) / len(total_scores), 1),
        "avg_format_score": round(sum(format_scores) / len(format_scores), 1),
        "avg_tone_score": round(sum(tone_scores) / len(tone_scores), 1),
        "avg_persona_score": round(sum(persona_scores) / len(persona_scores), 1),
        "avg_rhythm_score": round(sum(rhythm_scores) / len(rhythm_scores), 1),
    }

    return results, stats


def calculate_context_accuracy(
    results: list[TestResult],
) -> Optional[ContextAccuracyStats]:
    """计算多轮对话上下文准确率（单独统计）

    多轮对话上下文准确率的判断逻辑：
    1. 只统计回问问题（is_reference_question=True）
    2. 上下文处理成功 = context_handled=True 且 context_score >= 60
    3. 上下文准确率 = 成功数 / 回问总数

    Args:
        results: 测试结果列表（已包含 context_result 或 context_judge_result）

    Returns:
        上下文准确率统计，如果没有回问问题则返回 None
    """
    # 固定回问轮次配置（与agent.py保持一致）
    CALLBACK_TURNS = [3, 7, 10, 15, 20]
    CALLBACK_REFERENCE_STRATEGY = {
        3: 1,  # 第3轮回问第1轮（短期记忆）
        7: 5,  # 第7轮回问第5轮（中期记忆）
        10: 2,  # 第10轮回问第2轮（长期记忆）
        15: 8,  # 第15轮回问第8轮（中期记忆）
        20: 4,  # 第20轮回问第4轮（极限记忆）
    }

    # 筛选回问问题
    reference_results = []
    for i, r in enumerate(results):
        # 兼容两种字段名：context_result 和 context_judge_result
        context_judge = r.get("context_result") or r.get("context_judge_result")
        turn_index = r.get("turn_index", i + 1)

        # 判断是否是回问问题
        is_reference = False
        reference_turn = 0

        if context_judge:
            is_reference = context_judge.get("is_reference_question", False)
            reference_turn = context_judge.get("reference_turn", 0)
        else:
            # 如果没有 context_judge，根据固定轮次判断
            is_reference = turn_index in CALLBACK_TURNS
            reference_turn = CALLBACK_REFERENCE_STRATEGY.get(turn_index, 0)

        if is_reference:
            reference_results.append((turn_index, r, context_judge, reference_turn))

    if not reference_results:
        return None

    # 计算统计
    total_reference = len(reference_results)
    success_count = 0
    total_score = 0
    reference_turns = []
    success_by_turn = {}
    details_by_turn = {}  # 详细信息

    # 上下文处理成功的阈值：得分 >= 60 且 context_handled=True
    PASS_THRESHOLD = 60

    for turn, result, context_judge, ref_turn in reference_results:
        if context_judge:
            # 从上下文评估结果中获取
            context_handled = context_judge.get("context_handled", False)
            context_score = context_judge.get("context_score", 0)
            # 成功条件：context_handled=True 且得分 >= 60
            is_success = context_handled and context_score >= PASS_THRESHOLD
            reason = context_judge.get("reason", "")
            key_info = context_judge.get("key_info_found", "")
        else:
            # 没有评估结果，默认失败
            is_success = False
            context_score = 0
            reason = "未进行上下文评估"
            key_info = ""

        if is_success:
            success_count += 1
        total_score += context_score
        reference_turns.append(turn)
        success_by_turn[turn] = is_success
        details_by_turn[turn] = {
            "reference_turn": ref_turn,
            "success": is_success,
            "score": context_score,
            "reason": reason[:50] if reason else "",
            "key_info": key_info[:100] if key_info else "",
        }

    # 计算记忆类型统计
    short_term_success = 0  # 短期记忆成功数（回问间隔 <= 3轮）
    short_term_total = 0
    long_term_success = 0  # 长期记忆成功数（回问间隔 > 3轮）
    long_term_total = 0

    for turn, result, context_judge, ref_turn in reference_results:
        gap = turn - ref_turn
        if context_judge:
            context_handled = context_judge.get("context_handled", False)
            context_score = context_judge.get("context_score", 0)
            is_success = context_handled and context_score >= PASS_THRESHOLD
        else:
            is_success = False

        if gap <= 3:
            short_term_total += 1
            if is_success:
                short_term_success += 1
        else:
            long_term_total += 1
            if is_success:
                long_term_success += 1

    return ContextAccuracyStats(
        total_reference_questions=total_reference,
        context_success_count=success_count,
        context_accuracy_rate=round(success_count / total_reference * 100, 2)
        if total_reference > 0
        else 0,
        avg_context_score=round(total_score / total_reference, 2)
        if total_reference > 0
        else 0,
        reference_turns=reference_turns,
        success_by_turn=success_by_turn,
    )


def calculate_persona_accuracy(
    results: list[TestResult],
) -> Optional[PersonaAccuracyStats]:
    """计算人设贴合度准确率（单独统计）

    Args:
        results: 测试结果列表（已包含 human_like_result）

    Returns:
        人设贴合度准确率统计
    """
    persona_scores = []

    for r in results:
        if r["success"] and r.get("human_like_result"):
            hl_result = r.get("human_like_result")
            if hl_result:
                persona_score = hl_result.get("persona_score", {})
                score = persona_score.get("score", 0)
                persona_scores.append(score)

    if not persona_scores:
        return None

    # 人设贴合通过标准：>=80分
    pass_threshold = 80
    pass_count = sum(1 for s in persona_scores if s >= pass_threshold)

    # 分档统计
    high_count = sum(1 for s in persona_scores if s >= 90)
    medium_count = sum(1 for s in persona_scores if 70 <= s < 90)
    low_count = sum(1 for s in persona_scores if s < 70)

    return PersonaAccuracyStats(
        total=len(persona_scores),
        persona_pass_count=pass_count,
        persona_fail_count=len(persona_scores) - pass_count,
        persona_accuracy_rate=round(pass_count / len(persona_scores) * 100, 2)
        if persona_scores
        else 0,
        avg_persona_score=round(sum(persona_scores) / len(persona_scores), 2),
        high_persona_count=high_count,
        medium_persona_count=medium_count,
        low_persona_count=low_count,
    )


def calculate_persona_profile_accuracy(
    persona_results: list[dict[str, Any]],
) -> Optional[PersonaProfileStats]:
    """计算用户画像构建准确率
    
    评估 Bot 从用户对话中提取和构建用户画像的准确率。
    需要传入画像评估结果列表，每个结果包含 evaluation 字段。
    
    Args:
        persona_results: 画像评估结果列表，每项包含:
            - user_input: 用户输入
            - expected_profile: 期望画像
            - actual_profile: 实际画像（Bot构建的）
            - evaluation: 评估结果
    
    Returns:
        用户画像构建准确率统计
    """
    if not persona_results:
        return None
    
    total = len(persona_results)
    passed = 0
    failed = 0
    
    field_recalls = []
    field_precisions = []
    value_accuracies = []
    overall_scores = []
    
    grade_distribution = {
        "excellent": 0,
        "good": 0,
        "pass": 0,
        "fail": 0
    }
    
    # 字段级统计聚合
    all_field_stats: dict[str, dict[str, Any]] = {}
    
    for result in persona_results:
        evaluation = result.get("evaluation", {})
        
        if not evaluation:
            continue
        
        overall_score = evaluation.get("overall_score", 0)
        is_pass = evaluation.get("is_pass", False)
        grade = evaluation.get("grade", "fail")
        
        overall_scores.append(overall_score)
        
        if is_pass:
            passed += 1
        else:
            failed += 1
        
        # 统计等级分布
        if grade in grade_distribution:
            grade_distribution[grade] += 1
        
        # 收集指标
        field_recalls.append(evaluation.get("field_recall", 0))
        field_precisions.append(evaluation.get("field_precision", 0))
        value_accuracies.append(evaluation.get("value_accuracy", 0))
        
        # 聚合字段统计
        field_stats = evaluation.get("field_stats", {})
        for field_name, field_data in field_stats.items():
            if field_name not in all_field_stats:
                all_field_stats[field_name] = {
                    "count": 0,
                    "total_score": 0,
                    "match_types": {}
                }
            
            all_field_stats[field_name]["count"] += 1
            all_field_stats[field_name]["total_score"] += field_data.get("score", 0)
            
            match_type = field_data.get("match_type", "unknown")
            if match_type not in all_field_stats[field_name]["match_types"]:
                all_field_stats[field_name]["match_types"][match_type] = 0
            all_field_stats[field_name]["match_types"][match_type] += 1
    
    if not overall_scores:
        return None
    
    # 计算字段级平均统计
    field_stats_summary = {}
    for field_name, stats in all_field_stats.items():
        count = stats["count"]
        if count > 0:
            avg_score = stats["total_score"] / count
            # 找出最常见的匹配类型
            most_common_match = max(stats["match_types"].items(), key=lambda x: x[1])[0] if stats["match_types"] else "unknown"
            field_stats_summary[field_name] = {
                "count": count,
                "avg_score": round(avg_score, 2),
                "most_common_match": most_common_match,
                "match_type_distribution": stats["match_types"]
            }
    
    return PersonaProfileStats(
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=round(passed / total * 100, 2) if total > 0 else 0,
        avg_field_recall=round(sum(field_recalls) / len(field_recalls), 4) if field_recalls else 0,
        avg_field_precision=round(sum(field_precisions) / len(field_precisions), 4) if field_precisions else 0,
        avg_value_accuracy=round(sum(value_accuracies) / len(value_accuracies), 4) if value_accuracies else 0,
        avg_overall_score=round(sum(overall_scores) / len(overall_scores), 2) if overall_scores else 0,
        grade_distribution=grade_distribution,
        field_stats=field_stats_summary
    )


def calculate_product_catalog_accuracy(
    results: list[TestResult],
) -> Optional[ProductCatalogStats]:
    """计算商品库评估统计
    
    识别商品相关问题的依据：
    1. 问题中包含 [IMAGE:xxx] 标签（图片问题）
    2. 问题涉及商品价格、商品编码、商品名称等关键词
    
    评估指标：
    - 价格准确率：Bot 回答的价格信息是否正确
    - 信息完整度：Bot 是否提供了完整的商品信息
    - 图片识别率：Bot 是否正确识别了图片对应的商品
    - 编码匹配率：Bot 是否正确匹配了商品编码
    
    Args:
        results: 测试结果列表
    
    Returns:
        商品库评估统计，如果没有商品相关问题则返回 None
    """
    import re
    
    # 商品相关关键词
    product_keywords = [
        "价格", "多少钱", "费用", "售价", "优惠",
        "商品", "产品", "货号", "SKU", "编码",
        "库存", "现货", "有货", "缺货",
        "规格", "型号", "尺寸", "颜色",
        "图片", "照片", "样子", "外观"
    ]
    
    # 图片问题正则
    image_pattern = re.compile(r'\[IMAGE:([^\]]+)\]')
    
    # 统计变量
    product_questions = 0
    image_questions = 0
    price_correct = 0
    info_complete = 0
    image_recognized = 0
    code_matched = 0
    
    # 商品相关问题评估计数
    price_questions = 0
    info_questions = 0
    code_questions = 0
    
    for result in results:
        if not result.get("success"):
            continue
            
        question = result.get("question", "")
        answer = result.get("answer", "")
        judge_result = result.get("judge_result", {})
        
        # 检查是否是商品相关问题
        is_product_question = False
        
        # 检查图片问题
        image_match = image_pattern.search(question)
        if image_match:
            is_product_question = True
            image_questions += 1
            
            # 检查图片是否被正确识别
            # 如果 Bot 回答中提到了商品编码或相关商品信息，认为识别成功
            product_code = image_match.group(1)
            if product_code.upper() != "RANDOM" and product_code.upper() != "INVALID":
                if product_code in answer or judge_result.get("is_correct", False):
                    image_recognized += 1
        
        # 检查关键词
        for keyword in product_keywords:
            if keyword in question:
                is_product_question = True
                break
        
        if not is_product_question:
            continue
        
        product_questions += 1
        
        # 根据问题类型分类统计
        # 价格类问题
        if any(kw in question for kw in ["价格", "多少钱", "费用", "售价"]):
            price_questions += 1
            if judge_result.get("is_correct", False):
                price_correct += 1
        
        # 商品信息类问题
        if any(kw in question for kw in ["商品", "产品", "规格", "型号", "库存"]):
            info_questions += 1
            if judge_result.get("is_correct", False):
                info_complete += 1
        
        # 编码类问题
        if any(kw in question for kw in ["货号", "SKU", "编码"]):
            code_questions += 1
            if judge_result.get("is_correct", False):
                code_matched += 1
    
    # 如果没有商品相关问题，返回 None
    if product_questions == 0:
        return None
    
    # 计算各项指标
    price_accuracy_rate = round(price_correct / price_questions * 100, 2) if price_questions > 0 else 0
    info_completeness_rate = round(info_complete / product_questions * 100, 2) if product_questions > 0 else 0
    image_recognition_rate = round(image_recognized / image_questions * 100, 2) if image_questions > 0 else 0
    code_match_rate = round(code_matched / product_questions * 100, 2) if product_questions > 0 else 0
    
    return ProductCatalogStats(
        total=product_questions,
        price_accuracy_rate=price_accuracy_rate,
        info_completeness_rate=info_completeness_rate,
        image_recognition_rate=image_recognition_rate,
        code_match_rate=code_match_rate,
        product_questions=product_questions,
        image_questions=image_questions,
        price_correct=price_correct,
        info_complete=info_complete,
        image_recognized=image_recognized,
        code_matched=code_matched
    )


def save_report(
    results: list[TestResult],
    knowledge_content: str = "",
    report_dir: str = "",
    is_multi_turn: bool = False,
    bot_persona: str = "",
    persona_profile_stats: Optional[PersonaProfileStats] = None,
) -> TestReport:
    """保存测试报告

    Args:
        results: 测试结果列表
        knowledge_content: 知识库内容，用于裁判评估
        report_dir: 报告保存目录，如果为空则使用默认目录
        is_multi_turn: 是否是多轮对话测试
        bot_persona: BOT的人设（如"二次元"、"专业客服"等）
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_report_{timestamp}.json"

    # 使用传入的报告目录或默认目录
    output_dir = report_dir if report_dir else REPORTS_DIR

    # 计算统计数据
    total = len(results)
    success = sum(1 for r in results if r["success"])
    failed = total - success

    # 计算响应时间统计
    response_times = [r["response_time"] for r in results if r["success"]]
    avg_response_time = (
        sum(response_times) / len(response_times) if response_times else 0
    )
    min_response_time = min(response_times) if response_times else 0
    max_response_time = max(response_times) if response_times else 0

    # 计算首字出现时间统计
    first_token_times = [
        r.get("first_token_time", 0)
        for r in results
        if r["success"] and r.get("first_token_time", 0) > 0
    ]
    avg_first_token = (
        sum(first_token_times) / len(first_token_times) if first_token_times else 0
    )
    min_first_token = min(first_token_times) if first_token_times else 0
    max_first_token = max(first_token_times) if first_token_times else 0

    # 显式构造类型化对象
    stats: ResponseTimeStats = {
        "average": round(avg_response_time, 2),
        "min": round(min_response_time, 2),
        "max": round(max_response_time, 2),
        "first_token_avg": round(avg_first_token, 2),
        "first_token_min": round(min_first_token, 2),
        "first_token_max": round(max_first_token, 2),
        "unit": "seconds",
    }

    # 裁判评估和精确率计算（多轮对话自动使用整组评估）
    accuracy_stats: Optional[AccuracyStats] = None
    if knowledge_content:
        print("\n[JUDGE] 开始裁判评估...")
        if bot_persona:
            print(f"[JUDGE] BOT人设: {bot_persona}")
        # batch_judge 会自动检测多轮对话并调用 batch_judge_multi_turn
        results = cast(
            list[TestResult],
            batch_judge(cast(list[dict[str, Any]], results), knowledge_content, bot_persona=bot_persona)
        )
        accuracy_stats = cast(AccuracyStats, calculate_accuracy(cast(list[dict[str, Any]], results)))
        print(
            f"[JUDGE] 精确率: {accuracy_stats['accuracy_rate']}% (平均分: {accuracy_stats['avg_score']})"
        )

    # 上下文评估统计（从 accuracy_stats 中获取，新版已集成）
    context_stats = None

    # 拟人化评估
    human_like_stats: Optional[HumanLikeStats] = None
    print("\n[HUMAN_LIKE] 开始拟人化评估...")
    results, human_like_stats = batch_evaluate_human_like(results)
    if human_like_stats:
        print(
            f"[HUMAN_LIKE] 通过率: {human_like_stats['pass_rate']}% (平均分: {human_like_stats['avg_score']})"
        )

    # 多轮对话上下文准确率统计（单独计算）
    context_accuracy_stats: Optional[ContextAccuracyStats] = None
    if is_multi_turn:
        context_accuracy_stats = calculate_context_accuracy(results)
        if context_accuracy_stats:
            print(
                f"[CONTEXT_ACCURACY] 回问准确率: {context_accuracy_stats['context_accuracy_rate']}% ({context_accuracy_stats['context_success_count']}/{context_accuracy_stats['total_reference_questions']})"
            )

    # 人设贴合度准确率统计（单独计算）
    persona_accuracy_stats: Optional[PersonaAccuracyStats] = None
    persona_accuracy_stats = calculate_persona_accuracy(results)
    if persona_accuracy_stats:
        print(
            f"[PERSONA_ACCURACY] 人设贴合准确率: {persona_accuracy_stats['persona_accuracy_rate']}% (平均分: {persona_accuracy_stats['avg_persona_score']})"
        )

    # EPR 错误传播率统计（多轮对话）
    epr_stats: Optional[EPRStats] = None
    memory_recall_stats: Optional[MemoryRecallStats] = None
    if is_multi_turn and accuracy_stats:
        print("\n[EPR] 计算错误传播率...")
        epr_stats = cast(EPRStats, calculate_epr(cast(list[dict[str, Any]], results)))
        if epr_stats:
            print(
                f"[EPR] 错误传播率: {epr_stats['epr']} - {epr_stats['interpretation']}"
            )

        print("\n[MEMORY_RECALL] 计算记忆召回率...")
        memory_recall_stats = cast(MemoryRecallStats, calculate_memory_recall_score(cast(list[dict[str, Any]], results)))
        if memory_recall_stats:
            print(
                f"[MEMORY_RECALL] 记忆召回率: {memory_recall_stats['memory_recall_rate']}% ({memory_recall_stats['correct_reference_turns']}/{memory_recall_stats['total_reference_turns']})"
            )

    # 商品库评估统计
    product_catalog_stats: Optional[ProductCatalogStats] = None
    print("\n[PRODUCT_CATALOG] 计算商品库评估统计...")
    product_catalog_stats = calculate_product_catalog_accuracy(results)
    if product_catalog_stats:
        print(
            f"[PRODUCT_CATALOG] 商品相关问题: {product_catalog_stats['total']}个, "
            f"价格准确率: {product_catalog_stats['price_accuracy_rate']}%, "
            f"图片识别率: {product_catalog_stats['image_recognition_rate']}%"
        )

    report: TestReport = {
        "timestamp": timestamp,
        "total": total,
        "success": success,
        "failed": failed,
        "success_rate": round(success / total * 100, 2) if total > 0 else 0,
        "response_time_stats": stats,
        "accuracy_stats": accuracy_stats,
        "human_like_stats": human_like_stats,
        "context_stats": context_stats,
        "context_accuracy_stats": context_accuracy_stats,
        "persona_accuracy_stats": persona_accuracy_stats,
        "epr_stats": epr_stats,
        "memory_recall_stats": memory_recall_stats,
        "persona_profile_stats": persona_profile_stats,  # 用户画像构建准确率统计
        "product_catalog_stats": product_catalog_stats,  # 商品库评估统计
        "is_multi_turn": is_multi_turn,
        "results": results,
    }

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 报告已保存: {filepath}")

    # 生成Markdown格式报告
    save_markdown_report(
        results,
        timestamp,
        accuracy_stats,
        human_like_stats,
        context_stats,
        context_accuracy_stats,
        persona_accuracy_stats,
        epr_stats,
        memory_recall_stats,
        None,
        is_multi_turn,
        output_dir,
        product_catalog_stats,
    )

    return report


def save_markdown_report(
    results: list[TestResult],
    timestamp: str,
    accuracy_stats: Optional[AccuracyStats] = None,
    human_like_stats: Optional[HumanLikeStats] = None,
    context_stats: Optional[dict] = None,
    context_accuracy_stats: Optional[ContextAccuracyStats] = None,
    persona_accuracy_stats: Optional[PersonaAccuracyStats] = None,
    epr_stats: Optional[EPRStats] = None,
    memory_recall_stats: Optional[MemoryRecallStats] = None,
    persona_profile_stats: Optional[PersonaProfileStats] = None,
    is_multi_turn: bool = False,
    report_dir: str = "",
    product_catalog_stats: Optional[ProductCatalogStats] = None,
) -> None:
    """保存Markdown格式报告

    Args:
        results: 测试结果列表
        timestamp: 时间戳
        accuracy_stats: 精确率统计
        human_like_stats: 拟人化评估统计
        context_stats: 多轮对话上下文评估统计（新版集成在 accuracy_stats 中）
        context_accuracy_stats: 多轮对话上下文准确率统计（单独）
        persona_accuracy_stats: 人设贴合度准确率统计（单独）
        epr_stats: 错误传播率统计
        memory_recall_stats: 记忆召回统计
        persona_profile_stats: 用户画像构建准确率统计
        is_multi_turn: 是否是多轮对话测试
        report_dir: 报告保存目录，如果为空则使用默认目录
        product_catalog_stats: 商品库评估统计
    """
    filename = f"test_report_{timestamp}.md"

    # 使用传入的报告目录或默认目录
    output_dir = report_dir if report_dir else REPORTS_DIR

    # 计算统计数据
    total = len(results)
    success = sum(1 for r in results if r["success"])
    failed = total - success

    # 计算响应时间统计
    response_times = [r["response_time"] for r in results if r["success"]]
    avg_response_time = (
        sum(response_times) / len(response_times) if response_times else 0
    )
    success_rate = round(success / total * 100, 2) if total > 0 else 0

    # 生成Markdown内容
    if is_multi_turn:
        markdown_content = f"# AI销售机器人多轮对话测试报告\n\n"
    else:
        markdown_content = f"# AI销售机器人测试报告\n\n"
    markdown_content += (
        f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )

    # 多轮对话上下文评估统计（如果是多轮测试）
    if is_multi_turn and context_stats:
        markdown_content += "## 🔄 多轮对话上下文评估\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 总轮次 | {context_stats['total_turns']} |\n"
        markdown_content += f"| 回问轮次 | {context_stats['reference_turns']} |\n"
        markdown_content += (
            f"| **上下文成功率** | **{context_stats['context_success_rate']}%** |\n"
        )
        markdown_content += (
            f"| 平均上下文得分 | {context_stats['avg_context_score']}分 |\n"
        )
        markdown_content += (
            f"| **极限轮次** | **第{context_stats['limit_turn']}轮** |\n"
        )
        markdown_content += f"| 极限类型 | {context_stats['limit_type']} |\n"
        markdown_content += "\n"

        # 上下文得分变化趋势
        degradation = context_stats.get("context_degradation", [])
        if degradation:
            markdown_content += "### 上下文得分趋势\n\n"
            markdown_content += "```\n"
            for d in degradation:
                marker = "📍" if d["is_reference"] else "  "
                markdown_content += f"{marker} 第{d['turn']:2d}轮: {'█' * (d['score'] // 10)}{'░' * (10 - d['score'] // 10)} {d['score']}分\n"
            markdown_content += "```\n"
            markdown_content += "📍 = 回问轮次\n\n"

    # 精确率统计（如果有）
    if accuracy_stats:
        group_stats = accuracy_stats.get("group_stats", {})
        is_multi_turn = (
            group_stats.get("is_multi_turn", False) if group_stats else False
        )

        markdown_content += "## 精确率统计\n\n"

        # ========== 单轮精确率 ==========
        markdown_content += "### 单轮精确率\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += (
            f"| 正确回答 | {accuracy_stats['correct']}/{accuracy_stats['total']} |\n"
        )
        markdown_content += (
            f"| **单轮精确率** | **{accuracy_stats['accuracy_rate']}%** |\n"
        )
        markdown_content += f"| 平均得分 | {accuracy_stats['avg_score']}分 |\n"
        markdown_content += f"| 高分(80+) | {accuracy_stats['high_score_count']}个 |\n"
        markdown_content += (
            f"| 中分(50-79) | {accuracy_stats['medium_score_count']}个 |\n"
        )
        markdown_content += f"| 低分(<50) | {accuracy_stats['low_score_count']}个 |\n\n"

        # 各模型独立统计
        model_stats = accuracy_stats.get("model_stats", {})
        if model_stats:
            markdown_content += "#### 各裁判模型独立统计\n\n"
            markdown_content += f"| 裁判模型 | 正确数 | 总数 | 精确率 | 平均分 |\n"
            markdown_content += f"|----------|--------|------|--------|--------|\n"
            for model_name, stats in model_stats.items():
                markdown_content += f"| {stats['display_name']} | {stats['correct']} | {stats['total']} | {stats['accuracy_rate']}% | {stats['avg_score']}分 |\n"
            markdown_content += "\n"

        # ========== 混沌矩阵统计 ==========
        chaos_matrix = accuracy_stats.get("chaos_matrix", {})
        if chaos_matrix and chaos_matrix.get("total", 0) > 0:
            markdown_content += "### 混沌矩阵统计\n\n"
            markdown_content += "| 指标 | 数量 | 说明 |\n"
            markdown_content += "|------|------|------|\n"
            markdown_content += f"| TP (True Positive) | {chaos_matrix['TP']} | 有效问题，BOT正确回答 |\n"
            markdown_content += f"| TN (True Negative) | {chaos_matrix['TN']} | 异常问题，BOT正确拒绝 |\n"
            markdown_content += f"| FP (False Positive) | {chaos_matrix['FP']} | 异常问题，BOT错误接受 |\n"
            markdown_content += f"| FN (False Negative) | {chaos_matrix['FN']} | 有效问题，BOT错误拒绝 |\n"
            markdown_content += f"| **总计** | {chaos_matrix['total']} | |\n\n"

            markdown_content += "**性能指标**\n\n"
            markdown_content += "| 指标 | 值 | 说明 |\n"
            markdown_content += "|------|------|------|\n"
            markdown_content += (
                f"| 准确率 (Accuracy) | {chaos_matrix['accuracy']}% | (TP+TN)/Total |\n"
            )
            markdown_content += (
                f"| 精确率 (Precision) | {chaos_matrix['precision']}% | TP/(TP+FP) |\n"
            )
            markdown_content += (
                f"| 召回率 (Recall) | {chaos_matrix['recall']}% | TP/(TP+FN) |\n"
            )
            markdown_content += (
                f"| F1分数 | {chaos_matrix['f1_score']}% | 2*P*R/(P+R) |\n\n"
            )

            # FN 相关指标
            type_breakdown = chaos_matrix.get("type_breakdown", {})
            fn_stats = type_breakdown.get("meaningless", {})
            fn_total = fn_stats.get("total", 0)
            fn_incorrect = fn_stats.get("incorrect", 0)  # FN = BOT错误回答无意义问题
            fn_rate = round(fn_incorrect / fn_total * 100, 2) if fn_total > 0 else 0

            if fn_total > 0:
                markdown_content += "**FN检测指标**\n\n"
                markdown_content += "| 指标 | 值 | 说明 |\n"
                markdown_content += "|------|------|------|\n"
                markdown_content += (
                    f"| FN问题总数 | {fn_total} | 无意义/攻击性问句总数 |\n"
                )
                markdown_content += (
                    f"| FN检出数 | {fn_incorrect} | BOT错误回答的FN问题数 |\n"
                )
                markdown_content += (
                    f"| FN检出率 | {fn_rate}% | FN问题中BOT未正确拒绝的比例 |\n\n"
                )

            # 各类型详细统计
            if type_breakdown:
                markdown_content += (
                    "<details>\n<summary>📊 各类型详细统计</summary>\n\n"
                )
                markdown_content += "| 类型 | 正确 | 错误 | 总计 | 正确率 |\n"
                markdown_content += "|------|------|------|------|--------|\n"
                type_labels = {
                    "normal": "TP (正常)",
                    "boundary": "TN (边界)",
                    "abnormal": "TN (异常)",
                    "inductive": "FP (诱导)",
                    "meaningless": "FN (无意义)",
                }
                for q_type in [
                    "normal",
                    "boundary",
                    "abnormal",
                    "inductive",
                    "meaningless",
                ]:
                    stats = type_breakdown.get(q_type, {})
                    correct = stats.get("correct", 0)
                    incorrect = stats.get("incorrect", 0)
                    total = stats.get("total", 0)
                    rate = round(correct / total * 100, 2) if total > 0 else 0
                    label = type_labels.get(q_type, q_type)
                    markdown_content += (
                        f"| {label} | {correct} | {incorrect} | {total} | {rate}% |\n"
                    )
                markdown_content += "\n</details>\n\n"

        # ========== 记忆能力评估 ==========
        memory_metrics = accuracy_stats.get("memory_metrics", {})
        if memory_metrics:
            markdown_content += "### 记忆能力评估\n\n"
            markdown_content += "| 指标 | 值 | 说明 |\n"
            markdown_content += "|------|------|------|\n"
            markdown_content += f"| 记忆召回率 | {memory_metrics['memory_recall_rate']}% | 回问问题正确回答率 |\n"
            markdown_content += f"| 上下文连贯性 | {memory_metrics['context_coherence']}% | 对话上下文一致性 |\n"
            markdown_content += f"| 错误传播率 | {memory_metrics['error_propagation_rate']}% | 前序错误导致后续错误的比例 |\n\n"

            markdown_content += "**详细统计**：\n"
            markdown_content += (
                f"- 回问问题总数: {memory_metrics['total_callback_questions']}\n"
            )
            markdown_content += (
                f"- 正确回答回问: {memory_metrics['correct_callback_answers']}\n"
            )
            markdown_content += (
                f"- 上下文检查数: {memory_metrics['total_context_checks']}\n"
            )
            markdown_content += (
                f"- 连贯上下文数: {memory_metrics['coherent_contexts']}\n\n"
            )

        # ========== 多轮精确率 ==========
        if is_multi_turn:
            markdown_content += "### 多轮精确率\n\n"
            markdown_content += f"| 指标 | 数值 |\n"
            markdown_content += f"|------|------|\n"
            markdown_content += f"| 对话组数 | {group_stats['total_groups']} |\n"
            markdown_content += f"| 完全正确组数 | {group_stats['correct_groups']} |\n"
            markdown_content += (
                f"| **多轮精确率** | **{group_stats['group_accuracy_rate']}%** |\n\n"
            )

            # 各组详细统计
            groups_detail = group_stats.get("groups_detail", [])
            if groups_detail:
                markdown_content += "#### 各对话组详细统计\n\n"
                markdown_content += (
                    "| 组号 | 问题数 | 正确数 | 组精确率 | 平均分 | 状态 |\n"
                )
                markdown_content += (
                    "|------|--------|--------|----------|--------|------|\n"
                )
                for g in groups_detail:
                    status = "✅" if g["is_group_correct"] else "❌"
                    markdown_content += f"| 第{g['group_index'] + 1}组 | {g['total_questions']} | {g['correct_questions']} | {g['group_accuracy_rate']}% | {g['avg_score']}分 | {status} |\n"
                markdown_content += "\n**说明**: 每组内所有问题都正确才算该组正确\n\n"

    # ========== 单独统计：多轮对话上下文准确率 ==========
    if context_accuracy_stats:
        markdown_content += "## 🔄 多轮对话上下文准确率（单独统计）\n\n"
        markdown_content += (
            "> **判断标准**: 回问问题中，context_handled=True 且得分≥60分视为成功\n\n"
        )
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 回问问题总数 | {context_accuracy_stats['total_reference_questions']} |\n"
        markdown_content += (
            f"| 上下文处理成功 | {context_accuracy_stats['context_success_count']} |\n"
        )
        markdown_content += f"| **上下文准确率** | **{context_accuracy_stats['context_accuracy_rate']}%** |\n"
        markdown_content += (
            f"| 平均上下文得分 | {context_accuracy_stats['avg_context_score']}分 |\n"
        )
        markdown_content += "\n"

        # 各轮回问结果
        if context_accuracy_stats["reference_turns"]:
            markdown_content += "### 各轮回问结果详情\n\n"
            markdown_content += f"| 回问轮次 | 引用轮次 | 记忆跨度 | 结果 | 得分 |\n"
            markdown_content += f"|----------|----------|----------|------|------|\n"

            # 回问引用策略
            callback_strategy = {
                3: (1, "短期"),
                7: (5, "中期"),
                10: (2, "长期"),
                15: (8, "中期"),
                20: (4, "极限"),
            }

            for turn in context_accuracy_stats["reference_turns"]:
                success = context_accuracy_stats["success_by_turn"].get(turn, False)
                status = "✅ 成功" if success else "❌ 失败"

                # 获取引用轮次和记忆跨度
                ref_info = callback_strategy.get(turn, (1, "未知"))
                ref_turn = ref_info[0]
                memory_span = ref_info[1]

                # 尝试从结果中获取得分
                score = "-"
                for r in results:
                    if r.get("turn_index", 0) == turn:
                        ctx = r.get("context_result") or r.get("context_judge_result")
                        if ctx:
                            score = f"{ctx.get('context_score', 0)}分"
                        break

                markdown_content += f"| 第{turn}轮 | 第{ref_turn}轮 | {memory_span}记忆 | {status} | {score} |\n"
            markdown_content += "\n"

            # 记忆能力分析
            markdown_content += "### 记忆能力分析\n\n"
            markdown_content += "```\n"
            markdown_content += "回问轮次分布:\n"
            markdown_content += "  第3轮  → 第1轮  (短期记忆, 间隔2轮)\n"
            markdown_content += "  第7轮  → 第5轮  (中期记忆, 间隔2轮)\n"
            markdown_content += "  第10轮 → 第2轮  (长期记忆, 间隔8轮)\n"
            markdown_content += "  第15轮 → 第8轮  (中期记忆, 间隔7轮)\n"
            markdown_content += "  第20轮 → 第4轮  (极限记忆, 间隔16轮)\n"
            markdown_content += "```\n\n"

    # ========== EPR 错误传播率 ==========
    if epr_stats:
        markdown_content += "## ⚠️ EPR 错误传播率分析\n\n"
        markdown_content += "> **EPR (Error Propagation Rate)** 来源: ThReadMed-QA (arXiv:2603.11281)\n\n"
        markdown_content += f"| 指标 | 数值 | 说明 |\n"
        markdown_content += f"|------|------|------|\n"
        markdown_content += (
            f"| **EPR 值** | **{epr_stats['epr']}** | {epr_stats['interpretation']} |\n"
        )
        markdown_content += f"| 错误后下一轮错误概率 | {epr_stats['p_error_after_error']}% | 当前轮错误时，下一轮也错误的概率 |\n"
        markdown_content += f"| 正确后下一轮错误概率 | {epr_stats['p_error_after_correct']}% | 当前轮正确时，下一轮错误的概率 |\n"
        markdown_content += (
            f"| 错误传播样本数 | {epr_stats['error_transitions']} | 统计样本数 |\n"
        )
        markdown_content += "\n> EPR > 1 表示错误会引发连锁反应，值越大风险越高\n\n"

    # ========== 记忆召回分析 ==========
    if memory_recall_stats and memory_recall_stats.get("total_reference_turns", 0) > 0:
        markdown_content += "## 🧠 记忆召回分析\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += (
            f"| 回问总轮次数 | {memory_recall_stats['total_reference_turns']} |\n"
        )
        markdown_content += (
            f"| 正确处理的回问数 | {memory_recall_stats['correct_reference_turns']} |\n"
        )
        markdown_content += (
            f"| **记忆召回率** | **{memory_recall_stats['memory_recall_rate']}%** |\n"
        )
        markdown_content += (
            f"| 回问平均得分 | {memory_recall_stats['avg_reference_score']} |\n"
        )
        markdown_content += (
            f"| 平均上下文连贯性 | {memory_recall_stats['avg_context_coherence']} |\n"
        )
        markdown_content += (
            f"\n> **评估结论**: {memory_recall_stats['interpretation']}\n\n"
        )

    # ========== 用户画像构建准确率统计 ==========
    if persona_profile_stats and persona_profile_stats.get("total", 0) > 0:
        markdown_content += "## 👤 用户画像构建准确率统计\n\n"
        markdown_content += (
            "> **评估内容**: Bot从用户对话中提取和构建用户画像的准确率\n\n"
        )
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 测试总数 | {persona_profile_stats['total']} |\n"
        markdown_content += f"| 通过数 | {persona_profile_stats['passed']} |\n"
        markdown_content += f"| 失败数 | {persona_profile_stats['failed']} |\n"
        markdown_content += (
            f"| **通过率** | **{persona_profile_stats['pass_rate']}%** |\n"
        )
        markdown_content += (
            f"| **平均综合得分** | **{persona_profile_stats['avg_overall_score']}** |\n"
        )
        markdown_content += "\n"

        # 画像构建指标
        markdown_content += "### 画像构建指标\n\n"
        markdown_content += f"| 指标 | 数值 | 说明 |\n"
        markdown_content += f"|------|------|------|\n"
        markdown_content += f"| 字段召回率 | {persona_profile_stats['avg_field_recall']:.2%} | Bot提取了多少期望信息 |\n"
        markdown_content += f"| 字段精确率 | {persona_profile_stats['avg_field_precision']:.2%} | Bot提取的信息有多少是正确的 |\n"
        markdown_content += f"| 值准确率 | {persona_profile_stats['avg_value_accuracy']:.2%} | 提取值的准确程度 |\n"
        markdown_content += "\n"

        # 等级分布
        grade_dist = persona_profile_stats.get("grade_distribution", {})
        if grade_dist:
            markdown_content += "### 等级分布\n\n"
            markdown_content += f"| 等级 | 数量 | 说明 |\n"
            markdown_content += f"|------|------|------|\n"
            markdown_content += f"| 优秀 (≥90) | {grade_dist.get('excellent', 0)} | 画像构建非常准确 |\n"
            markdown_content += (
                f"| 良好 (≥80) | {grade_dist.get('good', 0)} | 画像构建较为准确 |\n"
            )
            markdown_content += (
                f"| 合格 (≥60) | {grade_dist.get('pass', 0)} | 画像构建基本合格 |\n"
            )
            markdown_content += (
                f"| 不合格 (<60) | {grade_dist.get('fail', 0)} | 画像构建需要改进 |\n"
            )
            markdown_content += "\n"

        # 字段级统计
        field_stats = persona_profile_stats.get("field_stats", {})
        if field_stats:
            markdown_content += "### 字段级统计\n\n"
            markdown_content += f"| 字段 | 准确率 | 平均得分 | 最常见匹配类型 |\n"
            markdown_content += f"|------|--------|----------|----------------|\n"
            for field_name, stats in field_stats.items():
                markdown_content += f"| {field_name} | {stats.get('accuracy_rate', 0):.2%} | {stats.get('avg_score', 0)} | {stats.get('most_common_type', '-')} |\n"
            markdown_content += "\n"

    # ========== 单独统计：人设贴合度准确率 ==========
    if persona_accuracy_stats:
        markdown_content += "## 🎭 人设贴合度准确率（单独统计）\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 评估总数 | {persona_accuracy_stats['total']} |\n"
        markdown_content += f"| 人设贴合通过(>=80分) | {persona_accuracy_stats['persona_pass_count']} |\n"
        markdown_content += (
            f"| 人设贴合未通过 | {persona_accuracy_stats['persona_fail_count']} |\n"
        )
        markdown_content += f"| **人设贴合准确率** | **{persona_accuracy_stats['persona_accuracy_rate']}%** |\n"
        markdown_content += (
            f"| 平均人设得分 | {persona_accuracy_stats['avg_persona_score']}分 |\n"
        )
        markdown_content += "\n"

        # 人设得分分布
        markdown_content += "### 人设得分分布\n\n"
        markdown_content += f"| 分档 | 数量 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += (
            f"| 高分(>=90) | {persona_accuracy_stats['high_persona_count']}个 |\n"
        )
        markdown_content += (
            f"| 中分(70-89) | {persona_accuracy_stats['medium_persona_count']}个 |\n"
        )
        markdown_content += (
            f"| 低分(<70) | {persona_accuracy_stats['low_persona_count']}个 |\n"
        )
        markdown_content += "\n"

    # ========== 商品库评估统计 ==========
    if product_catalog_stats and product_catalog_stats.get("total", 0) > 0:
        markdown_content += "## 🛒 商品库评估统计\n\n"
        markdown_content += "> **评估内容**: Bot 对商品价格、商品信息、图片识别、商品编码的回答准确率\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 商品相关问题数 | {product_catalog_stats['total']} |\n"
        markdown_content += f"| 图片问题数 | {product_catalog_stats['image_questions']} |\n"
        markdown_content += f"| **价格准确率** | **{product_catalog_stats['price_accuracy_rate']}%** |\n"
        markdown_content += f"| **信息完整度** | **{product_catalog_stats['info_completeness_rate']}%** |\n"
        markdown_content += f"| **图片识别率** | **{product_catalog_stats['image_recognition_rate']}%** |\n"
        markdown_content += f"| **编码匹配率** | **{product_catalog_stats['code_match_rate']}%** |\n"
        markdown_content += "\n"

        # 详细统计
        markdown_content += "### 详细统计\n\n"
        markdown_content += f"| 指标 | 正确数 | 总数 | 准确率 |\n"
        markdown_content += f"|------|--------|------|--------|\n"
        markdown_content += f"| 价格问题 | {product_catalog_stats['price_correct']} | {product_catalog_stats['total']} | {product_catalog_stats['price_accuracy_rate']}% |\n"
        markdown_content += f"| 信息问题 | {product_catalog_stats['info_complete']} | {product_catalog_stats['total']} | {product_catalog_stats['info_completeness_rate']}% |\n"
        markdown_content += f"| 图片问题 | {product_catalog_stats['image_recognized']} | {product_catalog_stats['image_questions']} | {product_catalog_stats['image_recognition_rate']}% |\n"
        markdown_content += f"| 编码问题 | {product_catalog_stats['code_matched']} | {product_catalog_stats['total']} | {product_catalog_stats['code_match_rate']}% |\n"
        markdown_content += "\n"

    # 拟人化评估统计
    if human_like_stats:
        markdown_content += "## 拟人化评估统计\n\n"
        markdown_content += f"| 指标 | 数值 |\n"
        markdown_content += f"|------|------|\n"
        markdown_content += f"| 评估总数 | {human_like_stats['total']} |\n"
        markdown_content += f"| 通过数(>=70分) | {human_like_stats['pass_count']} |\n"
        markdown_content += f"| 未通过数 | {human_like_stats['fail_count']} |\n"
        markdown_content += f"| **通过率** | **{human_like_stats['pass_rate']}%** |\n"
        markdown_content += f"| 平均总分 | {human_like_stats['avg_score']}分 |\n"
        markdown_content += "\n"

        # 各维度评分
        markdown_content += "### 各维度评分\n\n"
        markdown_content += f"| 维度 | 平均分 | 权重 |\n"
        markdown_content += f"|------|--------|------|\n"
        markdown_content += (
            f"| 格式与排版 | {human_like_stats['avg_format_score']}分 | 30% |\n"
        )
        markdown_content += (
            f"| 语气自然度 | {human_like_stats['avg_tone_score']}分 | 30% |\n"
        )
        markdown_content += (
            f"| 人设贴合度 | {human_like_stats['avg_persona_score']}分 | 20% |\n"
        )
        markdown_content += (
            f"| 回复节奏 | {human_like_stats['avg_rhythm_score']}分 | 20% |\n"
        )
        markdown_content += "\n"

    # 测试结果详情
    markdown_content += "## 测试结果详情\n\n"
    for i, result in enumerate(results, 1):
        markdown_content += f"### 测试 {i}\n\n"
        markdown_content += f"**Q: {result['question']}**\n\n"
        if result["success"]:
            markdown_content += f"**A:** {result['answer']}\n\n"
            markdown_content += f"- 响应时间: {result['response_time']}秒\n"
            # 首字出现时间
            first_token = result.get("first_token_time", 0)
            if first_token > 0:
                markdown_content += f"- 首字时间: {first_token}秒\n"

            # 多裁判模型评估结果
            judge = result.get("judge_result")
            if judge:
                score = judge.get("score", 0)
                is_correct = judge.get("is_correct", False)
                consensus_rate = judge.get("consensus_rate", 0)
                status = "✅ 正确" if is_correct else "❌ 错误"
                markdown_content += f"\n**综合评估: {score}分 ({status})** - 共识率: {consensus_rate * 100:.0f}%\n\n"

                # 各裁判模型详情
                judges = judge.get("judges", [])
                if judges:
                    markdown_content += (
                        "<details>\n<summary>📋 各裁判模型评估详情</summary>\n\n"
                    )
                    markdown_content += f"| 裁判模型 | 判断 | 分数 | 评估理由 |\n"
                    markdown_content += f"|----------|------|------|----------|\n"

                    # 获取当前问题的轮次索引（用于多轮对话）
                    # 注意：turn_index 从 1 开始，0 表示未设置
                    # 如果 result 中没有 turn_index，使用问题序号 i 作为 turn_index
                    current_turn_index = result.get("turn_index", 0)

                    for j in judges:
                        # 兼容单轮和多轮两种格式
                        # 单轮格式: is_correct, score, reason
                        # 多轮格式: is_group_correct, group_score, group_reason, turns_evaluation
                        is_correct = j.get("is_correct", None)
                        score = j.get("score", None)
                        reason = j.get("reason", "")

                        # 如果是单轮格式字段不存在，尝试从多轮格式提取
                        if is_correct is None or score is None:
                            # 尝试从 turns_evaluation 中提取当前轮次的评估结果
                            turns_eval = j.get("turns_evaluation", [])
                            if turns_eval:
                                turn_eval = None
                                if current_turn_index > 0:
                                    # 按 turn_index 匹配
                                    for te in turns_eval:
                                        if te.get("turn_index") == current_turn_index:
                                            turn_eval = te
                                            break
                                # 如果没有 turn_index 或匹配失败，取第一轮
                                if turn_eval is None:
                                    turn_eval = turns_eval[0]

                                is_correct = turn_eval.get("is_correct", False)
                                score = turn_eval.get("score", 0)
                                reason = turn_eval.get("reason", "")

                            # 如果还是没有，使用整组评估结果
                            if is_correct is None:
                                is_correct = j.get("is_group_correct", False)
                            if score is None:
                                score = j.get("group_score", 0)
                            if not reason:
                                reason = j.get("group_reason", "")

                        j_status = "✅" if is_correct else "❌"
                        reason_text = str(reason)[:50] if reason else ""
                        markdown_content += f"| {j.get('display_name', j.get('model_name', 'Unknown'))} | {j_status} | {score}分 | {reason_text} |\n"
                    markdown_content += "\n"

                    # 各模型的答案
                    markdown_content += "**各裁判模型给出的答案:**\n\n"
                    for j in judges:
                        # 兼容单轮和多轮格式
                        model_answer = j.get("model_answer", "")
                        # 多轮格式中，model_answer 可能在 turns_evaluation 里
                        if not model_answer:
                            turns_eval = j.get("turns_evaluation", [])
                            if turns_eval:
                                turn_eval = None
                                if current_turn_index > 0:
                                    # 按 turn_index 匹配
                                    for te in turns_eval:
                                        if te.get("turn_index") == current_turn_index:
                                            turn_eval = te
                                            break
                                # 如果没有匹配到，取第一轮
                                if turn_eval is None:
                                    turn_eval = turns_eval[0]
                                model_answer = (
                                    turn_eval.get("model_answer", "")
                                    if turn_eval
                                    else ""
                                )
                        if model_answer:
                            markdown_content += f"- **{j.get('display_name', j.get('model_name', 'Unknown'))}**: {model_answer[:200]}{'...' if len(model_answer) > 200 else ''}\n"
                    markdown_content += "\n"

                    markdown_content += "</details>\n\n"

            # 拟人化评估结果
            hl_result = result.get("human_like_result")
            if hl_result:
                hl_score = hl_result.get("total_score", 0)
                hl_pass = hl_result.get("is_human_like", False)
                hl_status = "✅ 通过" if hl_pass else "❌ 未通过"
                markdown_content += f"\n**拟人化评估: {hl_score}分 ({hl_status})**\n\n"

                # 各维度分数
                markdown_content += (
                    "<details>\n<summary>🎭 拟人化各维度评分</summary>\n\n"
                )
                markdown_content += f"| 维度 | 分数 | 扣分原因 |\n"
                markdown_content += f"|------|------|----------|\n"

                format_score = hl_result.get("format_score", {})
                format_reasons = (
                    "; ".join(format_score.get("deduction_reasons", [])) or "无"
                )
                markdown_content += f"| 格式与排版 | {format_score.get('score', 0)}分 | {format_reasons[:50]} |\n"

                tone_score = hl_result.get("tone_score", {})
                tone_reasons = (
                    "; ".join(tone_score.get("deduction_reasons", [])) or "无"
                )
                markdown_content += f"| 语气自然度 | {tone_score.get('score', 0)}分 | {tone_reasons[:50]} |\n"

                persona_score = hl_result.get("persona_score", {})
                persona_reasons = (
                    "; ".join(persona_score.get("deduction_reasons", [])) or "无"
                )
                markdown_content += f"| 人设贴合度 | {persona_score.get('score', 0)}分 | {persona_reasons[:50]} |\n"

                rhythm_score = hl_result.get("rhythm_score", {})
                rhythm_reasons = (
                    "; ".join(rhythm_score.get("deduction_reasons", [])) or "无"
                )
                markdown_content += f"| 回复节奏 | {rhythm_score.get('score', 0)}分 | {rhythm_reasons[:50]} |\n"

                markdown_content += "\n"

                # 改进建议
                suggestions = hl_result.get("suggestions", [])
                if suggestions:
                    markdown_content += "**改进建议:**\n"
                    for s in suggestions:
                        markdown_content += f"- {s}\n"
                    markdown_content += "\n"

                markdown_content += "</details>\n\n"

            markdown_content += "\n"
        else:
            markdown_content += f"**A:** ❌ 未获取到回答\n\n"

    # 计算首字时间统计
    first_token_times = [
        r.get("first_token_time", 0)
        for r in results
        if r["success"] and r.get("first_token_time", 0) > 0
    ]
    avg_first_token = (
        sum(first_token_times) / len(first_token_times) if first_token_times else 0
    )

    # 总结
    markdown_content += "## 总结\n\n"
    markdown_content += f"| 指标 | 数值 |\n"
    markdown_content += f"|------|------|\n"
    markdown_content += f"| 平均耗时 | {round(avg_response_time, 2)}秒 |\n"
    if avg_first_token > 0:
        markdown_content += f"| 平均首字时间 | {round(avg_first_token, 2)}秒 |\n"
    markdown_content += f"| 回复率 | {success_rate}% |\n"
    markdown_content += f"| 总测试数 | {total} |\n"
    markdown_content += f"| 成功数 | {success} |\n"
    markdown_content += f"| 失败数 | {failed} |\n"
    if accuracy_stats:
        markdown_content += f"| **精确率** | **{accuracy_stats['accuracy_rate']}%** |\n"
    if human_like_stats:
        markdown_content += (
            f"| **拟人化通过率** | **{human_like_stats['pass_rate']}%** |\n"
        )
        markdown_content += f"| 拟人化平均分 | {human_like_stats['avg_score']}分 |\n"
    if is_multi_turn and context_stats:
        markdown_content += (
            f"| **上下文成功率** | **{context_stats['context_success_rate']}%** |\n"
        )
        markdown_content += (
            f"| **极限轮次** | **第{context_stats['limit_turn']}轮** |\n"
        )

    # 保存Markdown文件
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"[OK] Markdown报告已保存: {filepath}")
