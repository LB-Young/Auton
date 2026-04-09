"""Agents Command — /agents（M12 Multi-Agent）"""

from __future__ import annotations

import json
from typing import Any

from ..agent import AgentManager
from .base import Command, CommandResult


class AgentsCommand(Command):
    """Agent 管理命令（M12 — Multi-Agent）"""

    name = "agents"
    description = "管理子 Agent（list/show/create）"
    patterns = [
        ("/agents",),
        ("/agents", "(list|show|get|abort)"),
        ("/agents", "show", "<name>"),
        ("/agents", "get", "<run_id>"),
        ("/agents", "abort", "<run_id>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"
        handler = {
            "list": self._list,
            "show": self._show,
            "get": self._get,
            "abort": self._abort,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage())

    # ─── /agents list ──────────────────────────────────────────────────────

    async def _list(self, args: dict) -> CommandResult:
        manager = AgentManager()
        agents = manager.list()

        source_icon = {
            "builtin": "🔧 builtin",
            "user": "👤 user",
            "project": "📁 project",
            "plugin": "🔌 plugin",
        }

        lines = ["## 🤖 Agent 列表\n"]
        lines.append(f"**总计**: {len(agents)} 个 agent\n")
        lines.append("---\n")

        for agent in agents:
            icon = source_icon.get(agent.source, agent.source)
            tools_str = ", ".join(agent.tools) if agent.tools else "all tools"
            lines.append(
                f"**`{agent.name}`**  {icon}\n"
                f"  {agent.description}\n"
                f"  tools: {tools_str}"
            )
            lines.append("")

        # 显示活跃运行
        runs = manager.list_runs()
        active = [r for r in runs if r.status in {"pending", "running"}]
        if active:
            lines.append("---\n")
            lines.append("## 🔄 活跃运行\n")
            for run in active[:10]:
                lines.append(
                    f"**`{run.run_id}`** {run.agent_name} "
                    f"[{run.status}] {run.created_at.strftime('%H:%M:%S')}"
                )

        return CommandResult(content="\n".join(lines))

    # ─── /agents show <name> ───────────────────────────────────────────────

    async def _show(self, args: dict) -> CommandResult:
        manager = AgentManager()
        name = args.get("<name>", "").strip()

        if not name:
            return CommandResult(content="用法：`/agents show <name>`", success=False)

        agent = manager.get(name)
        if not agent:
            return CommandResult(content=f"未找到 agent：`{name}`", success=False)

        lines = [
            f"## 🤖 Agent: `{agent.name}`",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| 名称 | `{agent.name}` |",
            f"| 来源 | {agent.source} |",
            f"| 模型 | {agent.model or '(inherit)'} |",
            f"| 权限 | {agent.permission_mode} |",
            f"| 最大轮次 | {agent.max_turns or '∞'} |",
            "",
            f"**描述**: {agent.description}",
            "",
            f"**工具**: {', '.join(agent.tools) if agent.tools else '全部工具'}",
            f"**禁用工具**: {', '.join(agent.disallowed_tools) if agent.disallowed_tools else '无'}",
            f"**Skills**: {', '.join(agent.skills) if agent.skills else '无'}",
            f"**MCP Servers**: {', '.join(agent.mcp_servers) if agent.mcp_servers else '无'}",
            "",
            "### System Prompt",
            "```",
            agent.system_prompt[:1000],
            "```",
        ]

        return CommandResult(content="\n".join(lines))

    # ─── /agents get <run_id> ──────────────────────────────────────────────

    async def _get(self, args: dict) -> CommandResult:
        manager = AgentManager()
        run_id = args.get("<run_id>", "").strip()

        if not run_id:
            return CommandResult(content="用法：`/agents get <run_id>`", success=False)

        run = manager.get_run(run_id)
        if not run:
            return CommandResult(content=f"未找到运行：`{run_id}`", success=False)

        status_icon = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "aborted": "🛑",
        }
        icon = status_icon.get(run.status, "?")

        lines = [
            f"## {icon} Agent Run: `{run.run_id}`",
            "",
            f"| 字段 | 值 |",
            f"|------|-----|",
            f"| Agent | `{run.agent_name}` |",
            f"| 状态 | `{run.status}` |",
            f"| 父会话 | `{run.parent_session_id}` |",
            f"| 创建 | {run.created_at.strftime('%Y-%m-%d %H:%M:%S')} |",
        ]

        if run.started_at:
            lines.append(f"| 开始 | {run.started_at.strftime('%Y-%m-%d %H:%M:%S')} |")
        if run.completed_at:
            lines.append(f"| 完成 | {run.completed_at.strftime('%Y-%m-%d %H:%M:%S')} |")

        lines.append("")
        lines.append(f"**Prompt**:\n```\n{run.prompt}\n```")

        if run.result:
            lines.append("")
            lines.append(f"**Result**:\n```\n{run.result[:2000]}\n```")
        if run.error:
            lines.append("")
            lines.append(f"**Error**: {run.error}")

        return CommandResult(content="\n".join(lines))

    # ─── /agents abort <run_id> ───────────────────────────────────────────

    async def _abort(self, args: dict) -> CommandResult:
        manager = AgentManager()
        run_id = args.get("<run_id>", "").strip()

        if not run_id:
            return CommandResult(content="用法：`/agents abort <run_id>`", success=False)

        run = manager.get_run(run_id)
        if not run:
            return CommandResult(content=f"未找到运行：`{run_id}`", success=False)

        if run.status not in {"pending", "running"}:
            return CommandResult(content=f"运行 `{run_id}` 状态为 `{run.status}`，无法中止。")

        success = manager.abort_run(run_id)
        if success:
            return CommandResult(content=f"🛑 已中止运行 `{run_id}`")
        return CommandResult(content=f"中止失败。", success=False)

    # ─── 使用说明 ─────────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/agents** — Agent 管理命令

## 用法
```
/agents list           — 列出所有 agent（默认）
/agents show <name>    — 查看 agent 详情
/agents get <run_id>   — 查看运行结果
/agents abort <run_id> — 中止运行中的 agent
```

## Agent 类型
| 类型 | 说明 |
|------|------|
| 🔧 builtin | 内置 agent（explore/coder/reviewer/planner） |
| 👤 user | 用户 agent（~/.auton/agents/） |
| 📁 project | 项目 agent（.auton/agents/） |
| 🔌 plugin | 插件 agent |

## 内置 Agent
| Agent | 用途 |
|-------|------|
| `explore` | 代码探索、分析项目结构 |
| `coder` | 写代码、改代码 |
| `reviewer` | 代码审查 |
| `planner` | 任务分解、方案设计 |

## 示例
```
/agents list
/agents show coder
/agents get abc123xyz
```
"""
