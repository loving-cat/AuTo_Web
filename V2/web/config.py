# -*- coding: utf-8 -*-
"""V2 Web应用配置"""

import os
import sys

# ========== 路径配置 ==========
WEB_DIR = os.path.dirname(os.path.abspath(__file__))

# 判断是否在 Docker 容器中
if os.path.exists("/app/web"):
    # Docker 容器环境: /app/web/config.py
    APP_DIR = "/app"
    V2_ROOT = "/app"
    PROJECT_ROOT = "/app"  # 容器内统一路径
else:
    # 本地开发环境: V2/web/config.py
    V2_ROOT = os.path.dirname(WEB_DIR)  # V2目录
    PROJECT_ROOT = os.path.dirname(V2_ROOT)  # Auto_aiwa根目录

# 添加路径
if V2_ROOT not in sys.path:
    sys.path.insert(0, V2_ROOT)
if WEB_DIR not in sys.path:
    sys.path.insert(0, WEB_DIR)

# ========== 目录配置 ==========
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "Agent_Test", "data", "uploads")
PLAYWRIGHT_DIR = os.path.join(V2_ROOT, "MCP_Server", "lib", "PlayWright")
SINGLE_TEST_REPORT_DIR = os.path.join(PLAYWRIGHT_DIR, "solo_worker_PlayWright", "reports")
CONCURRENT_REPORT_DIR = os.path.join(PLAYWRIGHT_DIR, "max_worker", "reports")

# ========== 执行模式配置 ==========
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "local").lower()
IS_REMOTE_MODE = EXECUTION_MODE == "remote"

# ========== Flask配置 ==========
PORT = int(os.getenv("V2_PORT", "5002"))
HOST = "0.0.0.0"
