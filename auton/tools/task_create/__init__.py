"""TaskCreate Tool — 创建后台任务"""

from __future__ import annotations

from ..base import Tool, ToolResult


class TaskCreateTool(Tool):
    name = "task_create"
    description = "Create a background task for long-running operations"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title (short, descriptive)",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed task description and instructions",
                },
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Task IDs that must complete before this task runs",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for organizing tasks",
                },
            },
            "required": ["title"],
        }

    async def execute(
        self,
        title: str,
        description: str = "",
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> ToolResult:
        from auton.task import TaskManager

        tm = TaskManager()
        task = tm.create(
            title=title,
            description=description,
            depends_on=depends_on or None,
            tags=tags or [],
            created_by="agent",
        )

        lines = [
            f"✅ 任务已创建: `{task.id}`",
            f"**标题**: {task.title}",
            f"**状态**: {task.status}",
        ]
        if task.description:
            lines.append(f"**描述**: {task.description}")
        if task.depends_on:
            lines.append(f"**依赖**: {', '.join(f'`{d}`' for d in task.depends_on)}")

        return ToolResult(content="\n".join(lines))
