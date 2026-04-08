"""
任务持久化模块
使用 SQLite 存储任务历史和测试结果
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

# 数据库路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "tasks.db")


def ensure_db_dir():
    """确保数据库目录存在"""
    os.makedirs(DATA_DIR, exist_ok=True)


@contextmanager
def get_connection():
    """获取数据库连接的上下文管理器"""
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """初始化数据库表"""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 任务表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                session_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                config_json TEXT,
                result_json TEXT,
                error_message TEXT
            )
        """)
        
        # 测试结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                site_name TEXT,
                question TEXT,
                answer TEXT,
                response_time REAL,
                success INTEGER,
                judged INTEGER DEFAULT 0,
                judge_result TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(task_id)
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_results_task ON test_results(task_id)")
        
        conn.commit()
        print(f"[DB] 数据库初始化完成: {DB_PATH}")


def create_task(task_id: str, session_id: str, task_type: str, config: Optional[Dict[str, Any]] = None) -> bool:
    """创建新任务"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, session_id, task_type, config_json, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (task_id, session_id, task_type, json.dumps(config) if config else None))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] 创建任务失败: {e}")
        return False


def update_task_status(task_id: str, status: str, error: Optional[str] = None) -> bool:
    """更新任务状态"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if status == "running":
                cursor.execute("""
                    UPDATE tasks SET status = ?, started_at = CURRENT_TIMESTAMP
                    WHERE task_id = ?
                """, (status, task_id))
            elif status in ("completed", "failed", "cancelled"):
                cursor.execute("""
                    UPDATE tasks SET status = ?, completed_at = CURRENT_TIMESTAMP, error_message = ?
                    WHERE task_id = ?
                """, (status, error, task_id))
            else:
                cursor.execute("""
                    UPDATE tasks SET status = ? WHERE task_id = ?
                """, (status, task_id))
            
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] 更新任务状态失败: {e}")
        return False


def save_task_result(task_id: str, result: Dict[str, Any]) -> bool:
    """保存任务结果"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tasks SET result_json = ? WHERE task_id = ?
            """, (json.dumps(result), task_id))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] 保存任务结果失败: {e}")
        return False


def save_test_result(task_id: str, site_name: str, question: str, answer: str,
                     response_time: float, success: bool, judge_result: Optional[str] = None) -> bool:
    """保存单个测试结果"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO test_results 
                (task_id, site_name, question, answer, response_time, success, judge_result, judged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (task_id, site_name, question, answer, response_time, 
                  1 if success else 0, judge_result, 1 if judge_result else 0))
            conn.commit()
            return True
    except Exception as e:
        print(f"[DB] 保存测试结果失败: {e}")
        return False


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务详情"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None


def get_tasks_by_session(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取会话的任务列表"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tasks WHERE session_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (session_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_recent_tasks(limit: int = 100) -> List[Dict[str, Any]]:
    """获取最近的任务列表"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def get_task_results(task_id: str) -> List[Dict[str, Any]]:
    """获取任务的测试结果"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM test_results WHERE task_id = ?
        """, (task_id,))
        return [dict(row) for row in cursor.fetchall()]


def cleanup_old_tasks(days: int = 30) -> int:
    """清理旧任务"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            # 先删除关联的测试结果
            cursor.execute("""
                DELETE FROM test_results WHERE task_id IN (
                    SELECT task_id FROM tasks 
                    WHERE created_at < datetime('now', ?)
                )
            """, (f'-{days} days',))
            # 再删除任务
            cursor.execute("""
                DELETE FROM tasks WHERE created_at < datetime('now', ?)
            """, (f'-{days} days',))
            deleted = cursor.rowcount
            conn.commit()
            return deleted
    except Exception as e:
        print(f"[DB] 清理旧任务失败: {e}")
        return 0


# 初始化数据库
init_db()
