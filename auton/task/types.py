"""Task — 任务数据结构与状态机"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

# ─── 状态 ─────────────────────────────────────────────────────────────────────

TaskStatus = Literal["pending", "running", "completed", "failed", "killed"]
TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "failed", "killed"})


def is_terminal(status: str) -> bool:
    """判断是否为终止状态（不可再转移）"""
    return status in TERMINAL_STATUSES


def is_runnable(status: str) -> bool:
    """判断是否可运行"""
    return status == "pending"


def can_transition(from_status: str, to_status: str) -> bool:
    """判断状态转移是否合法"""
    if from_status == to_status:
        return True
    # pending → running/killed
    if from_status == "pending":
        return to_status in {"running", "killed"}
    # running → completed/failed/killed
    if from_status == "running":
        return to_status in {"completed", "failed", "killed"}
    # failed → pending (retry) — terminal 但允许重试
    if from_status == "failed":
        return to_status == "pending"
    # killed → terminal，不可转移
    if from_status == "killed":
        return False
    # completed → terminal，不可转移
    if from_status == "completed":
        return False
    return False


# ─── Task ─────────────────────────────────────────────────────────────────────

@dataclass
class Task:
    """后台任务"""

    title: str
    id: str = field(default_factory=lambda: f"task_{int(time.time())}_{uuid.uuid4().hex[:6]}")
    description: str = ""
    status: TaskStatus = "pending"
    created_by: str = "agent"           # "agent" | "user"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    depends_on: list[str] = field(default_factory=list)  # 依赖的任务 ID
    output: str = ""                    # 执行输出（截断至一定长度）
    result: dict = field(default_factory=dict)  # 结构化结果
    error: str = ""                    # 错误信息
    progress: float = 0.0              # 进度 0.0-1.0
    tags: list[str] = field(default_factory=list)
    parent_session: str | None = None  # 创建时所属 session

    def terminal(self) -> bool:
        return is_terminal(self.status)

    def runnable(self) -> bool:
        return is_runnable(self.status) and not self.unmet_dependencies()

    def unmet_dependencies(self) -> list[str]:
        """返回未满足的依赖 ID 列表"""
        # 依赖是否完成需要在 store 层检查，这里只做标记
        return []

    def duration_seconds(self) -> float | None:
        """返回执行时长（秒）"""
        if self.started_at is None:
            return None
        end = self.completed_at or datetime.now()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "depends_on": self.depends_on,
            "output": self.output[:5000] if self.output else "",
            "result": self.result,
            "error": self.error,
            "progress": self.progress,
            "tags": self.tags,
            "parent_session": self.parent_session,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        """从字典重建 Task"""
        from datetime import datetime

        def parse_dt(val) -> datetime | None:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(val)

        return cls(
            id=data["id"],
            title=data["title"],
            description=data.get("description", ""),
            status=data.get("status", "pending"),
            created_by=data.get("created_by", "agent"),
            created_at=parse_dt(data.get("created_at")) or datetime.now(),
            started_at=parse_dt(data.get("started_at")),
            completed_at=parse_dt(data.get("completed_at")),
            depends_on=data.get("depends_on", []),
            output=data.get("output", ""),
            result=data.get("result", {}),
            error=data.get("error", ""),
            progress=data.get("progress", 0.0),
            tags=data.get("tags", []),
            parent_session=data.get("parent_session"),
        )
