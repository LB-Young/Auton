"""TaskGet Tool — 获取任务详情"""

from __future__ import annotations

import json

from ..base import Tool, ToolResult


class TaskGetTool(Tool):
    name = "task_get"
    description = "Get details of a specific task including output and status"

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The task ID to look up",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, task_id: str) -> ToolResult:
        from auton.task import TaskManager

        tm = TaskManager()
        task = tm.get(task_id)

        if task is None:
            return ToolResult(content=f"[task_get] 未找到任务: `{task_id}`")

        duration = ""
        if task.duration_seconds() is not None:
            secs = task.duration_seconds()
            if secs is not None:
                duration = f"{secs:.1f}s"

        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "killed": "🛑",
        }.get(task.status, "?")

        lines = [
            f"## {status_icon} 任务: {task.id}",
            f"**标题**: {task.title}",
            f"**状态**: `{task.status}`",
            f"**创建**: {task.created_at.strftime('%Y-%m-%d %H:%M')}",
        ]

        if task.started_at:
            lines.append(f"**开始**: {task.started_at.strftime('%Y-%m-%d %H:%M')}")
        if task.completed_at:
            lines.append(f"**完成**: {task.completed_at.strftime('%Y-%m-%d %H:%M')}")
        if duration:
            lines.append(f"**耗时**: {duration}")

        if task.description:
            lines.append(f"\n**描述**: {task.description}")

        if task.output:
            lines.append("\n**输出**:")
            lines.append("```")
            out = task.output[:3000]
            if len(task.output) > 3000:
                out += f"\n...（共 {len(task.output)} 字符）"
            lines.append(out)
            lines.append("```")

        if task.error:
            lines.append(f"\n**错误**: `{task.error}`")

        if task.result:
            lines.append("\n**结果**:")
            lines.append("```json")
            lines.append(json.dumps(task.result, ensure_ascii=False, indent=2)[:2000])
            lines.append("```")

        if task.depends_on:
            lines.append(f"\n**依赖**: {', '.join(f'`{d}`' for d in task.depends_on)}")

        return ToolResult(content="\n".join(lines))
