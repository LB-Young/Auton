"""Auton Task — 后台任务系统

任务状态机：pending → running → completed / failed / killed
"""

from .types import (
    Task,
    TaskStatus,
    is_terminal,
    is_runnable,
    can_transition,
)
from .store import TaskStore
from .manager import TaskManager
from .runner import TaskRunner, RunningTask

__all__ = [
    # 类型
    "Task",
    "TaskStatus",
    "RunningTask",
    # 状态判断
    "is_terminal",
    "is_runnable",
    "can_transition",
    # 核心
    "TaskStore",
    "TaskManager",
    "TaskRunner",
]
