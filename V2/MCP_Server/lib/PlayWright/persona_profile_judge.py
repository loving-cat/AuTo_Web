# -*- coding: utf-8 -*-
"""
用户画像评估模块

评估 Bot 构建的用户画像与期望画像的匹配程度
"""

import os
import json
import re
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher


def load_rules(rules_path: str | None = None) -> Dict[str, Any]:
    """
    加载评估规则配置
    
    Args:
        rules_path: 规则配置文件路径
    
    Returns:
        规则配置字典
    """
    default_rules = {
        "version": "1.0.0",
        "pass_threshold": 60,
        "grade_thresholds": {
            "excellent": 90,
            "good": 80,
            "pass": 60
        },
        "field_weights": {
            "name": 1.0,
            "phone": 1.0,
            "wechat": 1.0,
            "email": 1.0,
            "address": 0.8,
            "product": 0.9,
            "budget": 0.8,
            "preference": 0.7
        },
        "match_types": {
            "exact": 1.0,      # 完全匹配
            "partial": 0.7,    # 部分匹配
            "semantic": 0.5,   # 语义匹配
            "no_match": 0.0    # 不匹配
        }
    }
    
    if rules_path and os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                custom_rules = json.load(f)
                default_rules.update(custom_rules)
        except Exception as e:
            print(f"[WARN] 加载规则文件失败: {e}，使用默认规则")
    
    return default_rules


def calculate_string_similarity(s1: str, s2: str) -> float:
    """
    计算两个字符串的相似度
    
    Args:
        s1: 字符串1
        s2: 字符串2
    
    Returns:
        相似度 (0-1)
    """
    if not s1 or not s2:
        return 0.0
    
    s1_lower = s1.lower().strip()
    s2_lower = s2.lower().strip()
    
    # 完全匹配
    if s1_lower == s2_lower:
        return 1.0
    
    # 使用 SequenceMatcher 计算相似度
    return SequenceMatcher(None, s1_lower, s2_lower).ratio()


def match_field_value(
    expected: Any,
    actual: Any,
    field_name: str,
    rules: Dict[str, Any]
) -> Tuple[str, float, str]:
    """
    匹配字段值
    
    Args:
        expected: 期望值
        actual: 实际值
        field_name: 字段名
        rules: 规则配置
    
    Returns:
        (match_type, score, reason)
    """
    if expected is None or expected == "":
        if actual is None or actual == "":
            return "exact", 1.0, "两者都为空"
        return "partial", 0.5, "期望为空，实际有值"
    
    if actual is None or actual == "":
        return "no_match", 0.0, "实际值为空"
    
    # 类型转换
    expected_str = str(expected)
    actual_str = str(actual)
    
    # 完全匹配
    if expected_str == actual_str:
        return "exact", 1.0, "完全匹配"
    
    # 数值比较
    try:
        expected_num = float(expected)
        actual_num = float(actual)
        diff_ratio = abs(expected_num - actual_num) / max(abs(expected_num), abs(actual_num), 1)
        if diff_ratio < 0.1:
            return "partial", 0.9, f"数值接近 (差异 {diff_ratio:.1%})"
        elif diff_ratio < 0.3:
            return "partial", 0.7, f"数值部分匹配 (差异 {diff_ratio:.1%})"
        else:
            return "semantic", 0.3, f"数值差异较大 (差异 {diff_ratio:.1%})"
    except (ValueError, TypeError):
        pass
    
    # 字符串相似度
    similarity = calculate_string_similarity(expected_str, actual_str)
    
    if similarity >= 0.9:
        return "partial", 0.9, f"高度相似 ({similarity:.1%})"
    elif similarity >= 0.7:
        return "partial", 0.7, f"部分相似 ({similarity:.1%})"
    elif similarity >= 0.5:
        return "semantic", 0.5, f"语义相关 ({similarity:.1%})"
    else:
        return "no_match", 0.0, f"不匹配 (相似度 {similarity:.1%})"


def evaluate_persona_profile(
    user_input: str,
    expected_profile: Dict[str, Any],
    actual_profile: Dict[str, Any],
    rules: Dict[str, Any]
) -> Dict[str, Any]:
    """
    评估画像构建结果
    
    Args:
        user_input: 用户输入
        expected_profile: 期望画像
        actual_profile: 实际画像
        rules: 规则配置
    
    Returns:
        评估结果字典
    """
    if not expected_profile:
        return {
            "field_recall": 0.0,
            "field_precision": 0.0,
            "value_accuracy": 0.0,
            "overall_score": 0.0,
            "is_pass": False,
            "grade": "fail",
            "reason": "期望画像为空",
            "consensus_rate": 0.0,
            "field_stats": {}
        }
    
    if not actual_profile:
        return {
            "field_recall": 0.0,
            "field_precision": 0.0,
            "value_accuracy": 0.0,
            "overall_score": 0.0,
            "is_pass": False,
            "grade": "fail",
            "reason": "实际画像为空",
            "consensus_rate": 0.0,
            "field_stats": {}
        }
    
    field_weights = rules.get("field_weights", {})
    match_type_scores = rules.get("match_types", {})
    
    # 字段级统计
    field_stats: Dict[str, Dict[str, Any]] = {}
    
    # 计算字段召回率（期望字段中有多少被提取）
    expected_fields = set(expected_profile.keys())
    actual_fields = set(actual_profile.keys())
    
    matched_expected = expected_fields & actual_fields
    field_recall = len(matched_expected) / len(expected_fields) if expected_fields else 0.0
    
    # 计算字段精确率（提取的字段中有多少是正确的）
    field_precision = len(matched_expected) / len(actual_fields) if actual_fields else 0.0
    
    # 计算值准确率
    total_score = 0.0
    total_weight = 0.0
    
    for field_name in expected_fields:
        expected_value = expected_profile.get(field_name)
        actual_value = actual_profile.get(field_name)
        
        weight = field_weights.get(field_name, 0.5)
        match_type, score, reason = match_field_value(
            expected_value, actual_value, field_name, rules
        )
        
        field_stats[field_name] = {
            "expected": expected_value,
            "actual": actual_value,
            "match_type": match_type,
            "score": score,
            "reason": reason,
            "weight": weight
        }
        
        total_score += score * weight
        total_weight += weight
    
    # 对于实际中有但期望中没有的字段，给予部分惩罚
    extra_fields = actual_fields - expected_fields
    if extra_fields:
        for field_name in extra_fields:
            field_stats[field_name] = {
                "expected": None,
                "actual": actual_profile.get(field_name),
                "match_type": "extra",
                "score": 0.3,  # 额外字段给予部分分数
                "reason": "额外字段（期望中不存在）",
                "weight": 0.3
            }
    
    # 计算值准确率
    value_accuracy = total_score / total_weight if total_weight > 0 else 0.0
    
    # 计算综合得分
    overall_score = (
        field_recall * 0.3 +
        field_precision * 0.3 +
        value_accuracy * 0.4
    ) * 100
    
    # 判断等级
    grade_thresholds = rules.get("grade_thresholds", {})
    if overall_score >= grade_thresholds.get("excellent", 90):
        grade = "excellent"
    elif overall_score >= grade_thresholds.get("good", 80):
        grade = "good"
    elif overall_score >= grade_thresholds.get("pass", 60):
        grade = "pass"
    else:
        grade = "fail"
    
    # 判断是否通过
    pass_threshold = rules.get("pass_threshold", 60)
    is_pass = overall_score >= pass_threshold
    
    # 生成原因
    if is_pass:
        reason = f"画像构建{'优秀' if grade == 'excellent' else '良好' if grade == 'good' else '合格'}"
    else:
        missing_fields = expected_fields - actual_fields
        if missing_fields:
            reason = f"缺少字段: {', '.join(list(missing_fields)[:3])}"
        else:
            reason = "字段值匹配度较低"
    
    # 计算共识率（字段匹配的一致程度）
    consensus_rate = len(matched_expected) / len(expected_fields) if expected_fields else 0.0
    
    return {
        "field_recall": round(field_recall, 4),
        "field_precision": round(field_precision, 4),
        "value_accuracy": round(value_accuracy, 4),
        "overall_score": round(overall_score, 2),
        "is_pass": is_pass,
        "grade": grade,
        "reason": reason,
        "consensus_rate": round(consensus_rate, 4),
        "field_stats": field_stats
    }


# 导出
__all__ = ["load_rules", "evaluate_persona_profile"]
