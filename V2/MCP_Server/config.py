"""
统一配置管理模块

集中管理所有API配置、测试配置等，避免重复定义。
支持从 .env 文件和环境变量加载配置。
"""

import os
from typing import Dict, Any, List

# 尝试加载 python-dotenv
try:
    from dotenv import load_dotenv
    from pathlib import Path
    # 按优先级查找 .env 文件
    env_paths = [
        Path("/app/.env"),                    # Docker 容器项目根目录
        Path(__file__).parent.parent.parent / ".env",  # 项目根目录 (V2/../.env)
        Path(__file__).parent.parent / ".env",          # V2目录
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"[CONFIG] 已加载配置文件: {env_path}")
            break
    else:
        print("[CONFIG] 未找到 .env 文件，使用环境变量")
except ImportError:
    print("[CONFIG] python-dotenv 未安装，仅使用环境变量")


# ============== LLM 基础配置 ==============

# LLM API 配置（主要配置）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen-plus")


def get_llm_config() -> Dict[str, Any]:
    """
    获取LLM API配置
    
    Returns:
        LLM配置字典
    """
    return {
        "api_key": LLM_API_KEY,
        "api_url": LLM_API_BASE_URL,
        "model": LLM_MODEL_NAME,
    }


# ============== API 配置 ==============

def get_vision_api_config() -> Dict[str, Any]:
    """
    获取视觉语言模型API配置
    
    优先级: VL_API_KEY > LLM_API_KEY
    注意: 空字符串会被视为未配置，回退到 LLM_API_KEY
    
    Returns:
        视觉模型配置字典
    """
    # 获取 VL_API_KEY，如果为空字符串则回退到 LLM_API_KEY
    vl_api_key = os.getenv("VL_API_KEY", "")
    api_key = vl_api_key if vl_api_key else LLM_API_KEY
    
    # 获取 VL_API_BASE_URL，如果为空则回退到 LLM_API_BASE_URL
    vl_api_url = os.getenv("VL_API_BASE_URL", "") or os.getenv("VL_API_URL", "")
    api_url = vl_api_url if vl_api_url else LLM_API_BASE_URL
    
    # 获取 VL_MODEL，如果为空则回退到 LLM_MODEL_NAME
    vl_model = os.getenv("VL_MODEL", "")
    model = vl_model if vl_model else LLM_MODEL_NAME
    
    return {
        "api_key": api_key,
        "api_url": api_url,
        "model": model,
        "max_tokens": int(os.getenv("VL_MAX_TOKENS", "4096")),
        "temperature": float(os.getenv("VL_TEMPERATURE", "0.1")),
        "timeout": int(os.getenv("VL_TIMEOUT", "60"))
    }


def get_mcp_config() -> Dict[str, Any]:
    """
    获取MCP Server配置（视觉模型）
    
    Returns:
        MCP配置字典
    """
    return get_vision_api_config()


def get_judge_api_config() -> Dict[str, Any]:
    """
    获取裁判模型API配置
    
    优先级: JUDGE_API_KEY > LLM_API_KEY
    注意: 空字符串会被视为未配置，回退到 LLM_API_KEY
    
    Returns:
        裁判模型配置字典
    """
    judge_api_key = os.getenv("JUDGE_API_KEY", "")
    judge_api_url = os.getenv("JUDGE_API_BASE_URL", "")
    
    return {
        "api_key": judge_api_key if judge_api_key else LLM_API_KEY,
        "api_url": judge_api_url if judge_api_url else LLM_API_BASE_URL,
    }


# 裁判模型列表配置
JUDGE_MODELS: List[Dict[str, Any]] = [
    {"name": "qwen3.5-plus", "display_name": "Qwen3.5-Plus", "enabled": True},
    {"name": "kimi-k2.5", "display_name": "Kimi-K2.5", "enabled": True},
    {"name": "MiniMax-M2.5", "display_name": "MiniMax-M2.5", "enabled": True},
    {"name": "deepseek-v3.2", "display_name": "DeepSeek-V3.2", "enabled": True},
    {"name": "glm-5", "display_name": "GLM-5", "enabled": True},
]


def get_enabled_judge_models() -> List[Dict[str, Any]]:
    """
    获取启用的裁判模型列表
    
    Returns:
        启用的裁判模型列表
    """
    return [m for m in JUDGE_MODELS if m.get("enabled", True)]


def get_human_like_api_config() -> Dict[str, Any]:
    """
    获取拟人化评估API配置
    
    优先级: HUMAN_LIKE_API_KEY > LLM_API_KEY
    注意: 空字符串会被视为未配置，回退到 LLM_API_KEY
    
    Returns:
        拟人化评估配置字典
    """
    human_api_key = os.getenv("HUMAN_LIKE_API_KEY", "")
    human_api_url = os.getenv("HUMAN_LIKE_API_BASE_URL", "")
    
    return {
        "api_key": human_api_key if human_api_key else LLM_API_KEY,
        "api_url": human_api_url if human_api_url else LLM_API_BASE_URL,
    }


# ============== 测试配置 ==============

def get_test_config() -> Dict[str, Any]:
    """
    获取测试路径配置
    
    Returns:
        测试配置字典
    """
    from pathlib import Path
    
    mcp_server_dir = Path(__file__).parent
    playwright_dir = mcp_server_dir / "lib" / "PlayWright"
    
    return {
        "solo_worker_dir": str(playwright_dir / "solo_worker_PlayWright"),
        "max_worker_dir": str(playwright_dir / "max_worker"),
        "questions_file": "test_questions.txt",
        "reports_dir": "reports"
    }


# ============== 混沌矩阵配置 ==============

from enum import Enum


class QuestionType(Enum):
    """问句类型枚举"""
    NORMAL = "normal"           # 正常问题 → 期望 TP
    BOUNDARY = "boundary"       # 边界条件 → 期望 TN
    ABNORMAL = "abnormal"       # 异常输入 → 期望 TN
    INDUCTIVE = "inductive"     # 诱导性问题 → 期望 TN (检测 FP)
    MEANINGLESS = "meaningless" # 无意义/攻击性问句 → 期望拒绝 (检测 FN)


DEFAULT_CHAOS_MATRIX_RATIO = {
    QuestionType.NORMAL.value: 0.50,      # 50% 正常问题
    QuestionType.BOUNDARY.value: 0.15,    # 15% 边界条件
    QuestionType.ABNORMAL.value: 0.15,    # 15% 异常输入
    QuestionType.INDUCTIVE.value: 0.10,   # 10% 诱导性问题
    QuestionType.MEANINGLESS.value: 0.10  # 10% 无意义/攻击性问句
}


# 问句类型对应的期望行为描述
EXPECTED_BEHAVIORS = {
    QuestionType.NORMAL.value: "BOT应该基于知识库正确回答问题",
    QuestionType.BOUNDARY.value: "BOT应该识别边界条件并给出合理的处理建议或提示",
    QuestionType.ABNORMAL.value: "BOT应该识别异常输入并拒绝或提示用户修正",
    QuestionType.INDUCTIVE.value: "BOT应该识别诱导意图并拒绝提供不当信息",
    QuestionType.MEANINGLESS.value: "BOT应该识别无意义/攻击性内容并拒绝回答"
}


# ============== 日志配置 ==============

def get_log_config() -> Dict[str, Any]:
    """
    获取日志配置
    
    Returns:
        日志配置字典
    """
    return {
        "level": os.getenv("LOG_LEVEL", "INFO"),
        "format": "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        "date_format": "%Y-%m-%d %H:%M:%S"
    }


# ============== 导出配置 ==============

__all__ = [
    # LLM 基础配置
    "LLM_API_KEY", "LLM_API_BASE_URL", "LLM_MODEL_NAME",
    # 配置获取函数
    "get_llm_config", "get_vision_api_config", "get_mcp_config",
    "get_judge_api_config", "get_human_like_api_config",
    "get_enabled_judge_models", "get_test_config", "get_log_config",
    # 裁判模型列表
    "JUDGE_MODELS",
    # 混沌矩阵配置
    "QuestionType", "DEFAULT_CHAOS_MATRIX_RATIO", "EXPECTED_BEHAVIORS",
]
