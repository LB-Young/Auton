"""Workflow Command — /workflow (M10 Workflow Engine)"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from ..workflow import (
    DSLParser,
    RunStore,
    WorkflowDefinition,
    WorkflowRunner,
    WorkflowStore,
)
from .base import Command, CommandResult


class WorkflowCommand(Command):
    """工作流管理命令（M10 — Workflow Engine）"""

    name = "workflow"
    description = "管理工作流（list/show/run/pause/resume/stop/log）"
    patterns = [
        ("/workflow",),
        ("/workflow", "(list|show|run|pause|resume|stop|delete)"),
        ("/workflow", "show", "<wf_id>"),
        ("/workflow", "run", "<wf_id>"),
        ("/workflow", "pause", "<run_id>"),
        ("/workflow", "resume", "<run_id>"),
        ("/workflow", "stop", "<run_id>"),
        ("/workflow", "log", "<run_id>"),
        ("/workflow", "delete", "<wf_id>"),
        ("/workflow", "create"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._logger = logger.bind(name="WorkflowCommand")
        self._runner: WorkflowRunner | None = None
        self._pending_runs: dict[str, str] = {}  # run_id → workflow_id

    @property
    def runner(self) -> WorkflowRunner:
        if self._runner is None:
            self._runner = WorkflowRunner()
        return self._runner

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        handler = {
            "list": self._list,
            "show": self._show,
            "run": self._run,
            "pause": self._pause,
            "resume": self._resume,
            "stop": self._stop,
            "log": self._log,
            "delete": self._delete,
            "create": self._create,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage())

    # ─── /workflow list ─────────────────────────────────────────────────────

    async def _list(self, _args: dict) -> CommandResult:
        wf_store = WorkflowStore()
        run_store = RunStore()

        workflows = wf_store.list()
        runs = run_store.list()[:10]

        if not workflows and not runs:
            return CommandResult(content=self._empty_state())

        lines = ["## 工作流\n"]

        if workflows:
            lines.append(f"**定义**: {len(workflows)} 个\n")
            for wf in workflows[:20]:
                lines.append(f"- `{wf.id}` — {wf.name} ({len(wf.steps)} 步骤)")

        if runs:
            lines.append(f"\n**最近执行**: {len(runs)} 条\n")
            status_icon = {
                "idle": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "breakpoint": "⏸️",
                "cancelled": "🛑",
            }
            for r in runs[:5]:
                icon = status_icon.get(r.status, "?")
                time_str = r.created_at.strftime("%m-%d %H:%M")
                wf_name = r.workflow_name or r.workflow_id
                lines.append(f"{icon} `{r.id}` {time_str} — {wf_name}")

        if len(workflows) > 20:
            lines.append(f"\n_显示 20/{len(workflows)} 个_")

        return CommandResult(content="\n".join(lines))

    def _empty_state(self) -> str:
        return (
            "**当前没有工作流。**\n\n"
            "**创建工作流**：\n"
            "在工作流文件中定义 YAML（保存为 `~/.auton/workflows/<name>.autowf`），\n"
            "或使用 `/workflow create` 粘贴 YAML 内容。\n\n"
            "**工作流示例**：\n"
            "```yaml\n"
            "id: wf_demo\n"
            "name: 演示工作流\n"
            "steps:\n"
            "  - id: step1\n"
            "    type: task\n"
            "    task:\n"
            "      title: 打印消息\n"
            "```"
        )

    # ─── /workflow show <wf_id> ──────────────────────────────────────────

    async def _show(self, args: dict) -> CommandResult:
        wf_store = WorkflowStore()
        wf_id = args.get("<wf_id>", "").strip()

        if not wf_id:
            return CommandResult(content="用法：`/workflow show <wf_id>`", success=False)

        wf = wf_store.load(wf_id)
        if wf is None:
            return CommandResult(content=f"未找到工作流：`{wf_id}`", success=False)

        lines = [
            f"## 工作流: {wf.name}",
            f"**ID**: `{wf.id}`",
            f"**版本**: {wf.version}",
            f"**断点**: {', '.join(wf.breakpoints) or '无'}",
            f"**失败策略**: {wf.on_failure}\n",
            "",
            "### 步骤\n",
        ]

        for step in wf.steps:
            dep_note = f" (依赖: {', '.join(step.depends_on)})" if step.depends_on else ""
            bp_note = " 🔖" if step.breakpoints else ""
            lines.append(f"- `{step.id}` **{step.type}**{bp_note}{dep_note}")
            if step.description:
                lines.append(f"  {step.description}")

        return CommandResult(content="\n".join(lines))

    # ─── /workflow run <wf_id> ──────────────────────────────────────────

    async def _run(self, args: dict) -> CommandResult:
        wf_id = args.get("<wf_id>", "").strip()
        if not wf_id:
            return CommandResult(content="用法：`/workflow run <wf_id> [--param key=value]`", success=False)

        # 提取参数（简化版：取剩余文本作为 --param）
        raw_text = args.get("raw", "")
        params = self._parse_params(raw_text)

        run = self.runner.create_run(wf_id, params=params)
        if run is None:
            return CommandResult(content=f"未找到工作流：`{wf_id}`", success=False)

        lines = [
            f"✅ **执行实例已创建**",
            f"**Run ID**: `{run.id}`",
            f"**工作流**: {run.workflow_name}",
            f"**状态**: {run.status}",
        ]
        if params:
            param_str = ", ".join(f"`{k}={v}`" for k, v in params.items())
            lines.append(f"**参数**: {param_str}")

        lines.append("")
        lines.append(f"正在异步执行... 使用 `/workflow log {run.id}` 查看进度。")
        lines.append(f"\n控制命令：")
        lines.append(f"- `/workflow pause {run.id}` — 暂停")
        lines.append(f"- `/workflow stop {run.id}` — 取消")

        # 异步启动执行（不阻塞）
        asyncio.create_task(self.runner.run(run.id))

        return CommandResult(content="\n".join(lines))

    def _parse_params(self, raw: str) -> dict:
        """从文本中提取 --param key=value"""
        import re
        params: dict = {}
        for m in re.finditer(r"--param\s+(\w+)=(.+?)(?=\s+--param|$)", raw):
            params[m.group(1)] = m.group(2).strip()
        return params

    # ─── /workflow pause <run_id> ──────────────────────────────────────

    async def _pause(self, args: dict) -> CommandResult:
        run_id = args.get("<run_id>", "").strip()
        if not run_id:
            return CommandResult(content="用法：`/workflow pause <run_id>`", success=False)

        run = self.runner.pause(run_id)
        if run is None:
            return CommandResult(content=f"未找到执行：`{run_id}`", success=False)

        icon = "⏸️" if run.status == "breakpoint" else "❌"
        lines = [
            f"{icon} **执行已暂停**",
            f"**Run ID**: `{run.id}`",
            f"**状态**: {run.status}",
        ]
        if run.breakpoint_step:
            lines.append(f"**断点步骤**: `{run.breakpoint_step}`")
        if run.breakpoint_reason:
            lines.append(f"**原因**: {run.breakpoint_reason}")

        lines.append(f"\n恢复执行：`/workflow resume {run.id}`")

        return CommandResult(content="\n".join(lines))

    # ─── /workflow resume <run_id> ──────────────────────────────────────

    async def _resume(self, args: dict) -> CommandResult:
        run_id = args.get("<run_id>", "").strip()
        if not run_id:
            return CommandResult(content="用法：`/workflow resume <run_id>`", success=False)

        run = self.runner.get_run(run_id)
        if run is None:
            return CommandResult(content=f"未找到执行：`{run_id}`", success=False)
        if run.status != "breakpoint":
            return CommandResult(
                content=f"执行 `{run_id}` 不在断点状态（当前：`{run.status}`），无法恢复。",
                success=False,
            )

        lines = [
            f"🔄 **正在恢复执行**",
            f"**Run ID**: `{run.id}`",
            f"**从步骤**: `{run.finished_step_id}` 继续",
        ]
        lines.append(f"\n查看进度：`/workflow log {run.id}`")

        asyncio.create_task(self.runner.resume(run_id))

        return CommandResult(content="\n".join(lines))

    # ─── /workflow stop <run_id> ────────────────────────────────────────

    async def _stop(self, args: dict) -> CommandResult:
        run_id = args.get("<run_id>", "").strip()
        if not run_id:
            return CommandResult(content="用法：`/workflow stop <run_id>`", success=False)

        run = self.runner.stop(run_id)
        if run is None:
            return CommandResult(content=f"未找到执行：`{run_id}`", success=False)

        return CommandResult(content=f"🛑 执行 `{run_id}` 已取消。")

    # ─── /workflow log <run_id> ─────────────────────────────────────────

    async def _log(self, args: dict) -> CommandResult:
        run_id = args.get("<run_id>", "").strip()
        if not run_id:
            return CommandResult(content="用法：`/workflow log <run_id>`", success=False)

        run = self.runner.get_run(run_id)
        if run is None:
            return CommandResult(content=f"未找到执行：`{run_id}`", success=False)

        status_icon = {
            "idle": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "breakpoint": "⏸️",
            "cancelled": "🛑",
        }
        icon = status_icon.get(run.status, "?")

        lines = [
            f"## {icon} 执行: `{run.id}`",
            f"**工作流**: {run.workflow_name}",
            f"**状态**: `{run.status}`",
            f"**创建**: {run.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        ]

        if run.started_at:
            lines.append(f"**开始**: {run.started_at.strftime('%H:%M:%S')}")
        if run.completed_at:
            lines.append(f"**完成**: {run.completed_at.strftime('%H:%M:%S')}")
        if run.duration_seconds():
            lines.append(f"**耗时**: {run.duration_seconds():.1f}s")

        if run.current_step:
            lines.append(f"**当前步骤**: `{run.current_step}`")

        if run.error:
            lines.append(f"\n**错误**: `{run.error}`")

        # 步骤状态表
        if run.step_states:
            lines.append("\n### 步骤状态\n")
            lines.append("| 步骤 | 状态 |")
            lines.append("|------|------|")
            for sid, sstatus in run.step_states.items():
                icon2 = status_icon.get(sstatus, "?")
                lines.append(f"| `{sid}` | {icon2} `{sstatus}` |")

        # 执行日志
        if run.logs:
            lines.append(f"\n### 执行日志（共 {len(run.logs)} 条）\n")
            for entry in run.logs[-10:]:
                at = entry.get("at", "")
                if "T" in at:
                    at = at.split("T")[1][:8]
                lines.append(f"- {at} **{entry['event']}**" + (f" ({entry.get('detail', '')})" if entry.get("detail") else ""))

        return CommandResult(content="\n".join(lines))

    # ─── /workflow delete <wf_id> ──────────────────────────────────────

    async def _delete(self, args: dict) -> CommandResult:
        wf_store = WorkflowStore()
        wf_id = args.get("<wf_id>", "").strip()
        if not wf_id:
            return CommandResult(content="用法：`/workflow delete <wf_id>`", success=False)

        deleted = wf_store.delete(wf_id)
        if deleted:
            return CommandResult(content=f"已删除工作流：`{wf_id}`")
        return CommandResult(content=f"工作流 `{wf_id}` 不存在。")

    # ─── /workflow create ────────────────────────────────────────────────

    async def _create(self, args: dict) -> CommandResult:
        """从 YAML 文本创建工作流（需要用户提供 YAML 内容）"""
        return CommandResult(
            content=(
                "**创建工作流**\n\n"
                "请粘贴 YAML 工作流定义内容。\n\n"
                "**格式示例**：\n"
                "```yaml\n"
                "id: wf_hello\n"
                "name: 演示工作流\n"
                "steps:\n"
                "  - id: greet\n"
                "    type: task\n"
                "    task:\n"
                "      title: 打印欢迎\n"
                "```\n\n"
                "直接粘贴 YAML 内容即可保存。"
            )
        )

    # ─── 帮助 ─────────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/workflow** — 工作流管理命令

## 用法
```
/workflow list                 — 列出所有工作流和最近执行
/workflow show <wf_id>        — 查看工作流详情
/workflow run <wf_id>        — 运行工作流
/workflow run <wf_id> --param env=prod  — 带参数运行
/workflow pause <run_id>     — 暂停（触发断点）
/workflow resume <run_id>   — 从断点恢复
/workflow stop <run_id>      — 取消执行
/workflow log <run_id>        — 查看执行日志
/workflow delete <wf_id>     — 删除工作流定义
```

## 步骤类型
| 类型 | 说明 |
|------|------|
| `task` | 关联 M9 Task 执行 |
| `condition` | 条件分支（if/else） |
| `checkpoint` | 断点 |
| `input` | 等待用户输入 |
| `output` | 输出结果 |

## 状态
| 状态 | 含义 |
|------|------|
| ⏳ idle | 等待执行 |
| 🔄 running | 执行中 |
| ✅ completed | 已完成 |
| ❌ failed | 失败 |
| ⏸️ breakpoint | 断点暂停 |
| 🛑 cancelled | 已取消 |

## 示例
```
/workflow list
/workflow show wf_deploy
/workflow run wf_deploy --param env=prod
/workflow log run_xxx
```
"""
