# -*- coding: utf-8 -*-
"""任务管理路由"""

import json
from flask import request, jsonify

from routes import task_bp
from services import log_message
from config import IS_REMOTE_MODE

# 远程模式组件
_task_queue = None
_TaskType = None


def init_remote_mode(task_queue, task_type):
    """初始化远程模式组件"""
    global _task_queue, _TaskType
    _task_queue = task_queue
    _TaskType = task_type


@task_bp.route("/tasks", methods=["GET"])
def list_tasks():
    """获取任务列表"""
    if not IS_REMOTE_MODE or _task_queue is None:
        return jsonify({"success": False, "error": "仅在远程模式下可用"})
    tasks = _task_queue.get_all_tasks()
    return jsonify({"success": True, "tasks": [t.to_dict() for t in tasks]})


@task_bp.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    """获取单个任务"""
    if not IS_REMOTE_MODE or _task_queue is None:
        return jsonify({"success": False, "error": "仅在远程模式下可用"})
    task = _task_queue.get_task(task_id)
    if task:
        return jsonify({"success": True, "task": task.to_dict()})
    return jsonify({"success": False, "error": "任务不存在"}), 404


@task_bp.route("/tasks", methods=["POST"])
def create_task():
    """创建任务"""
    if not IS_REMOTE_MODE or _task_queue is None or _TaskType is None:
        return jsonify({"success": False, "error": "仅在远程模式下可用"})

    data = request.json or {}
    task_type_str = data.get("task_type", "single_test")

    try:
        task_type = _TaskType(task_type_str)
    except ValueError:
        return jsonify({"success": False, "error": f"无效的任务类型: {task_type_str}"})

    task = _task_queue.create_task(
        task_type=task_type,
        url=data.get("url", ""),
        questions=data.get("questions", []),
        question_count=data.get("question_count", 5),
        worker_count=data.get("worker_count", 1),
        username=data.get("username", ""),
        password=data.get("password", ""),
        bot_name=data.get("bot_name", ""),
        knowledge_file=data.get("knowledge_file", ""),
    )

    log_message(f"创建任务: {task.task_id} ({task_type_str})")
    return jsonify({
        "success": True,
        "task_id": task.task_id,
        "message": "任务已创建，等待执行节点处理"
    })


@task_bp.route("/tasks/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    """取消任务"""
    if not IS_REMOTE_MODE or _task_queue is None:
        return jsonify({"success": False, "error": "仅在远程模式下可用"})
    if _task_queue.cancel_task(task_id):
        return jsonify({"success": True, "message": "任务已取消"})
    return jsonify({"success": False, "error": "无法取消任务（可能已在执行或已完成）"})


@task_bp.route("/tasks/history")
def get_task_history():
    """获取任务历史"""
    try:
        from database import get_tasks_by_session, get_recent_tasks
        DB_AVAILABLE = True
    except ImportError:
        DB_AVAILABLE = False
    
    if not DB_AVAILABLE:
        return jsonify({"success": False, "error": "数据库不可用"})
    
    session_id = request.args.get("session_id", "")
    limit = int(request.args.get("limit", 50))
    
    if session_id:
        tasks = get_tasks_by_session(session_id, limit)
    else:
        tasks = get_recent_tasks(limit)
    
    # 解析 JSON 字段
    for task in tasks:
        if task.get("config_json"):
            try:
                task["config"] = json.loads(task["config_json"])
            except:
                task["config"] = {}
        if task.get("result_json"):
            try:
                task["result"] = json.loads(task["result_json"])
            except:
                task["result"] = {}
    
    return jsonify({"success": True, "tasks": tasks})


@task_bp.route("/tasks/<task_id>/results")
def get_task_result_detail(task_id):
    """获取任务测试结果详情"""
    try:
        from database import get_task, get_task_results
        DB_AVAILABLE = True
    except ImportError:
        DB_AVAILABLE = False
    
    if not DB_AVAILABLE:
        return jsonify({"success": False, "error": "数据库不可用"})
    
    task = get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    
    results = get_task_results(task_id)
    
    # 解析 JSON 字段
    if task.get("config_json"):
        try:
            task["config"] = json.loads(task["config_json"])
        except:
            task["config"] = {}
    if task.get("result_json"):
        try:
            task["result"] = json.loads(task["result_json"])
        except:
            task["result"] = {}
    
    return jsonify({"success": True, "task": task, "results": results})
