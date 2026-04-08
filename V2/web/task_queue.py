# -*- coding: utf-8 -*-
"""
任务队列系统 - 支持 Web 服务与执行节点分离

架构:
┌─────────────────┐      ┌─────────────────┐
│  Web 服务 (云端) │ ───▶ │   任务队列(文件)  │
└─────────────────┘      └─────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────┐
         │         本地执行节点 (Windows)         │
         │     轮询任务 → 执行 Playwright → 上报  │
         └──────────────────────────────────────┘
"""
import os
import json
import uuid
import threading
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

# 任务状态
class TaskStatus(str, Enum):
    PENDING = "pending"        # 等待执行
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消

# 任务类型
class TaskType(str, Enum):
    SINGLE_TEST = "single_test"           # 单网站测试
    CONCURRENT_TEST = "concurrent_test"   # 并发测试
    GENERATE_QUESTIONS = "generate_questions"  # 生成问题

@dataclass
class TestTask:
    """测试任务"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    
    # 任务参数
    url: str = ""
    questions: list[str] | None = None
    question_count: int = 5
    worker_count: int = 1
    username: str = ""
    password: str = ""
    bot_name: str = ""
    knowledge_file: str = ""

    # 执行结果
    progress: int = 0
    result_message: str = ""
    report_path: str = ""
    error: str = ""
    logs: list[str] | None = None
    
    def __post_init__(self):
        if self.questions is None:
            self.questions = []
        if self.logs is None:
            self.logs = []
    
    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> 'TestTask':
        data = dict(data)  # 复制一份避免修改原数据
        data['task_type'] = TaskType(str(data['task_type']))
        data['status'] = TaskStatus(str(data['status']))
        return cls(**data)  # pyright: ignore[reportArgumentType]


class TaskQueue:
    """基于文件的任务队列（支持云端-本地分离）"""

    queue_dir: str
    tasks_file: str
    lock: threading.Lock

    def __init__(self, queue_dir: str):
        self.queue_dir = queue_dir
        self.tasks_file = os.path.join(queue_dir, "tasks.json")
        self.lock = threading.Lock()
        os.makedirs(queue_dir, exist_ok=True)
        self._ensure_tasks_file()
    
    def _ensure_tasks_file(self):
        """确保任务文件存在"""
        if not os.path.exists(self.tasks_file):
            self._save_tasks({})
    
    def _load_tasks(self) -> dict[str, dict[str, object]]:
        """加载所有任务"""
        try:
            with open(self.tasks_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data  # type: ignore[return-value]
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_tasks(self, tasks: dict[str, dict[str, object]]):
        """保存所有任务"""
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

    def create_task(self, task_type: TaskType, **kwargs: object) -> TestTask:
        """创建新任务"""
        task = TestTask(
            task_id=str(uuid.uuid4())[:8],
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=datetime.now().isoformat(),
            **kwargs  # pyright: ignore[reportArgumentType]
        )
        
        with self.lock:
            tasks = self._load_tasks()
            tasks[task.task_id] = task.to_dict()
            self._save_tasks(tasks)
        
        return task
    
    def get_task(self, task_id: str) -> TestTask | None:
        """获取任务"""
        tasks = self._load_tasks()
        if task_id in tasks:
            return TestTask.from_dict(tasks[task_id])
        return None
    
    def update_task(self, task: TestTask):
        """更新任务"""
        with self.lock:
            tasks = self._load_tasks()
            tasks[task.task_id] = task.to_dict()
            self._save_tasks(tasks)
    
    def get_pending_tasks(self) -> list[TestTask]:
        """获取所有待执行任务"""
        tasks = self._load_tasks()
        result = []
        for task_data in tasks.values():
            if task_data['status'] == TaskStatus.PENDING.value:
                result.append(TestTask.from_dict(task_data))
        # 按创建时间排序
        result.sort(key=lambda t: t.created_at)
        return result
    
    def get_running_tasks(self) -> list[TestTask]:
        """获取所有执行中任务"""
        tasks = self._load_tasks()
        result = []
        for task_data in tasks.values():
            if task_data['status'] == TaskStatus.RUNNING.value:
                result.append(TestTask.from_dict(task_data))
        return result
    
    def get_all_tasks(self, limit: int = 50) -> list[TestTask]:
        """获取所有任务（最近优先）"""
        tasks = self._load_tasks()
        result = [TestTask.from_dict(t) for t in tasks.values()]
        result.sort(key=lambda t: t.created_at, reverse=True)
        return result[:limit]
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self.get_task(task_id)
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            self.update_task(task)
            return True
        return False
    
    def cleanup_old_tasks(self, days: int = 7):
        """清理旧任务"""
        cutoff = datetime.now().timestamp() - (days * 24 * 3600)
        with self.lock:
            tasks = self._load_tasks()
            to_remove = []
            for task_id, task_data in tasks.items():
                try:
                    created = datetime.fromisoformat(str(task_data['created_at'])).timestamp()
                    if created < cutoff and task_data['status'] in [
                        TaskStatus.COMPLETED.value, 
                        TaskStatus.FAILED.value,
                        TaskStatus.CANCELLED.value
                    ]:
                        to_remove.append(task_id)
                except:
                    pass
            for task_id in to_remove:
                del tasks[task_id]
            self._save_tasks(tasks)


# 全局任务队列实例
_queue_instance: TaskQueue | None = None

def get_task_queue() -> TaskQueue:
    """获取全局任务队列实例"""
    global _queue_instance
    if _queue_instance is None:
        queue_dir = os.path.join(os.path.dirname(__file__), "task_data")
        _queue_instance = TaskQueue(queue_dir)
    return _queue_instance
