"""问题加载模块"""

import os
import sys

# 处理相对导入
try:
    from .config import DEFAULT_QUESTIONS
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import DEFAULT_QUESTIONS


def load_questions(filepath, max_count):
    """从文件加载问题"""
    if not filepath or not os.path.exists(filepath):
        print(f"使用默认问题")
        return DEFAULT_QUESTIONS[:max_count]
    
    questions = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    questions.append(line)
        print(f"[OK] 从文件加载了 {len(questions)} 个问题")
        return questions[:max_count]
    except Exception as e:
        print(f"加载问题失败: {e}，使用默认问题")
        return DEFAULT_QUESTIONS[:max_count]
