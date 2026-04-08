# -*- coding: utf-8 -*-
"""会话状态管理服务"""

import queue
import os
import json
import threading
from typing import Any, TypedDict
from datetime import datetime, timedelta


class TestResult(TypedDict):
    index: int
    question: str
    answer: str
    response_time: float
    success: bool


class AgentStatus(TypedDict):
    is_running: bool
    progress: int
    results: list[TestResult]
    generated_questions: list[str]
    current_url: str
    last_file: str
    last_knowledge: list[str] | str
    selected_persona: dict[str, Any]
    target_sites: list[int]
    bot_persona: str
    username: str
    password: str
    # 移动端测试相关字段
    platform: str  # "web" | "mobile"
    mobile_results: list[dict[str, Any]]
    mobile_report: str
    # 会话活动时间
    last_activity: datetime


# ========== 日志持久化配置 ==========
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 日志文件锁（线程安全）
_log_file_lock = threading.Lock()


def _get_log_file_path(session_id: str = "") -> str:
    """获取日志文件路径"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    if session_id:
        return os.path.join(LOG_DIR, f"session_{session_id}_{date_str}.log")
    return os.path.join(LOG_DIR, f"global_{date_str}.log")


def _write_log_to_file(log_entry: dict[str, Any], session_id: str = ""):
    """将日志写入文件（持久化）"""
    try:
        with _log_file_lock:
            log_file = _get_log_file_path(session_id or log_entry.get("session_id", ""))
            log_line = json.dumps(log_entry, ensure_ascii=False) + "\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_line)
    except Exception as e:
        print(f"[LOG ERROR] 写入日志文件失败: {e}")


def get_log_files(session_id: str = "", date_str: str = "") -> list[str]:
    """获取日志文件列表
    
    Args:
        session_id: 会话ID，为空则返回所有日志文件
        date_str: 日期字符串 YYYY-MM-DD，为空则返回所有日期
    
    Returns:
        日志文件路径列表
    """
    try:
        files = []
        for f in os.listdir(LOG_DIR):
            if not f.endswith(".log"):
                continue
            if session_id and f"session_{session_id}_" not in f:
                continue
            if date_str and date_str not in f:
                continue
            files.append(os.path.join(LOG_DIR, f))
        return sorted(files, reverse=True)
    except Exception:
        return []


def read_log_file(log_file: str, limit: int = 500) -> list[dict]:
    """读取日志文件内容
    
    Args:
        log_file: 日志文件路径
        limit: 最大行数
    
    Returns:
        日志条目列表
    """
    try:
        logs = []
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # 读取最后 limit 行
            for line in lines[-limit:]:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    pass
        return logs
    except Exception:
        return []


# ========== 全局状态 ==========
session_status: dict[str, AgentStatus] = {}
session_logs: dict[str, queue.Queue[dict[str, Any]]] = {}
session_last_activity: dict[str, datetime] = {}  # 会话最后活动时间
agent_status: AgentStatus = {
    "is_running": False, "progress": 0, "results": [],
    "generated_questions": [], "current_url": "", "last_file": "", "last_knowledge": "",
    "selected_persona": {}, "target_sites": [], "bot_persona": "",
    "username": "", "password": "",
    "platform": "web", "mobile_results": [], "mobile_report": "",
    "last_activity": datetime.now()
}
log_queue = queue.Queue()

# 会话清理配置
SESSION_TIMEOUT_MINUTES = 30  # 会话超时时间（分钟）
_cleanup_lock = threading.Lock()


def get_session_status(session_id: str) -> AgentStatus:
    """获取或创建session状态"""
    if session_id not in session_status:
        session_status[session_id] = {
            "is_running": False, "progress": 0, "results": [],
            "generated_questions": [], "current_url": "", "last_file": "",
            "last_knowledge": "",
            "selected_persona": {},
            "target_sites": [],
            "bot_persona": "",
            "username": "",
            "password": "",
            "platform": "web",
            "mobile_results": [],
            "mobile_report": "",
            "last_activity": datetime.now()
        }
    # 更新活动时间
    session_last_activity[session_id] = datetime.now()
    return session_status[session_id]


def get_session_logs(session_id: str) -> queue.Queue[dict[str, Any]]:
    """获取session日志队列"""
    if session_id not in session_logs:
        session_logs[session_id] = queue.Queue()
    return session_logs[session_id]


def log_message(message: str, level: str = "INFO", session_id: str = ""):
    """记录日志（内存 + 文件持久化）"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "time": timestamp, 
        "timestamp": full_timestamp,
        "level": level, 
        "message": message, 
        "session_id": session_id
    }
    
    # 1. 写入内存队列（实时推送）
    if session_id:
        get_session_logs(session_id).put(log_entry)
        session_last_activity[session_id] = datetime.now()
    else:
        log_queue.put(log_entry)
    
    # 2. 写入文件（持久化，重启后可查）
    _write_log_to_file(log_entry, session_id)
    
    # 3. 控制台输出
    print(f"[{timestamp}] [{level}] [{session_id or 'global'}] {message}")


def cleanup_inactive_sessions(timeout_minutes: int = SESSION_TIMEOUT_MINUTES) -> int:
    """清理不活跃的会话
    
    Args:
        timeout_minutes: 超时时间（分钟）
    
    Returns:
        清理的会话数量
    """
    cleaned = 0
    cutoff_time = datetime.now() - timedelta(minutes=timeout_minutes)
    
    with _cleanup_lock:
        # 找出需要清理的会话
        sessions_to_clean = [
            sid for sid, last_active in session_last_activity.items()
            if last_active < cutoff_time
        ]
        
        for sid in sessions_to_clean:
            # 检查是否正在运行测试
            status = session_status.get(sid, {})
            if status.get("is_running", False):
                continue  # 跳过正在运行的会话
            
            # 清理会话状态
            if sid in session_status:
                del session_status[sid]
            if sid in session_logs:
                del session_logs[sid]
            if sid in session_last_activity:
                del session_last_activity[sid]
            
            # 清理会话的 Agent 实例
            try:
                from app import cleanup_agent
                cleanup_agent(sid)
            except Exception:
                pass
            
            cleaned += 1
    
    if cleaned > 0:
        print(f"[Session] 清理了 {cleaned} 个不活跃会话")
    
    return cleaned


def start_cleanup_timer(interval_minutes: int = 10):
    """启动定时清理任务
    
    Args:
        interval_minutes: 清理间隔（分钟）
    """
    def cleanup_task():
        while True:
            try:
                cleanup_inactive_sessions()
            except Exception as e:
                print(f"[Session] 清理任务出错: {e}")
            
            # 等待下一次清理
            threading.Event().wait(interval_minutes * 60)
    
    thread = threading.Thread(target=cleanup_task, daemon=True)
    thread.start()
    print(f"[Session] 会话清理任务已启动，间隔 {interval_minutes} 分钟")
