# -*- coding: utf-8 -*-
"""进程管理服务"""

import sys
import subprocess
import threading
from services.session_service import log_message

# 进程管理 - 按会话和测试类型隔离
# key: f"{session_id}_{test_type}" (test_type: "single" | "concurrent" | "check" | "simuser")
session_processes: dict[str, subprocess.Popen] = {}
session_processes_lock = threading.Lock()


def kill_process(session_id: str, test_type: str):
    """强制终止指定会话和测试类型的进程
    
    Args:
        session_id: 会话ID
        test_type: 测试类型 ("single" | "concurrent" | "check" | "simuser")
    """
    process_key = f"{session_id}_{test_type}"
    with session_processes_lock:
        process = session_processes.get(process_key)
        if process is not None:
            try:
                log_message(f"[INFO] 正在终止进程 {process_key}...", "WARN")
                # Windows: 使用 taskkill 强制终止进程树
                if sys.platform == "win32":
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except:
                        pass
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                            capture_output=True, timeout=5
                        )
                    except:
                        pass
                else:
                    # Linux/Mac
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except:
                        try:
                            process.kill()
                            process.wait(timeout=2)
                        except:
                            pass
                log_message(f"[INFO] 进程 {process_key} 已终止", "WARN")
            except Exception as e:
                log_message(f"[WARN] 终止进程时出错: {e}", "WARN")
            finally:
                session_processes.pop(process_key, None)


def register_process(session_id: str, test_type: str, process: subprocess.Popen):
    """注册进程到进程管理器"""
    process_key = f"{session_id}_{test_type}"
    with session_processes_lock:
        session_processes[process_key] = process


def unregister_process(session_id: str, test_type: str):
    """从进程管理器移除进程"""
    process_key = f"{session_id}_{test_type}"
    with session_processes_lock:
        session_processes.pop(process_key, None)
