"""
配置文件 - 敏感信息已迁移到环境变量
请创建项目根目录的 .env 文件或设置环境变量
"""
import os

CONFIG = {
    "login_url": os.getenv("TEST_LOGIN_URL", ""),  # [CLEARED]
    "username": os.getenv("TEST_USERNAME", ""),
    "password": os.getenv("TEST_PASSWORD", ""),
    "bot_name": os.getenv("TEST_BOT_NAME", ""),
    "api_key": os.getenv("LLM_API_KEY", ""),  # [CLEARED]
    "api_url": os.getenv("LLM_API_BASE_URL", ""),  # [CLEARED]
    "model": os.getenv("LLM_MODEL_NAME", "qwen-plus"),
    "questions_file": "test_questions.txt",
    "max_questions": 100,
    "max_pages": 10,
    # 页内滚动配置
    "max_scrolls": 10,       # 每页最大滚动次数
    "scroll_wait": 800,      # 每次滚动后等待时间（毫秒）
}

DEFAULT_QUESTIONS = [
    "你好，请问你能帮我什么？",
    "X100蓝牙耳机的价格是多少？",
    "这款耳机有什么特色功能？",
    "支持哪些设备连接？",
    "续航时间怎么样？",
]
