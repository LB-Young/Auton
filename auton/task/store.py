"""Task — 任务持久化存储

每任务一个 JSON 文件 + 索引文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from .types import Task, TaskStatus, is_terminal, can_transition


class TaskStore:
    """任务存储（JSON 文件持久化）"""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path("~/.auton/tasks").expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_dir / "index.jsonl"
        self._logger = logger.bind(name="TaskStore")

    # ─── 基础 CRUD ─────────────────────────────────────────────────────────

    def save(self, task: Task) -> None:
        """保存任务（新建或更新）"""
        # 写任务文件
        task_path = self._task_path(task.id)
        task_path.write_text(
            json.dumps(task.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 更新索引
        self._update_index(task.id, task.status)
        self._logger.debug("saved task {id} status={status}", id=task.id, status=task.status)

    def get(self, task_id: str) -> Task | None:
        """获取任务"""
        path = self._task_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Task.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            self._logger.warning("failed to load task {id}: {e}", id=task_id, e=exc)
            return None

    def delete(self, task_id: str) -> bool:
        """删除任务文件"""
        task_path = self._task_path(task_id)
        if task_path.exists():
            task_path.unlink()
            self._remove_from_index(task_id)
            return True
        return False

    # ─── 列表查询 ─────────────────────────────────────────────────────────

    def list(self, status: str | None = None) -> list[Task]:
        """列出所有任务（可选状态过滤）"""
        tasks: list[Task] = []
        for path in self.storage_dir.glob("*.json"):
            if path.name == "index.jsonl":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                task = Task.from_dict(data)
                if status is None or task.status == status:
                    tasks.append(task)
            except (json.JSONDecodeError, KeyError):
                continue

        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def count(self, status: str | None = None) -> int:
        """统计任务数量"""
        return len(self.list(status=status))

    # ─── 状态更新 ─────────────────────────────────────────────────────────

    def update_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        output: str | None = None,
        result: dict | None = None,
        error: str | None = None,
        progress: float | None = None,
    ) -> Task | None:
        """更新任务状态（带合法性校验）"""
        task = self.get(task_id)
        if task is None:
            return None

        if not can_transition(task.status, new_status):
            self._logger.warning(
                "invalid transition {t}: {f} → {n}",
                t=task_id,
                f=task.status,
                n=new_status,
            )
            return None

        from datetime import datetime

        task.status = new_status

        if new_status == "running" and task.started_at is None:
            task.started_at = datetime.now()

        if is_terminal(new_status):
            task.completed_at = datetime.now()

        if output is not None:
            task.output = output
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if progress is not None:
            task.progress = progress

        self.save(task)
        return task

    def append_output(self, task_id: str, chunk: str) -> None:
        """追加输出内容"""
        task = self.get(task_id)
        if task is None:
            return
        task.output += chunk
        # 限制输出长度
        if len(task.output) > 50_000:
            task.output = task.output[-50_000:]
        self.save(task)

    # ─── 依赖解析 ─────────────────────────────────────────────────────────

    def get_runnable_tasks(self) -> list[Task]:
        """获取可运行的任务（pending + 依赖已满足）"""
        tasks = self.list(status="pending")
        runnable: list[Task] = []

        for task in tasks:
            if self._dependencies_met(task):
                runnable.append(task)

        return runnable

    def _dependencies_met(self, task: Task) -> bool:
        """检查任务的所有依赖是否已满足（completed）"""
        if not task.depends_on:
            return True
        for dep_id in task.depends_on:
            dep = self.get(dep_id)
            if dep is None:
                # 依赖不存在当已完成
                continue
            if dep.status != "completed":
                return False
        return True

    # ─── 索引 ─────────────────────────────────────────────────────────────

    def _task_path(self, task_id: str) -> Path:
        return self.storage_dir / f"{task_id}.json"

    def _update_index(self, task_id: str, status: str) -> None:
        """更新索引文件"""
        index: dict[str, str] = {}
        if self.index_path.exists():
            try:
                index = json.loads(self.index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                index = {}

        index[task_id] = status
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False),
            encoding="utf-8",
        )

    def _remove_from_index(self, task_id: str) -> None:
        """从索引中移除"""
        if not self.index_path.exists():
            return
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
            index.pop(task_id, None)
            self.index_path.write_text(
                json.dumps(index, ensure_ascii=False),
                encoding="utf-8",
            )
        except json.JSONDecodeError:
            pass
