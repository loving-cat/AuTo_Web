# -*- coding: utf-8 -*-
"""页面检查路由"""

import os
import sys
import json
import subprocess
from flask import request, jsonify, Response

from routes import check_bp
from services import log_message
from services.process_manager import register_process, unregister_process, kill_process
from config import PLAYWRIGHT_DIR


def _get_auth_decorator():
    """获取认证装饰器"""
    try:
        from middleware import require_auth
        return require_auth
    except ImportError:
        return lambda f: f


@check_bp.route("/check/login", methods=["POST"])
@_get_auth_decorator()
def check_login():
    """仅登录页面"""
    data = request.json or {}
    login_url = data.get("login_url", "") or data.get("url", "")
    target_url = data.get("target_url", "")
    username = data.get("username", "")
    password = data.get("password", "")
    session_id = data.get("session_id", "")

    def generate():
        process = None
        try:
            script_path = os.path.join(PLAYWRIGHT_DIR, "checkWeb", "check_web_element_demo.py")

            if not os.path.exists(script_path):
                yield f"data: {json.dumps({'message': '[ERROR] 检查脚本不存在', 'done': True})}\n\n"
                return

            # 先终止该会话之前的check进程
            kill_process(session_id, "check")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CHECK_LOGIN_URL"] = login_url
            env["CHECK_TARGET_URL"] = target_url
            env["CHECK_USERNAME"] = username
            env["CHECK_PASSWORD"] = password
            env["CHECK_MODE"] = "login_only"
            if session_id:
                env["SESSION_ID"] = session_id

            yield f"data: {json.dumps({'status': '正在启动浏览器...', 'done': False})}\n\n"

            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=os.path.dirname(script_path),
                env=env, encoding="utf-8", errors="replace"
            )

            # 注册进程
            register_process(session_id, "check", process)

            if process.stdout:
                for line in process.stdout:
                    if line.strip():
                        yield f"data: {json.dumps({'message': line.strip(), 'done': False})}\n\n"

            process.wait()
            yield f"data: {json.dumps({'status': '登录完成', 'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'message': f'[ERROR] {str(e)}', 'done': True})}\n\n"
        finally:
            unregister_process(session_id, "check")

    return Response(generate(), mimetype="text/event-stream")


@check_bp.route("/check/analyze", methods=["POST"])
@_get_auth_decorator()
def check_analyze():
    """分析页面元素"""
    data = request.json or {}
    login_url = data.get("login_url", "") or data.get("url", "")
    target_url = data.get("target_url", "")
    username = data.get("username", "")
    password = data.get("password", "")
    session_id = data.get("session_id", "")

    def generate():
        process = None
        try:
            import json as json_module

            script_path = os.path.join(PLAYWRIGHT_DIR, "checkWeb", "check_web_element_demo.py")

            if not os.path.exists(script_path):
                yield f"data: {json.dumps({'message': '[ERROR] 检查脚本不存在', 'done': True})}\n\n"
                return

            # 先终止该会话之前的check进程
            kill_process(session_id, "check")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CHECK_LOGIN_URL"] = login_url
            env["CHECK_TARGET_URL"] = target_url
            env["CHECK_USERNAME"] = username
            env["CHECK_PASSWORD"] = password
            env["CHECK_MODE"] = "analyze"
            if session_id:
                env["SESSION_ID"] = session_id

            yield f"data: {json.dumps({'status': '正在启动浏览器...', 'done': False})}\n\n"

            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, cwd=os.path.dirname(script_path),
                env=env, encoding="utf-8", errors="replace"
            )

            # 注册进程
            register_process(session_id, "check", process)

            elements = []
            if process.stdout:
                for line in process.stdout:
                    if line.strip():
                        # 尝试解析元素JSON
                        if line.strip().startswith("[ELEMENTS]"):
                            try:
                                elements_json = line.strip().replace("[ELEMENTS] ", "")
                                elements = json_module.loads(elements_json)
                            except:
                                pass
                        yield f"data: {json.dumps({'message': line.strip(), 'done': False})}\n\n"

            process.wait()

            if elements:
                yield f"data: {json.dumps({'status': f'分析完成，识别到 {len(elements)} 个元素', 'elements': elements, 'done': True})}\n\n"
            else:
                yield f"data: {json.dumps({'status': '分析完成', 'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'message': f'[ERROR] {str(e)}', 'done': True})}\n\n"
        finally:
            unregister_process(session_id, "check")

    return Response(generate(), mimetype="text/event-stream")
