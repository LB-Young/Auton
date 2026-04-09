"""TaskStop Tool — 停止任务"""

from __future__ import annotations

from ..base import Tool, ToolResult


class TaskStopTool(Tool):
    name = "task_stop"
    description = "Stop a running or pending background task"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to stop",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str) -> ToolResult:
        from auton.task import TaskManager

        tm = TaskManager()
        task = tm.get(task_id)

        if task is None:
            return ToolResult(content=f"[task_stop] 未找到任务: `{task_id}`")

        if task.terminal():
            return ToolResult(
                content=f"[task_stop] 任务 `{task_id}` 已是终止状态（`{task.status}`），无法停止。"
            )

        stopped = tm.stop(task_id)
        if stopped:
            return ToolResult(
                content=f"🛑 已终止任务 `{task_id}`（{task.title[:50]}）"
            )
        return ToolResult(content="[task_stop] 终止失败。", error="unknown error")
