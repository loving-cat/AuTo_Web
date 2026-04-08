"""
统一类型定义模块

集中管理所有TypedDict、Enum等类型定义，避免重复定义。
"""

from enum import Enum
from typing import TypedDict, List, Dict, Any, Optional


# ============== 混沌矩阵类型 ==============

class TypedQuestion(TypedDict):
    """带类型的问句"""
    question: str              # 问句内容
    question_type: str         # 类型: normal/boundary/abnormal/inductive
    expected_behavior: str     # 期望行为描述
    group_index: int           # 多轮对话分组索引（单轮为0）


class ChaosMatrixResult(TypedDict):
    """混沌矩阵统计结果"""
    TP: int                    # True Positive: 有效问题，正确回答
    TN: int                    # True Negative: 异常问题，正确拒绝
    FP: int                    # False Positive: 诱导问题，错误接受
    FN: int                    # False Negative: 有效问题，错误拒绝
    total: int                 # 总数
    accuracy: float            # 准确率 (TP+TN)/(TP+TN+FP+FN)
    precision: float           # 精确率 TP/(TP+FP)
    recall: float              # 召回率 TP/(TP+FN)
    f1_score: float            # F1分数
    type_breakdown: Dict       # 各类型的详细统计


class MemoryEvaluationResult(TypedDict):
    """记忆评估结果"""
    memory_recall_rate: float      # 记忆召回率：正确回答的回问问题比例
    context_coherence: float       # 上下文连贯性：对话上下文保持一致的比例
    error_propagation_rate: float  # 错误传播率：前序错误导致后续错误的比例
    total_callback_questions: int  # 回问问题总数
    correct_callback_answers: int  # 正确回答的回问数量
    total_context_checks: int      # 上下文检查总数
    coherent_contexts: int         # 连贯的上下文数量


# ============== 裁判评估类型 ==============

class JudgeResult(TypedDict):
    """单个裁判模型的评估结果"""
    model_name: str            # 模型名称
    display_name: str          # 模型显示名称
    is_correct: bool           # 回答是否正确
    score: int                 # 0-100 分
    reason: str                # 评估理由
    knowledge_relevance: str   # 与知识库相关的关键信息
    model_answer: str          # 模型自己给出的答案
    thinking: str              # 思考过程


class ProfileFieldResult(TypedDict):
    """画像字段评估结果"""
    field_name: str
    expected_value: Any
    actual_value: Any
    match_type: str            # exact/partial/semantic/no_match/wrong
    score: float
    reason: str


class ProfileJudgeResult(TypedDict):
    """单个裁判的画像评估结果"""
    model_name: str
    display_name: str
    field_results: List[ProfileFieldResult]
    field_recall: float
    field_precision: float
    value_accuracy: float
    overall_score: float
    is_pass: bool
    reason: str
    thinking: str
    judge_profile: dict        # 裁判模型提取的画像
    bot_profile: dict          # Bot返回的画像


class MultiProfileJudgeResult(TypedDict):
    """多裁判综合画像评估结果"""
    field_recall: float
    field_precision: float
    value_accuracy: float
    overall_score: float
    is_pass: bool
    grade: str
    reason: str
    judges: List[ProfileJudgeResult]
    consensus_rate: float
    field_stats: dict


class MultiJudgeResult(TypedDict):
    """多裁判模型综合评估结果"""
    is_correct: bool           # 综合判断（多数投票）
    score: int                 # 平均分数
    reason: str                # 综合理由
    knowledge_relevance: str   # 综合知识库相关性
    judges: List[JudgeResult]  # 各裁判模型的详细结果
    consensus_rate: float      # 共识率（一致判断的比例）


class MultiTurnGroupJudgeResult(TypedDict):
    """多轮对话分组评估结果（整组评估）"""
    group_index: int           # 组索引
    total_turns: int           # 组内轮次数
    is_group_correct: bool     # 整组是否正确
    group_score: int           # 整组得分 0-100
    group_reason: str          # 整组评估理由
    context_coherence: int     # 上下文连贯性得分 0-100
    turns_detail: list         # 每轮详细评估
    judges: list               # 各裁判模型的详细结果
    consensus_rate: float      # 共识率


# ============== 拟人化评估类型 ==============

class HumanLikeScore(TypedDict):
    """拟人化评分单项"""
    score: int                 # 0-100 分
    max_score: int             # 满分
    deduction_reasons: List[str]  # 扣分原因


class HumanLikeResult(TypedDict):
    """拟人化评估结果"""
    total_score: int           # 总分 0-100
    format_score: HumanLikeScore      # 格式与排版 (30%)
    tone_score: HumanLikeScore        # 语气自然度 (30%)
    persona_score: HumanLikeScore     # 人设贴合度 (20%)
    rhythm_score: HumanLikeScore      # 回复节奏 (20%)
    is_human_like: bool        # 是否通过拟人化测试（总分>=70）
    suggestions: List[str]     # 改进建议


# ============== 报告统计类型 ==============

class ResponseTimeStats(TypedDict):
    """响应时间统计"""
    average: float
    min: float
    max: float
    first_token_avg: float     # 首字出现平均时间
    first_token_min: float     # 首字出现最短时间
    first_token_max: float     # 首字出现最长时间
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
    model_stats: Dict
    avg_consensus_rate: float
    group_stats: Dict
    chaos_matrix: Dict
    memory_metrics: Optional[Dict]


class HumanLikeStats(TypedDict):
    """拟人化评估统计"""
    total: int                 # 评估总数
    pass_count: int            # 通过数（>=70分）
    fail_count: int            # 未通过数
    pass_rate: float           # 通过率
    avg_score: float           # 平均总分
    avg_format_score: float    # 平均格式分
    avg_tone_score: float      # 平均语气分
    avg_persona_score: float   # 平均人设分
    avg_rhythm_score: float    # 平均节奏分


class ContextAccuracyStats(TypedDict):
    """多轮对话上下文准确率统计（单独计算）"""
    total_reference_questions: int   # 回问问题总数
    context_success_count: int       # 上下文处理成功数
    context_accuracy_rate: float     # 上下文准确率
    avg_context_score: float         # 平均上下文得分
    reference_turns: List[int]       # 回问轮次列表
    success_by_turn: Dict[int, bool] # 各轮回问成功情况


class PersonaAccuracyStats(TypedDict):
    """人设贴合度准确率统计（单独计算）"""
    total: int                 # 评估总数
    persona_pass_count: int    # 人设贴合通过数（>=80分）
    persona_fail_count: int    # 人设贴合未通过数
    persona_accuracy_rate: float  # 人设贴合准确率
    avg_persona_score: float   # 平均人设得分
    high_persona_count: int    # 高分(>=90)数量
    medium_persona_count: int  # 中分(70-89)数量
    low_persona_count: int     # 低分(<70)数量


class EPRStats(TypedDict):
    """错误传播率统计"""
    epr: float                 # EPR 值
    p_error_after_error: float # 错误后下一轮错误概率
    p_error_after_correct: float  # 正确后下一轮错误概率
    error_transitions: int     # 错误传播统计样本数
    correct_transitions: int   # 正确传播统计样本数
    interpretation: str        # 风险等级解读


class MemoryRecallStats(TypedDict):
    """记忆召回统计"""
    total_reference_turns: int     # 回问总轮次数
    correct_reference_turns: int   # 正确处理的回问数
    memory_recall_rate: float      # 记忆召回率
    avg_reference_score: float     # 回问平均得分
    avg_context_coherence: float   # 平均上下文连贯性
    interpretation: str        # 能力等级解读


class PersonaProfileStats(TypedDict):
    """用户画像构建准确率统计"""
    total: int                 # 测试总数
    passed: int                # 通过数
    failed: int                # 失败数
    pass_rate: float           # 通过率
    avg_field_recall: float    # 平均字段召回率
    avg_field_precision: float # 平均字段精确率
    avg_value_accuracy: float  # 平均值准确率
    avg_overall_score: float   # 平均综合得分
    grade_distribution: Dict   # 等级分布 {excellent, good, pass, fail}
    field_stats: Dict          # 字段级统计


# ============== 测试结果类型 ==============

class TestResult(TypedDict):
    """测试结果"""
    question: str
    answer: str
    response_time: float
    first_token_time: float    # 首字出现时间
    success: bool
    judge_result: Optional[Dict]
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
    human_like_stats: Optional[HumanLikeStats]
    context_stats: Optional[Dict]
    context_accuracy_stats: Optional[ContextAccuracyStats]
    persona_accuracy_stats: Optional[PersonaAccuracyStats]
    epr_stats: Optional[EPRStats]
    memory_recall_stats: Optional[MemoryRecallStats]
    persona_profile_stats: Optional[PersonaProfileStats]
    is_multi_turn: bool
    results: List[TestResult]


# ============== 画像测试类型 ==============

class PersonaTestCase(TypedDict):
    """画像测试用例"""
    test_case_id: str
    user_input: str
    expected_profile: Dict[str, Any]
    complexity: str
    scenario_type: str
    category: Optional[str]
