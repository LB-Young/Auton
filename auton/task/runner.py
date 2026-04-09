"""Task — 后台任务执行器

后台异步执行任务，推进任务状态机。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine

from loguru import logger

from .manager import TaskManager
from .types import Task, is_terminal


@dataclass
class RunningTask:
    """正在运行的任务"""
    task_id: str
    asyncio_task: asyncio.Task[Any]
    started_at: datetime = field(default_factory=datetime.now)
    callback: Callable[[str, str], None] | None = None  # (task_id, output) → void


class TaskRunner:
    """后台任务执行器

    用法：
        runner = TaskRunner(task_manager, max_concurrent=3)

        # 在事件循环中定期调用
        await runner.tick()
    """

    def __init__(
        self,
        task_manager: TaskManager | None = None,
        max_concurrent: int = 5,
    ) -> None:
        self.tm = task_manager or TaskManager()
        self.max_concurrent = max_concurrent
        self._running: dict[str, RunningTask] = {}  # task_id → RunningTask
        self._logger = logger.bind(name="TaskRunner")

    async def start(
        self,
        task_id: str,
        coro: Coroutine,
    ) -> bool:
        """启动任务（后台协程）"""
        if task_id in self._running:
            self._logger.warning("task {id} already running", id=task_id)
            return False

        if len(self._running) >= self.max_concurrent:
            self._logger.warning("max concurrent ({m}) reached, task {id} queued", m=self.max_concurrent, id=task_id)
            return False

        # 更新状态为 running
        self.tm.store.update_status(task_id, "running")

        # 创建 asyncio task
        async_task = asyncio.create_task(self._run_coro(task_id, coro))
        self._running[task_id] = RunningTask(task_id=task_id, asyncio_task=async_task)

        self._logger.info("started task {id} (running: {n})", id=task_id, n=len(self._running))
        return True

    async def _run_coro(self, task_id: str, coro: Coroutine) -> None:
        """包装协程执行，自动更新状态"""
        try:
            result = await coro
            self.tm.complete(task_id, output=str(result)[:5000] if result else "")
            self._logger.info("task {id} completed", id=task_id)
        except asyncio.CancelledError:
            self.tm.store.update_status(task_id, "killed", error="Cancelled by runner")
            self._logger.info("task {id} cancelled", id=task_id)
        except Exception as exc:
            self.tm.fail(task_id, error=str(exc))
            self._logger.error("task {id} failed: {e}", id=task_id, e=exc)
        finally:
            self._running.pop(task_id, None)

    async def stop(self, task_id: str) -> bool:
        """停止运行中的任务"""
        running = self._running.get(task_id)
        if running is None:
            return False

        running.asyncio_task.cancel()
        self._running.pop(task_id, None)
        self.tm.stop(task_id)
        self._logger.info("stopped task {id}", id=task_id)
        return True

    async def tick(self) -> int:
        """推进所有运行中的任务（主循环中定期调用）

        Returns:
            本次 tick 中新完成的任务数
        """
        done = 0
        for task_id, running in list(self._running.items()):
            if running.asyncio_task.done():
                self._running.pop(task_id, None)
                done += 1

        return done

    @property
    def running_count(self) -> int:
        return len(self._running)

    def is_running(self, task_id: str) -> bool:
        return task_id in self._running

    def get_running(self) -> list[str]:
        return list(self._running.keys())
