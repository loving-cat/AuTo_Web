# -*- coding: utf-8 -*-
# AIWA V2 Dockerfile - 生产级优化版本
# 多阶段构建，支持 Flask Web + MCP Server + Playwright 自动化测试
#
# 构建命令: docker build -t aiwa-v2:latest .
# 运行命令: docker run -d -p 5002:5002 --env-file ../.env aiwa-v2:latest
#
# 镜像大小: ~1.2GB (含 Playwright Chromium)

# ============================================================
# 第一阶段: 构建依赖
# ============================================================
FROM python:3.11-slim-bookworm AS builder

# 构建环境变量
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_TIMEOUT=120

# 使用阿里云镜像源加速 (Debian 12 bookworm)
RUN set -ex && \
    sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libc-dev \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

WORKDIR /build

# 安装 Python 依赖
COPY requirements.txt ./requirements.txt
RUN pip install --user -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# ============================================================
# 第二阶段: 生产镜像
# ============================================================
FROM python:3.11-slim-bookworm AS production

LABEL maintainer="AIWA Team" \
      version="2.0" \
      description="AIWA Agent Test Platform - Flask + MCP + Playwright"

# 生产环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/MCP_Server:/app/MCP_Server/lib \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    DISPLAY=:99 \
    PORT=5002 \
    HOST=0.0.0.0 \
    FLASK_ENV=production \
    FLASK_DEBUG=0

# 使用阿里云镜像源
RUN set -ex && \
    sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

# 安装 Playwright 必需的系统依赖 (完整列表)
RUN set -ex && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        # Playwright 核心依赖
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libatspi2.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        # 图像处理
        libxslt1.1 \
        libxml2 \
        # 字体支持 (中文)
        fonts-wqy-zenhei \
        fonts-wqy-microhei \
        fonts-noto-cjk \
        # 网络工具
        curl \
        wget \
        # 进程管理
        supervisor \
        # Xvfb 虚拟显示 (无头模式备用)
        xvfb \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    && apt-get clean

# 复制 Python 依赖（从构建阶段）
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:/usr/local/bin:$PATH

WORKDIR /app

# 安装 Playwright Chromium 浏览器（仅安装 chromium，减少体积）
RUN set -ex && \
    playwright install chromium --with-deps && \
    playwright install-deps chromium && \
    rm -rf /ms-playwright/.cache

# 创建应用目录结构
RUN set -ex && \
    mkdir -p /app/data/uploads \
             /app/data/reports \
             /app/data/logs \
             /app/Agent_Test/data/uploads \
             /app/Agent_Test/data/reports \
             /app/Agent_Test/data/logs \
             /app/MCP_Server/lib/PlayWright/solo_worker_PlayWright/reports \
             /app/MCP_Server/lib/PlayWright/max_worker/reports \
    && chmod -R 777 /app/data /app/Agent_Test/data

# ============================================================
# 复制应用代码（分层复制，优化缓存）
# ============================================================

# 1. 复制 MCP_Server 模块（核心依赖）
COPY MCP_Server/ ./MCP_Server/

# 2. 复制 Web 服务模块
COPY web/ ./web/

# 3. 复制启动脚本
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

# ============================================================
# 容器配置
# ============================================================

# 暴露端口
EXPOSE 5002

# 健康检查（优化间隔）
HEALTHCHECK --interval=60s --timeout=15s --start-period=90s --retries=5 \
    CMD curl -sf http://localhost:5002/api/mode || exit 1

# 切换工作目录
WORKDIR /app/web

# 启动命令
CMD ["/app/start.sh"]