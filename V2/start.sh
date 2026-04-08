#!/bin/bash
# AIWA V2 启动脚本 - 生产级优化版
# 用于 Docker 容器启动前的环境检查和初始化

set -e

echo "=========================================="
echo "AIWA V2 服务启动"
echo "=========================================="
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"

# ============================================================
# 1. 环境变量检查
# ============================================================
echo "[1/6] 检查环境变量..."

# 必需的环境变量
REQUIRED_VARS=("LLM_API_KEY")
MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo "[WARN] 未设置以下必需环境变量: ${MISSING_VARS[*]}"
    echo "[WARN] 请在 .env 文件中配置或在 docker-compose.yml 中设置"
fi

# 打印当前配置（隐藏敏感信息）
echo "[INFO] EXECUTION_MODE: ${EXECUTION_MODE:-local}"
echo "[INFO] PORT: ${PORT:-5002}"
echo "[INFO] PYTHONPATH: ${PYTHONPATH}"

# ============================================================
# 2. Playwright 浏览器检查
# ============================================================
echo "[2/6] 检查 Playwright 浏览器..."

if [ ! -d "/ms-playwright/chromium" ]; then
    echo "[INFO] 安装 Playwright Chromium..."
    playwright install chromium --with-deps
fi

echo "[OK] Playwright Chromium 已就绪"

# ============================================================
# 3. 创建必要目录
# ============================================================
echo "[3/6] 创建数据目录..."

mkdir -p /app/data/uploads
mkdir -p /app/data/reports
mkdir -p /app/data/logs
mkdir -p /app/Agent_Test/data/uploads
mkdir -p /app/Agent_Test/data/reports
mkdir -p /app/Agent_Test/data/logs
mkdir -p /app/MCP_Server/lib/PlayWright/solo_worker_PlayWright/reports
mkdir -p /app/MCP_Server/lib/PlayWright/max_worker/reports

echo "[OK] 数据目录已创建"

# ============================================================
# 4. 模块导入检查
# ============================================================
echo "[4/6] 检查模块导入..."

cd /app

# 检查 MCP_Server 模块
python -c "from MCP_Server.tools_api import run_debug_test" && echo "[OK] MCP_Server.tools_api 正常" || echo "[WARN] MCP_Server.tools_api 导入失败"
python -c "from MCP_Server.config import get_mcp_config" && echo "[OK] MCP_Server.config 正常" || echo "[WARN] MCP_Server.config 导入失败"

# 检查 Web 模块
python -c "import sys; sys.path.insert(0, '/app/web'); from config import PORT, HOST" && echo "[OK] web.config 正常" || echo "[WARN] web.config 导入失败"

# ============================================================
# 5. 权限检查
# ============================================================
echo "[5/6] 检查文件权限..."

chmod -R 777 /app/data 2>/dev/null || true
chmod -R 777 /app/Agent_Test/data 2>/dev/null || true

echo "[OK] 权限设置完成"

# ============================================================
# 6. 启动 Flask 服务
# ============================================================
echo "[6/6] 启动 Flask Web 服务..."
echo "=========================================="
echo "服务端口: ${PORT:-5002}"
echo "执行模式: ${EXECUTION_MODE:-local}"
echo "=========================================="

# 切换到 web 目录并启动
cd /app/web

# 使用 gunicorn 生产服务器（如果可用）
if command -v gunicorn &> /dev/null; then
    echo "[INFO] 使用 Gunicorn 生产服务器"
    exec gunicorn \
        --bind 0.0.0.0:${PORT:-5002} \
        --workers 2 \
        --threads 4 \
        --timeout 120 \
        --keep-alive 5 \
        --access-logfile /app/data/logs/access.log \
        --error-logfile /app/data/logs/error.log \
        --log-level info \
        app:app
else
    echo "[INFO] 使用 Flask 开发服务器"
    exec python app.py
fi