"""
多渠道测试配置文件 - 站点配置改为运行时注入
"""
import os
import json
from typing import Dict


def get_sites_config() -> Dict:
    """
    获取站点配置 - 从环境变量 SITES_CONFIG_JSON 读取
    格式: '{"1":{"name":"Site1","url":"..."},...}'
    """
    sites_json = os.getenv("SITES_CONFIG_JSON", "")
    if sites_json:
        try:
            return json.loads(sites_json)
        except json.JSONDecodeError:
            print("[WARN] SITES_CONFIG_JSON 解析失败")
    return {}


# 兼容旧代码 - 获取配置
SITES_CONFIG = get_sites_config()

# 页面选择器配置（列表格式，支持多个选择器）
SELECTORS = {
    "chat_bubble": [
        ".chat-bubble",
        "[class*='chat-bubble']",
        "[class*='chatBubble']",
        ".chat-icon",
        "[class*='chat-icon']",
        "button[class*='chat']",
        ".float-chat",
        "[class*='float-chat']",
    ],
    "input_box": [
        "textarea[placeholder*='输入']",
        "textarea[placeholder*='请输入']",
        "textarea[placeholder*='消息']",
        "input[type='text'][placeholder*='输入']",
        "input[placeholder*='请输入']",
        ".chat-input textarea",
        ".chat-input input",
        "[class*='chat-input'] textarea",
        "[class*='chatInput'] textarea",
        "textarea",
    ],
    "send_button": [
        "button:has-text('发送')",
        "button[type='submit']",
        ".send-btn",
        "[class*='send-btn']",
        "[class*='sendBtn']",
        "button[class*='send']",
    ],
    "message_container": [
        ".message",
        ".chat-message",
        "[class*='message']",
        "[class*='chat-message']",
    ],
    "bot_message": [
        ".bot-message",
        ".assistant-message",
        "[class*='bot']",
        "[class*='assistant']",
        "[class*='reply']",
    ],
}

# 测试配置
TEST_CONFIG = {
    "timeout": int(os.getenv("TEST_TIMEOUT", "30000")),          # 超时时间（毫秒）
    "wait_for_response": int(os.getenv("TEST_WAIT_RESPONSE", "5")),    # 等待回复时间（秒）
    "max_retries": int(os.getenv("TEST_MAX_RETRIES", "3")),          # 最大重试次数
    "screenshot": os.getenv("TEST_SCREENSHOT", "true").lower() == "true",        # 是否截图
    "headless": os.getenv("TEST_HEADLESS", "true").lower() == "true",          # 无头模式
    "element_wait_time": int(os.getenv("TEST_ELEMENT_WAIT", "10")),          # 元素等待时间（秒）
    "chat_load_wait": int(os.getenv("TEST_CHAT_LOAD_WAIT", "500")),       # 聊天加载等待时间（毫秒）
    "question_interval": int(os.getenv("TEST_QUESTION_INTERVAL", "1")),           # 问题间隔（秒）
    "max_wait_time": int(os.getenv("TEST_MAX_WAIT_TIME", "30")),         # 最大等待时间（秒）
}
