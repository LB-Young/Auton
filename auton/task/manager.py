"""Task — 任务管理器

提供任务创建、查询、停止、重试等操作。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger

from .store import TaskStore
from .types import Task, TaskStatus, is_terminal


class TaskManager:
    """任务管理器

    用法：
        tm = TaskManager()
        task = tm.create(title="运行测试", description="pytest -v")
        tasks = tm.list(status="running")
        tm.stop(task.id)
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.store = TaskStore(storage_dir)
        self._logger = logger.bind(name="TaskManager")

    def create(
        self,
        title: str,
        description: str = "",
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
        created_by: str = "agent",
        parent_session: str | None = None,
    ) -> Task:
        """创建新任务"""
        task = Task(
            title=title,
            description=description,
            depends_on=depends_on or [],
            tags=tags or [],
            created_by=created_by,
            parent_session=parent_session,
        )
        self.store.save(task)
        self._logger.info(
            "created task {id}: {title}",
            id=task.id,
            title=title[:50],
        )
        return task

    def get(self, task_id: str) -> Task | None:
        """获取任务详情"""
        return self.store.get(task_id)

    def list(
        self,
        status: TaskStatus | None = None,
        limit: int = 50,
    ) -> list[Task]:
        """列出任务（支持状态过滤）"""
        tasks = self.store.list(status=status)
        return tasks[:limit]

    def list_all(self) -> list[Task]:
        """列出所有任务"""
        return self.store.list()

    def stop(self, task_id: str) -> Task | None:
        """终止任务（→ killed）"""
        task = self.store.get(task_id)
        if task is None:
            return None
        if is_terminal(task.status):
            self._logger.warning("cannot stop terminal task {id} ({status})", id=task_id, status=task.status)
            return None

        updated = self.store.update_status(task_id, "killed")
        if updated:
            self._logger.info("task {id} killed", id=task_id)
        return updated

    def retry(self, task_id: str) -> Task | None:
        """重试失败任务（→ pending）"""
        task = self.store.get(task_id)
        if task is None:
            return None
        if task.status not in {"failed", "killed"}:
            self._logger.warning("cannot retry non-failed task {id} ({status})", id=task_id, status=task.status)
            return None

        updated = self.store.update_status(task_id, "pending", error="")
        if updated:
            self._logger.info("task {id} reset to pending for retry", id=task_id)
        return updated

    def get_runnable(self) -> list[Task]:
        """获取当前可运行的任务"""
        return self.store.get_runnable_tasks()

    def stats(self) -> dict:
        """获取任务统计"""
        all_tasks = self.store.list()
        counts: dict[str, int] = {}
        for t in all_tasks:
            counts[t.status] = counts.get(t.status, 0) + 1

        return {
            "total": len(all_tasks),
            "by_status": counts,
            "storage_dir": str(self.store.storage_dir),
        }

    def update_progress(self, task_id: str, progress: float, output: str | None = None) -> Task | None:
        """更新任务进度"""
        task = self.store.get(task_id)
        if task is None or task.status != "running":
            return None
        updated = self.store.update_status(
            task_id,
            "running",
            progress=max(0.0, min(1.0, progress)),
            output=output,
        )
        return updated

    def complete(
        self,
        task_id: str,
        output: str = "",
        result: dict | None = None,
    ) -> Task | None:
        """标记任务完成"""
        return self.store.update_status(
            task_id,
            "completed",
            output=output,
            result=result or {},
        )

    def fail(self, task_id: str, error: str, output: str = "") -> Task | None:
        """标记任务失败"""
        return self.store.update_status(
            task_id,
            "failed",
            error=error,
            output=output,
        )
