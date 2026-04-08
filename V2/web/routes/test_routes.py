# -*- coding: utf-8 -*-
"""测试执行路由"""

import os
import re
import json
import base64
import subprocess
import sys
import threading
from flask import request, jsonify
from typing import Optional

from routes import test_bp
from services import (
    get_session_status, get_session_logs, agent_status, log_message,
    kill_process, register_process, unregister_process, load_saved_questions,
    execute_test, execute_concurrent_test
)
from config import PLAYWRIGHT_DIR

# Agent引用（多用户会话隔离）
_get_agent_func = None

def set_get_agent(get_agent_func):
    """设置获取 Agent 实例的函数"""
    global _get_agent_func
    _get_agent_func = get_agent_func

def get_agent_for_session(session_id: str = ""):
    """获取会话对应的 Agent 实例"""
    if _get_agent_func:
        return _get_agent_func(session_id)
    return None

# 兼容旧代码的 set_agent（已废弃，保留向后兼容）
agent = None
def set_agent(agent_instance):
    """设置Agent实例（已废弃，使用 set_get_agent）"""
    global agent
    agent = agent_instance

# 移动端测试器实例缓存
_mobile_testers: dict = {}


def _get_auth_decorator():
    """获取认证装饰器"""
    try:
        from middleware import require_auth
        return require_auth
    except ImportError:
        return lambda f: f


@test_bp.route("/run_test", methods=["POST"])
@_get_auth_decorator()
def run_test():
    """运行测试"""
    data = request.json or {}
    session_id = data.get("session_id", "")
    
    # 先终止该会话之前的单测试进程
    kill_process(session_id, "single")
    
    # 获取URL，如果为空则尝试从session状态获取
    url = data.get("url", "")
    if not url:
        # 尝试从session状态获取上次保存的URL
        status = get_session_status(session_id) if session_id else agent_status
        url = status.get("test_url", "")
    if not url:
        return jsonify({"success": False, "error": "未设置测试URL，请先在设置中配置测试网站地址"})
    
    questions = data.get("questions", [])
    username = data.get("username", "")
    password = data.get("password", "")
    
    # 获取会话专属的 Agent 实例
    agent = get_agent_for_session(session_id)
    if not questions and agent and hasattr(agent, "pending_questions"):
        questions = agent.pending_questions
    if not questions:
        questions = load_saved_questions(session_id, target="solo")
    if not questions:
        return jsonify({"success": False, "error": "没有测试问题"})
    
    # 保存登录凭据到session状态
    status = get_session_status(session_id) if session_id else agent_status
    if username:
        status["username"] = username
    if password:
        status["password"] = password
    
    agent_status["is_running"] = True
    agent_status["progress"] = 0
    
    if session_id:
        s = get_session_status(session_id)
        s["is_running"] = True
        s["progress"] = 0
    
    thread = threading.Thread(target=execute_test, args=(url, questions, session_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "测试已启动"})


@test_bp.route("/stop_test", methods=["POST"])
def stop_test():
    """停止测试"""
    data = request.json or {}
    session_id = data.get("session_id", "")
    
    # 终止该会话的所有测试进程
    kill_process(session_id, "single")
    kill_process(session_id, "concurrent")
    kill_process(session_id, "check")
    
    if session_id:
        status = get_session_status(session_id)
        status["is_running"] = False
    else:
        agent_status["is_running"] = False
    
    log_message("测试已停止", "WARN", session_id=session_id)
    return jsonify({"success": True})


@test_bp.route("/concurrent-test", methods=["POST"])
@_get_auth_decorator()
def start_concurrent_test():
    """启动并发测试"""
    data = request.json or {}
    session_id = data.get("session_id", "default")
    question_count = data.get("question_count", 5)
    worker_count = data.get("worker_count", 1)
    target_sites = data.get("target_sites", [])
    username = data.get("username", "")
    password = data.get("password", "")
    knowledge = data.get("knowledge", [])
    
    print(f"[API] start_concurrent_test: question_count={question_count}, target_sites={target_sites}, knowledge={knowledge}")
    
    status = get_session_status(session_id)
    # 先终止该会话之前的并发测试进程
    kill_process(session_id, "concurrent")
    
    # 记住用户选择的知识库（支持多选）
    if knowledge:
        status["last_knowledge"] = knowledge if isinstance(knowledge, list) else [knowledge]
        log_message(f"并发测试: 用户选择了知识库: {knowledge}", "INFO", session_id=session_id)
    
    # 保存配置到 session 状态（多用户隔离，不再修改配置文件）
    status["worker_count"] = worker_count
    status["question_count"] = question_count
    
    # 保存用户选择的网站到session状态
    status["target_sites"] = target_sites
    log_message(f"并发测试: 用户选择了 {len(target_sites)} 个网站: {target_sites}", session_id=session_id)
    
    status["is_running"] = True
    thread = threading.Thread(target=execute_concurrent_test, args=(session_id, username, password, target_sites))
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "并发测试已启动", "action": "concurrent_test_started"})


# ==================== 移动端测试路由 ====================

@test_bp.route("/mobile/devices", methods=["GET"])
def list_mobile_devices():
    """列出可用的移动设备"""
    try:
        # 尝试获取连接的设备列表
        devices = []
        
        # Android: 使用 adb devices
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:  # 跳过标题行
                    if "\t" in line:
                        device_id, status = line.split("\t")
                        if status == "device":
                            devices.append({
                                "id": device_id,
                                "platform": "Android",
                                "status": "connected"
                            })
        except Exception:
            pass
        
        # iOS: 使用 idevice_id (需要 libimobiledevice)
        try:
            result = subprocess.run(
                ["idevice_id", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        devices.append({
                            "id": line.strip(),
                            "platform": "iOS",
                            "status": "connected"
                        })
        except Exception:
            pass
        
        return jsonify({
            "success": True,
            "devices": devices,
            "count": len(devices)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "devices": []
        })


@test_bp.route("/mobile/test", methods=["POST"])
@_get_auth_decorator()
def run_mobile_test():
    """
    运行移动端测试
    
    请求参数:
    - session_id: 会话ID
    - device_id: 设备ID (可选，如果不提供则使用第一个可用设备)
    - platform: 平台类型 "Android" 或 "iOS"
    - app_package: APP包名
    - app_activity: APP启动Activity (Android)
    - questions: 测试问题列表
    - chat_input_id: 聊天输入框元素ID
    - chat_send_id: 发送按钮元素ID
    """
    data = request.json or {}
    session_id = data.get("session_id", "")
    
    # 设备配置
    device_id = data.get("device_id", "")
    platform = data.get("platform", "Android")
    app_package = data.get("app_package", "")
    app_activity = data.get("app_activity", "")
    
    # 测试配置
    questions = data.get("questions", [])
    chat_input_id = data.get("chat_input_id", "")
    chat_send_id = data.get("chat_send_id", "")
    
    # 获取问题
    if not questions and agent and hasattr(agent, "pending_questions"):
        questions = agent.pending_questions
    if not questions:
        questions = load_saved_questions(session_id, target="solo")
    if not questions:
        return jsonify({"success": False, "error": "没有测试问题"})
    
    if not app_package:
        return jsonify({"success": False, "error": "请提供APP包名 (app_package)"})
    
    # 更新会话状态
    status = get_session_status(session_id)
    status["is_running"] = True
    status["platform"] = "mobile"
    
    log_message(f"[Mobile] 启动移动端测试: {platform}, 设备: {device_id}, APP: {app_package}", session_id=session_id)
    
    def run_mobile_test_thread():
        tester = None
        try:
            # 导入移动端测试器
            lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "MCP_Server", "lib")
            if lib_path not in sys.path:
                sys.path.insert(0, lib_path)
            
            # pylint: disable=import-error
            from base_tester import TestConfig, PlatformType  # type: ignore
            from Appium import MobileTester  # type: ignore
            
            # 创建测试配置
            config = TestConfig(
                url="",
                questions=questions,
                session_id=session_id,
                platform=PlatformType.MOBILE,
                device_name=device_id,
                platform_name=platform,
                app_package=app_package,
                app_activity=app_activity,
            )
            
            # 创建测试器
            tester = MobileTester(config)
            
            # 配置聊天元素
            tester.mobile_config.chat_input_id = chat_input_id
            tester.mobile_config.chat_send_id = chat_send_id
            
            # 缓存测试器
            _mobile_testers[session_id] = tester
            
            # 执行测试
            results = tester.execute_all()
            
            # 生成报告
            report_path = tester.generate_report()
            
            # 统计结果
            success_count = sum(1 for r in results if r.success)
            log_message(f"[Mobile] 测试完成: {success_count}/{len(results)} 成功", session_id=session_id)
            
            # 保存结果到会话状态
            status["mobile_results"] = [
                {
                    "question": r.question,
                    "answer": r.answer,
                    "success": r.success,
                    "response_time": r.response_time,
                    "error": r.error
                }
                for r in results
            ]
            status["mobile_report"] = report_path
            
        except ImportError as e:
            log_message(f"[Mobile] 导入模块失败: {e}，请确保已安装 Appium-Python-Client", "ERROR", session_id=session_id)
        except Exception as e:
            log_message(f"[Mobile] 测试失败: {e}", "ERROR", session_id=session_id)
        finally:
            status["is_running"] = False
            if session_id in _mobile_testers:
                del _mobile_testers[session_id]
    
    thread = threading.Thread(target=run_mobile_test_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "message": "移动端测试已启动",
        "action": "mobile_test_started"
    })


@test_bp.route("/mobile/stop", methods=["POST"])
def stop_mobile_test():
    """停止移动端测试"""
    data = request.json or {}
    session_id = data.get("session_id", "")
    
    if session_id in _mobile_testers:
        tester = _mobile_testers[session_id]
        tester.stop()
        del _mobile_testers[session_id]
        log_message("[Mobile] 测试已停止", "WARN", session_id=session_id)
    
    status = get_session_status(session_id)
    status["is_running"] = False
    
    return jsonify({"success": True, "message": "移动端测试已停止"})


@test_bp.route("/mobile/status", methods=["GET"])
def get_mobile_status():
    """获取移动端测试状态"""
    session_id = request.args.get("session_id", "")
    
    status = get_session_status(session_id)
    
    return jsonify({
        "success": True,
        "is_running": status.get("is_running", False),
        "platform": status.get("platform", "web"),
        "results": status.get("mobile_results", []),
        "report": status.get("mobile_report", "")
    })
