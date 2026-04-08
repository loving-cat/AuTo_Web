# -*- coding: utf-8 -*-
"""自动化测试Agent Web界面 - 精简版"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sys
import os

# ========== 路径配置（必须在其他导入之前）==========
web_dir = os.path.dirname(os.path.abspath(__file__))
if web_dir not in sys.path:
    sys.path.insert(0, web_dir)

# 加载 .env 环境变量
try:
    from dotenv import load_dotenv
    # 尝试多个可能的 .env 路径
    env_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
        os.path.join(os.getcwd(), '.env'),
        '.env'
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            load_dotenv(env_path)
            print(f"[Flask] 已加载环境变量: {env_path}")
            break
except ImportError:
    print("[Flask] 警告: 未安装 python-dotenv，使用系统环境变量")

# Windows控制台UTF-8编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# 导入配置
from config import (
    UPLOAD_DIR, 
    SINGLE_TEST_REPORT_DIR, IS_REMOTE_MODE, PORT, HOST
)

# 导入路由蓝图
from routes import (
    test_bp, chat_bp, question_bp, file_bp,
    report_bp, site_bp, task_bp, check_bp, persona_bp,
    product_bp
)

# 导入路由模块（将路由绑定到蓝图）
import routes.test_routes
import routes.chat_routes
import routes.question_routes
import routes.file_routes
import routes.report_routes
import routes.site_routes
import routes.task_routes
import routes.check_routes
import routes.persona_routes
import routes.product_routes

# 导入认证中间件
try:
    from middleware import require_auth, check_auth_status
except ImportError:
    # 兼容直接运行的情况
    middleware_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "middleware")
    if os.path.exists(middleware_dir):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from middleware import require_auth, check_auth_status
    else:
        # 回退：创建空装饰器
        def require_auth(f):
            return f
        def check_auth_status():
            return {"enabled": False, "message": "认证模块未加载"}

# 导入数据库模块
try:
    from database import (
        create_task, update_task_status, save_task_result, 
        get_task, get_tasks_by_session, get_recent_tasks, get_task_results,
        cleanup_old_tasks
    )
    DB_AVAILABLE = True
except ImportError as e:
    print(f"[WARN] 数据库模块未加载: {e}")
    DB_AVAILABLE = False

# ========== Flask应用初始化 ==========
app = Flask(__name__)
CORS(app)

# 注册蓝图
app.register_blueprint(test_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(question_bp)
app.register_blueprint(file_bp)
app.register_blueprint(report_bp)
app.register_blueprint(site_bp)
app.register_blueprint(task_bp)
app.register_blueprint(check_bp)
app.register_blueprint(persona_bp)
app.register_blueprint(product_bp)

# ========== 远程模式任务队列 ==========
_task_queue = None
_TaskType = None

if IS_REMOTE_MODE:
    try:
        from task_queue import get_task_queue, TaskType as _TaskTypeImport
        _task_queue = get_task_queue()
        _TaskType = _TaskTypeImport
        print("[OK] 任务队列初始化成功(远程模式)")
        
        # 初始化任务路由的远程模式
        from routes.task_routes import init_remote_mode
        init_remote_mode(_task_queue, _TaskType)
    except ImportError as e:
        print(f"[WARN] 任务队列导入失败，回退到本地模式: {e}")

# ========== Agent初始化（多用户会话隔离） ==========
_agent_available = False
TestAgent = None
_agent_pool: dict = {}  # session_id -> Agent 实例
_agent_pool_lock = __import__('threading').Lock()

def get_agent(session_id: str = ""):
    """获取或创建会话专属的 Agent 实例"""
    if not _agent_available or TestAgent is None:
        return None
    
    with _agent_pool_lock:
        if session_id not in _agent_pool:
            _agent_pool[session_id] = TestAgent()
            print(f"[Agent] 创建会话 Agent: {session_id}")
        return _agent_pool[session_id]

def cleanup_agent(session_id: str):
    """清理会话的 Agent 实例"""
    with _agent_pool_lock:
        if session_id in _agent_pool:
            del _agent_pool[session_id]
            print(f"[Agent] 清理会话 Agent: {session_id}")

if not IS_REMOTE_MODE:
    try:
        from agent_wrapper import TestAgent as _TestAgent
        TestAgent = _TestAgent
        _agent_available = True
        print("[OK] Agent模块加载成功(本地模式，支持多用户会话隔离)")
        
        # 设置 get_agent 函数到路由模块
        from routes.test_routes import set_get_agent as set_test_get_agent
        from routes.chat_routes import set_get_agent as set_chat_get_agent
        from routes.question_routes import set_get_agent as set_question_get_agent
        from routes.persona_routes import set_get_agent as set_persona_get_agent
        from services.test_executor import set_get_agent as set_executor_get_agent
        
        set_test_get_agent(get_agent)
        set_chat_get_agent(get_agent)
        set_question_get_agent(get_agent)
        set_persona_get_agent(get_agent)
        set_executor_get_agent(get_agent)
        
    except ImportError as e:
        import traceback
        print(f"[ERROR] Agent模块加载失败: {e}")
        traceback.print_exc()
        print("[ERROR] 请检查以下配置:")
        print("  1. .env 文件是否存在并包含 LLM_API_KEY")
        print("  2. LLM_API_KEY 是否已正确配置")
        print("  3. 检查 config/__init__.py 是否正确加载")

# ========== 基础路由 ==========
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/mode")
def get_mode():
    """获取执行模式"""
    return jsonify({
        "success": True,
        "mode": "remote" if IS_REMOTE_MODE else "local",
        "agent_available": _agent_available or IS_REMOTE_MODE
    })


@app.route("/api/auth/status")
def auth_status():
    """获取认证状态"""
    return jsonify(check_auth_status())


# ========== 错误处理 ==========
@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "API路径不存在"}), 404
    return render_template("index.html")


@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "error": "服务器错误"}), 500


# ========== 主入口 ==========
if __name__ == "__main__":
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(SINGLE_TEST_REPORT_DIR, exist_ok=True) 
    
    # 打印认证状态
    auth_info = check_auth_status()
    print(f"[AUTH] {auth_info['message']}")
    
    # 启动会话清理任务
    from services.session_service import start_cleanup_timer
    start_cleanup_timer(interval_minutes=10)
    
    print("=" * 60)
    print("Agent Web界面")
    print(f"执行模式: {'远程分发' if IS_REMOTE_MODE else '本地执行'}")
    print(f"Agent状态: {'可用' if (_agent_available or IS_REMOTE_MODE) else '不可用'}")
    print(f"多用户支持: 已启用（会话隔离）")
    print("=" * 60)
    print(f"访问地址: http://localhost:{PORT}")
    print(f"访问地址: http://192.168.7.16:{PORT}")
    
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
