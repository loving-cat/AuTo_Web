# -*- coding: utf-8 -*-
"""
拟人化评估模块 - "去AI化"定量评分
检测格式检查、语气自然度、人设贴合度、回复节奏
"""
import os
import re
import json
import requests
from typing import TypedDict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 加载环境变量
try:
    from dotenv import load_dotenv
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    env_path = os.path.join(_project_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
except ImportError:
    pass

# API 配置
# [CLEARED] 从环境变量读取API配置
HUMAN_LIKE_API_KEY = os.getenv("HUMAN_LIKE_API_KEY", "")
HUMAN_LIKE_API_BASE_URL = os.getenv("HUMAN_LIKE_API_BASE_URL", "")


class HumanLikeScore(TypedDict):
    """拟人化评分单项"""
    score: int               # 0-100 分
    max_score: int           # 满分
    deduction_reasons: list[str]  # 扣分原因


class HumanLikeResult(TypedDict):
    """拟人化评估结果"""
    total_score: int         # 总分 0-100
    format_score: HumanLikeScore      # 格式与排版 (30%)
    tone_score: HumanLikeScore        # 语气自然度 (30%)
    persona_score: HumanLikeScore     # 人设贴合度 (20%)
    rhythm_score: HumanLikeScore      # 回复节奏 (20%)
    is_human_like: bool      # 是否通过拟人化测试（总分>=70）
    suggestions: list[str]   # 改进建议


# AI 味检测关键词
AI_KEYWORDS = [
    "作为AI语言模型",
    "作为人工智能",
    "我无法回答",
    "我无法提供",
    "我是一个AI",
    "我是AI助手",
    "作为助手",
    "根据我的训练",
    "我没有个人观点",
    "我无法表达个人",
    "作为语言模型",
    "很抱歉，我无法",
    "抱歉，作为",
]

# Markdown 格式检测模式
MARKDOWN_PATTERNS = [
    r'```[\s\S]*?```',      # 代码块
    r'`[^`]+`',              # 行内代码
    r'#{1,6}\s',             # 标题
    r'\*\*[^*]+\*\*',        # 粗体
    r'\*[^*]+\*',            # 斜体
    r'^\s*[-*+]\s',          # 无序列表
    r'^\s*\d+\.\s',          # 有序列表
    r'\[[^\]]+\]\([^)]+\)',  # 链接
    r'^\s*>\s',              # 引用
]

# 机械回复模式
MECHANICAL_PATTERNS = [
    r'亲亲?，?您好',
    r'亲，?有什么可以帮您',
    r'感谢您的咨询',
    r'很高兴为您服务',
    r'请问还有什么可以帮您',
    r'如有其他问题',
]


def detect_markdown(text: str) -> tuple[bool, list[str]]:
    """
    检测文本中是否包含 Markdown 格式
    
    Args:
        text: 待检测文本
        
    Returns:
        (是否包含Markdown, 检测到的模式列表)
    """
    detected = []
    for pattern in MARKDOWN_PATTERNS:
        matches = re.findall(pattern, text, re.MULTILINE)
        if matches:
            detected.extend(matches[:3])  # 最多记录3个
    
    return len(detected) > 0, detected


def detect_ai_keywords(text: str) -> tuple[bool, list[str]]:
    """
    检测文本中是否包含 AI 味关键词
    
    Args:
        text: 待检测文本
        
    Returns:
        (是否包含AI关键词, 检测到的关键词列表)
    """
    detected = []
    for keyword in AI_KEYWORDS:
        if keyword in text:
            detected.append(keyword)
    
    return len(detected) > 0, detected


def detect_mechanical_tone(text: str) -> tuple[bool, list[str]]:
    """
    检测机械回复模式
    
    Args:
        text: 待检测文本
        
    Returns:
        (是否包含机械模式, 检测到的模式列表)
    """
    detected = []
    for pattern in MECHANICAL_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            detected.extend(matches[:3])
    
    return len(detected) > 0, detected


def evaluate_format(response: str) -> HumanLikeScore:
    """
    评估格式与排版
    
    满分：纯文本/表情，短句为主
    扣分：Markdown、代码块、大段文字
    """
    score = 100
    deduction_reasons = []
    
    # 检测 Markdown
    has_markdown, markdown_items = detect_markdown(response)
    if has_markdown:
        score -= 30
        deduction_reasons.append(f"包含 Markdown 格式: {markdown_items[0][:30]}...")
    
    # 检测代码块
    if '```' in response:
        score -= 20
        deduction_reasons.append("包含代码块")
    
    # 检测过长段落
    paragraphs = response.split('\n\n')
    for p in paragraphs:
        if len(p) > 150:
            score -= 10
            deduction_reasons.append(f"存在过长段落 ({len(p)} 字)")
            break
    
    # 检测列表格式
    if re.search(r'^\s*[-*+]\s', response, re.MULTILINE):
        score -= 5
        deduction_reasons.append("包含列表格式")
    
    return HumanLikeScore(
        score=max(0, score),
        max_score=100,
        deduction_reasons=deduction_reasons
    )


def evaluate_tone(response: str) -> HumanLikeScore:
    """
    评估语气自然度
    
    满分：口语化，有情感波动
    扣分：机械、重复、过度礼貌
    """
    score = 100
    deduction_reasons = []
    
    # 检测 AI 关键词
    has_ai, ai_keywords = detect_ai_keywords(response)
    if has_ai:
        score -= 30
        deduction_reasons.append(f"包含 AI 味关键词: {ai_keywords[0]}")
    
    # 检测机械模式
    has_mechanical, mechanical = detect_mechanical_tone(response)
    if has_mechanical:
        score -= 15
        deduction_reasons.append(f"包含机械回复模式: {mechanical[0]}")
    
    # 检测过度礼貌
    polite_count = response.count("请") + response.count("您") + response.count("感谢")
    if polite_count > 5:
        score -= 10
        deduction_reasons.append(f"过度礼貌 (出现{polite_count}次)")
    
    # 检测重复内容
    words = response.split()
    if len(words) > 3:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.5:
            score -= 10
            deduction_reasons.append("内容重复较多")
    
    return HumanLikeScore(
        score=max(0, score),
        max_score=100,
        deduction_reasons=deduction_reasons
    )


def evaluate_persona(response: str, persona_config: dict | None = None) -> HumanLikeScore:
    """
    评估人设贴合度
    
    Args:
        response: 回复内容
        persona_config: 人设配置（如 {"style": "傲娇二次元", "traits": ["毒舌", "可爱"]}）
        
    Returns:
        HumanLikeScore
    """
    score = 100
    deduction_reasons = []
    
    # 默认人设检查
    if persona_config:
        style = persona_config.get("style", "")
        traits = persona_config.get("traits", [])
        
        # 检查是否 OOC (Out of Character)
        if "傲娇" in style or "毒舌" in traits:
            # 检测是否出现不符合人设的礼貌用语
            if "亲亲您好" in response or "很高兴为您服务" in response:
                score -= 20
                deduction_reasons.append("人设不一致：傲娇风格不应使用过度礼貌用语")
        
        if "可爱" in traits or "软萌" in style:
            # 检测是否过于正式
            if "根据" in response or "综上所述" in response:
                score -= 15
                deduction_reasons.append("人设不一致：软萌风格不应使用正式用语")
    else:
        # 无特定人设时，检查是否过于机械
        if "作为" in response[:20] or "我是" in response[:20]:
            score -= 10
            deduction_reasons.append("开头过于正式")
    
    # 检测表情使用（加分项，这里只做不扣分处理）
    emoji_pattern = re.compile("["
        u"\U0001F600-\U0001F64F"  # emoticons
        u"\U0001F300-\U0001F5FF"  # symbols & pictographs
        u"\U0001F680-\U0001F6FF"  # transport & map symbols
        u"\U0001F1E0-\U0001F1FF"  # flags
        u"\U00002702-\U000027B0"
        u"\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    
    # 检测口语化连接词
    colloquial_words = ["嗯", "啊", "呢", "吧", "嘛", "哦", "呀", "哈"]
    has_colloquial = any(word in response for word in colloquial_words)
    if not has_colloquial and len(response) > 20:
        score -= 5
        deduction_reasons.append("缺少口语化表达")
    
    return HumanLikeScore(
        score=max(0, score),
        max_score=100,
        deduction_reasons=deduction_reasons
    )


def evaluate_rhythm(response: str, latency_ms: float | None = None) -> HumanLikeScore:
    """
    评估回复节奏
    
    Args:
        response: 回复内容
        latency_ms: 响应延迟（毫秒）
        
    Returns:
        HumanLikeScore
    """
    score = 100
    deduction_reasons = []
    
    # 计算期望响应时间（200ms/字）
    expected_time = len(response) * 200
    
    if latency_ms is not None:
        # 检测秒回
        if latency_ms < expected_time * 0.1:
            score -= 20
            deduction_reasons.append(f"响应过快 ({latency_ms:.0f}ms)，疑似秒回")
        
        # 检测过慢
        if latency_ms > 10000:  # 超过10秒
            score -= 10
            deduction_reasons.append(f"响应过慢 ({latency_ms:.0f}ms)")
    else:
        # 无延迟数据时，根据内容长度判断
        if len(response) > 100:
            deduction_reasons.append("长文本建议拆分发送")
    
    # 检测是否需要拆分消息
    if len(response) > 100:
        score -= 5
        deduction_reasons.append(f"单条消息过长 ({len(response)} 字)，建议拆分")
    
    return HumanLikeScore(
        score=max(0, score),
        max_score=100,
        deduction_reasons=deduction_reasons
    )


def evaluate_human_like(
    response: str,
    latency_ms: float | None = None,
    persona_config: dict | None = None
) -> HumanLikeResult:
    """
    综合评估拟人化程度
    
    Args:
        response: Agent 回复
        latency_ms: 响应延迟（毫秒）
        persona_config: 人设配置
        
    Returns:
        HumanLikeResult
    """
    # 各维度评分
    format_score = evaluate_format(response)
    tone_score = evaluate_tone(response)
    persona_score = evaluate_persona(response, persona_config)
    rhythm_score = evaluate_rhythm(response, latency_ms)
    
    # 加权计算总分
    total_score = (
        format_score["score"] * 0.30 +
        tone_score["score"] * 0.30 +
        persona_score["score"] * 0.20 +
        rhythm_score["score"] * 0.20
    )
    
    # 收集改进建议
    suggestions = []
    for name, score_result in [
        ("格式", format_score),
        ("语气", tone_score),
        ("人设", persona_score),
        ("节奏", rhythm_score)
    ]:
        if score_result["deduction_reasons"]:
            suggestions.append(f"【{name}】" + "; ".join(score_result["deduction_reasons"]))
    
    return HumanLikeResult(
        total_score=round(total_score),
        format_score=format_score,
        tone_score=tone_score,
        persona_score=persona_score,
        rhythm_score=rhythm_score,
        is_human_like=total_score >= 70,
        suggestions=suggestions
    )


def evaluate_human_like_with_llm(
    response: str,
    persona_config: dict | None = None,
    model_name: str = "qwen3.5-plus"
) -> HumanLikeResult:
    """
    使用 LLM 进行更智能的拟人化评估
    
    Args:
        response: Agent 回复
        persona_config: 人设配置
        model_name: 使用的模型名称
        
    Returns:
        HumanLikeResult
    """
    # 先进行规则评估
    rule_result = evaluate_human_like(response, None, persona_config)
    
    if not HUMAN_LIKE_API_KEY:
        return rule_result
    
    # 构建 LLM 评估提示
    persona_desc = ""
    if persona_config:
        persona_desc = f"人设风格: {persona_config.get('style', '未指定')}\n人设特点: {', '.join(persona_config.get('traits', []))}"
    
    prompt = f"""你是一个专业的AI拟人化评估专家。请评估以下客服回复的拟人化程度。

【客服回复】
{response}

{f'【预设人设】{persona_desc}' if persona_desc else ''}

请从以下四个维度评分（每个维度0-100分）：
1. 格式与排版：是否避免了Markdown、代码块、大段文字
2. 语气自然度：是否口语化、有情感、避免机械回复
3. 人设贴合度：是否符合预设人设（如有）
4. 回复节奏：是否像真人打字（需要结合实际延迟判断，这里只评内容）

请严格按照以下JSON格式输出：
{{
    "format_score": 分数,
    "tone_score": 分数,
    "persona_score": 分数,
    "rhythm_score": 分数,
    "is_human_like": true或false,
    "suggestions": ["建议1", "建议2"]
}}

只输出JSON，不要其他内容！"""

    try:
        headers = {
            "Authorization": f"Bearer {HUMAN_LIKE_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500
        }
        
        resp = requests.post(
            f"{HUMAN_LIKE_API_BASE_URL}/chat/completions",
            json=payload,
            headers=headers,
            timeout=60
        )
        resp.raise_for_status()
        
        content = resp.json()['choices'][0]['message']['content'].strip()
        
        # 解析 JSON
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            llm_result = json.loads(content[json_start:json_end])
            
            return HumanLikeResult(
                total_score=round((
                    llm_result.get("format_score", 70) * 0.30 +
                    llm_result.get("tone_score", 70) * 0.30 +
                    llm_result.get("persona_score", 70) * 0.20 +
                    llm_result.get("rhythm_score", 70) * 0.20
                )),
                format_score=HumanLikeScore(
                    score=llm_result.get("format_score", 70),
                    max_score=100,
                    deduction_reasons=[]
                ),
                tone_score=HumanLikeScore(
                    score=llm_result.get("tone_score", 70),
                    max_score=100,
                    deduction_reasons=[]
                ),
                persona_score=HumanLikeScore(
                    score=llm_result.get("persona_score", 70),
                    max_score=100,
                    deduction_reasons=[]
                ),
                rhythm_score=HumanLikeScore(
                    score=llm_result.get("rhythm_score", 70),
                    max_score=100,
                    deduction_reasons=[]
                ),
                is_human_like=llm_result.get("is_human_like", False),
                suggestions=llm_result.get("suggestions", [])
            )
    except Exception as e:
        print(f"[HumanLike] LLM 评估失败: {e}")
    
    return rule_result


def batch_evaluate_human_like(
    responses: list[str],
    persona_config: dict | None = None,
    use_llm: bool = False,
    max_workers: int = 3
) -> list[HumanLikeResult]:
    """
    批量评估拟人化程度
    
    Args:
        responses: 回复列表
        persona_config: 人设配置
        use_llm: 是否使用 LLM 评估
        max_workers: 并发数
        
    Returns:
        评估结果列表
    """
    results = []
    
    def evaluate_single(response: str) -> HumanLikeResult:
        if use_llm:
            return evaluate_human_like_with_llm(response, persona_config)
        return evaluate_human_like(response, None, persona_config)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(evaluate_single, r): i for i, r in enumerate(responses)}
        
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                results.append((idx, result))
            except Exception as e:
                print(f"[HumanLike] 评估 {idx} 失败: {e}")
                results.append((idx, HumanLikeResult(
                    total_score=0,
                    format_score=HumanLikeScore(score=0, max_score=100, deduction_reasons=["评估失败"]),
                    tone_score=HumanLikeScore(score=0, max_score=100, deduction_reasons=["评估失败"]),
                    persona_score=HumanLikeScore(score=0, max_score=100, deduction_reasons=["评估失败"]),
                    rhythm_score=HumanLikeScore(score=0, max_score=100, deduction_reasons=["评估失败"]),
                    is_human_like=False,
                    suggestions=[str(e)]
                )))
    
    # 按原始顺序排序
    results.sort(key=lambda x: x[0])
    return [r for _, r in results]


def generate_human_like_report(results: list[HumanLikeResult]) -> dict:
    """
    生成拟人化评估报告
    
    Args:
        results: 评估结果列表
        
    Returns:
        报告字典
    """
    total = len(results)
    if total == 0:
        return {"total": 0, "pass_rate": 0, "avg_score": 0}
    
    passed = sum(1 for r in results if r["is_human_like"])
    avg_score = sum(r["total_score"] for r in results) / total
    
    avg_format = sum(r["format_score"]["score"] for r in results) / total
    avg_tone = sum(r["tone_score"]["score"] for r in results) / total
    avg_persona = sum(r["persona_score"]["score"] for r in results) / total
    avg_rhythm = sum(r["rhythm_score"]["score"] for r in results) / total
    
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 2),
        "avg_score": round(avg_score, 2),
        "dimension_avg": {
            "format": round(avg_format, 2),
            "tone": round(avg_tone, 2),
            "persona": round(avg_persona, 2),
            "rhythm": round(avg_rhythm, 2)
        }
    }


if __name__ == "__main__":
    # 测试代码
    test_responses = [
        "亲，您好！很高兴为您服务，请问有什么可以帮您的吗？",
        "嗯，这款确实挺不错的~性价比很高呢！你预算多少呀？",
        "```python\nprint('Hello')\n```\n这是代码示例",
        "作为AI语言模型，我无法回答这个问题。",
        "哈哈这个我也觉得超好用！用了半年了完全没毛病~"
    ]
    
    print("=" * 60)
    print("拟人化评估测试")
    print("=" * 60)
    
    for i, resp in enumerate(test_responses, 1):
        print(f"\n【测试 {i}】{resp[:50]}...")
        result = evaluate_human_like(resp)
        print(f"总分: {result['total_score']} ({'通过' if result['is_human_like'] else '不通过'})")
        print(f"格式: {result['format_score']['score']} | 语气: {result['tone_score']['score']}")
        print(f"人设: {result['persona_score']['score']} | 节奏: {result['rhythm_score']['score']}")
        if result['suggestions']:
            print(f"建议: {'; '.join(result['suggestions'])}")
