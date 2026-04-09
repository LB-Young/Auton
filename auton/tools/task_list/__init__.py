"""TaskList Tool — 列出任务"""

from __future__ import annotations

from ..base import Tool, ToolResult


class TaskListTool(Tool):
    name = "task_list"
    description = "List all background tasks with their status"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status: pending, running, completed, failed, killed (omit for all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of tasks to return (default: 20)",
                    "default": 20,
                },
            },
        }

    async def execute(self, status: str | None = None, limit: int = 20) -> ToolResult:
        from auton.task import TaskManager

        tm = TaskManager()
        tasks = tm.list(status=status, limit=limit)

        if not tasks:
            msg = "暂无任务。"
            if status:
                msg = f"没有状态为 `{status}` 的任务。"
            return ToolResult(content=msg)

        stats = tm.stats()
        lines = [f"## 任务列表（{len(tasks)} 个"]
        if status:
            lines.append(f"状态: `{status}`")
        lines.append("）\n")

        by_status = stats.get("by_status", {})
        stat_parts = [f"{s}: {c}" for s, c in sorted(by_status.items())]
        lines.append(f"**总计**: {stats['total']} | {' | '.join(stat_parts)}\n")

        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "killed": "🛑",
        }

        for task in tasks:
            icon = status_icon.get(task.status, "?")
            time_str = task.created_at.strftime("%m-%d %H:%M")
            title_short = task.title[:40] + ("..." if len(task.title) > 40 else "")
            dep_note = f" (dep: {len(task.depends_on)})" if task.depends_on else ""
            lines.append(
                f"- {icon} `{task.id}` {time_str} — {title_short}{dep_note}"
            )

        return ToolResult(content="\n".join(lines))
