# -*- coding: utf-8 -*-
"""报告加载服务"""

import os
import glob
import json
from typing import Any
from services.session_service import log_message


def load_latest_report_data(report_dir: str) -> dict[str, Any] | None:
    """加载最新报告数据

    报告可能保存在:
    - report_dir/test_report_*.json (旧格式)
    - report_dir/{timestamp}/test_report_*.json (新格式，带时间戳子目录)
    """
    # 先搜索当前目录
    json_files = sorted(glob.glob(os.path.join(report_dir, "test_report_*.json")), reverse=True)

    # 如果当前目录没有，搜索子目录（时间戳目录）
    if not json_files:
        json_files = sorted(glob.glob(os.path.join(report_dir, "*", "test_report_*.json")), reverse=True)

    if json_files:
        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_message(f"读取报告失败: {e}", "ERROR")
    return None


def format_test_summary(report_data: dict[str, Any], accuracy_stats: dict[str, Any] | None) -> str:
    """格式化测试摘要"""
    lines = ["[DONE] 测试完成!\n"]
    lines.append(f"测试统计:")
    lines.append(f"  - 总问题数: {report_data.get('total', 0)}")
    lines.append(f"  - 成功回复: {report_data.get('success', 0)}")
    lines.append(f"  - 成功率: {report_data.get('success_rate', 0)}%")
    
    stats = report_data.get("response_time_stats", {})
    if stats:
        lines.append(f"\n响应时间:")
        lines.append(f"  - 平均: {stats.get('average', 0)}秒")
        lines.append(f"  - 最小: {stats.get('min', 0)}秒")
        lines.append(f"  - 最大: {stats.get('max', 0)}秒")
    
    if accuracy_stats:
        lines.append(f"\n精确率统计:")
        lines.append(f"  - 正确回答: {accuracy_stats.get('correct', 0)}/{accuracy_stats.get('total', 0)}")
        lines.append(f"  - 精确率: {accuracy_stats.get('accuracy_rate', 0)}%")
        lines.append(f"  - 平均得分: {accuracy_stats.get('avg_score', 0)}分")
    
    return "\n".join(lines)
