"""Tasks Command — /tasks (M9 Background Task System)"""

from __future__ import annotations

import json
from typing import Any

from ..task import TaskManager
from .base import Command, CommandResult


class TasksCommand(Command):
    """任务管理命令（M9 — Background Task System）"""

    name = "tasks"
    description = "管理后台异步任务（list/get/stop/retry）"
    patterns = [
        ("/tasks",),
        ("/tasks", "(list|get|stop|retry|stats)"),
        ("/tasks", "get", "<task_id>"),
        ("/tasks", "stop", "<task_id>"),
        ("/tasks", "retry", "<task_id>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        handler = {
            "list": self._list,
            "get": self._get,
            "stop": self._stop,
            "retry": self._retry,
            "stats": self._stats,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage())

    # ─── /tasks list ────────────────────────────────────────────────────────

    async def _list(self, args: dict) -> CommandResult:
        tm = TaskManager()
        status_filter = args.get("status")
        tasks = tm.list(status=status_filter, limit=50)

        if not tasks:
            msg = "暂无任务。"
            if status_filter:
                msg = f"没有状态为 `{status_filter}` 的任务。"
            return CommandResult(content=msg)

        stats = tm.stats()
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "killed": "🛑",
        }

        lines = [f"## 📋 任务列表\n"]
        if status_filter:
            lines.append(f"**过滤**: `{status_filter}`\n")

        # 统计
        by_status = stats.get("by_status", {})
        stat_parts = [f"{s}: {c}" for s, c in sorted(by_status.items())]
        lines.append(f"**总计**: {stats['total']} | {' | '.join(stat_parts)}\n")
        lines.append("---\n")

        for task in tasks[:30]:
            icon = status_icon.get(task.status, "?")
            time_str = task.created_at.strftime("%m-%d %H:%M")
            title = task.title[:45] + ("..." if len(task.title) > 45 else "")
            lines.append(
                f"**{icon} `{task.id}`** {time_str}\n"
                f"  {title}"
            )
            if task.status == "failed" and task.error:
                lines.append(f"  ❌ {task.error[:80]}")
            if task.depends_on:
                lines.append(f"  依赖: {', '.join(f'`{d}`' for d in task.depends_on[:3])}")
            lines.append("")

        if len(tasks) > 30:
            lines.append(f"_显示 30/{len(tasks)} 条，使用 `/tasks get <id>` 查看详情_")

        return CommandResult(content="\n".join(lines))

    # ─── /tasks get <task_id> ──────────────────────────────────────────────

    async def _get(self, args: dict) -> CommandResult:
        tm = TaskManager()
        task_id = args.get("<task_id>", "").strip()

        if not task_id:
            return CommandResult(content="用法：`/tasks get <task_id>`", success=False)

        task = tm.get(task_id)
        if task is None:
            return CommandResult(content=f"未找到任务：`{task_id}`", success=False)

        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "killed": "🛑",
        }
        icon = status_icon.get(task.status, "?")

        lines = [
            f"## {icon} 任务: `{task.id}`",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| 标题 | {task.title} |",
            f"| 状态 | `{task.status}` |",
            f"| 创建 | {task.created_at.strftime('%Y-%m-%d %H:%M')} |",
        ]

        if task.started_at:
            lines.append(f"| 开始 | {task.started_at.strftime('%Y-%m-%d %H:%M')} |")
        if task.completed_at:
            lines.append(f"| 完成 | {task.completed_at.strftime('%Y-%m-%d %H:%M')} |")
        if task.duration_seconds():
            lines.append(f"| 耗时 | {task.duration_seconds():.1f}s |")
        if task.error:
            lines.append(f"| 错误 | {task.error} |")

        if task.description:
            lines.append("")
            lines.append(f"**描述**: {task.description}")

        if task.output:
            lines.append("")
            lines.append("**输出**:")
            lines.append("```")
            lines.append(task.output[:3000])
            if len(task.output) > 3000:
                lines.append(f"...（共 {len(task.output)} 字符）")
            lines.append("```")

        if task.result:
            lines.append("")
            lines.append("**结果**:")
            lines.append("```json")
            lines.append(json.dumps(task.result, ensure_ascii=False, indent=2)[:2000])
            lines.append("```")

        if task.depends_on:
            lines.append("")
            lines.append(f"**依赖**: {', '.join(f'`{d}`' for d in task.depends_on)}")

        return CommandResult(content="\n".join(lines))

    # ─── /tasks stop <task_id> ────────────────────────────────────────────

    async def _stop(self, args: dict) -> CommandResult:
        tm = TaskManager()
        task_id = args.get("<task_id>", "").strip()

        if not task_id:
            return CommandResult(content="用法：`/tasks stop <task_id>`", success=False)

        task = tm.get(task_id)
        if task is None:
            return CommandResult(content=f"未找到任务：`{task_id}`", success=False)

        if task.terminal():
            return CommandResult(
                content=f"任务 `{task_id}` 已处于终止状态（`{task.status}`），无法停止。"
            )

        stopped = tm.stop(task_id)
        if stopped:
            return CommandResult(content=f"🛑 已终止任务 `{task_id}`")
        return CommandResult(content=f"停止失败。", success=False)

    # ─── /tasks retry <task_id> ──────────────────────────────────────────

    async def _retry(self, args: dict) -> CommandResult:
        tm = TaskManager()
        task_id = args.get("<task_id>", "").strip()

        if not task_id:
            return CommandResult(content="用法：`/tasks retry <task_id>`", success=False)

        task = tm.get(task_id)
        if task is None:
            return CommandResult(content=f"未找到任务：`{task_id}`", success=False)

        if task.status not in {"failed", "killed"}:
            return CommandResult(
                content=f"任务 `{task_id}` 状态为 `{task.status}`，只能重试 failed/killed 状态的任务。"
            )

        retried = tm.retry(task_id)
        if retried:
            return CommandResult(content=f"🔄 任务 `{task_id}` 已重置为 pending，可重新执行。")
        return CommandResult(content="重试失败。", success=False)

    # ─── /tasks stats ─────────────────────────────────────────────────────

    async def _stats(self, args: dict) -> CommandResult:
        tm = TaskManager()
        stats = tm.stats()

        by_status = stats.get("by_status", {})
        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "killed": "🛑",
        }

        lines = [
            "## 📊 任务统计\n",
            f"**目录**: `{stats['storage_dir']}`",
            f"**总计**: {stats['total']} 个任务\n",
            "",
            "| 状态 | 数量 |",
            "|------|------|",
        ]
        for s in ["pending", "running", "completed", "failed", "killed"]:
            count = by_status.get(s, 0)
            icon = status_icon.get(s, "?")
            lines.append(f"| {icon} {s} | {count} |")

        return CommandResult(content="\n".join(lines))

    # ─── 使用说明 ─────────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/tasks** — 任务管理命令

## 用法
```
/tasks list              — 列出所有任务（默认）
/tasks list running      — 只显示运行中的任务
/tasks get <task_id>     — 查看任务详情和输出
/tasks stop <task_id>   — 终止任务（→ killed）
/tasks retry <task_id>   — 重试失败任务（→ pending）
/tasks stats            — 显示任务统计
```

## 状态说明
| 状态 | 含义 |
|------|------|
| ⏳ pending | 等待执行 |
| 🔄 running | 执行中 |
| ✅ completed | 已完成 |
| ❌ failed | 执行失败 |
| 🛑 killed | 被手动终止 |

## 任务创建
使用 `task_create` 工具创建后台任务：
```
task_create(title="运行测试", description="pytest -v")
```

## 示例
```
/tasks list running
/tasks get task_xxx
/tasks stop task_xxx
```
"""
