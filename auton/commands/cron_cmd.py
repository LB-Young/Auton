"""Cron Command — /cron (stub for M8)"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult


class CronCommand(Command):
    """定时任务管理命令（完整功能在 M8 — Cron 里程碑实现）"""
    name = "cron"
    description = "管理定时任务（list/add/edit/remove/run/enable/disable/logs）"
    patterns = [
        ("/cron",),
        ("/cron", "(list|add|edit|remove|run|enable|disable|logs)"),
        ("/cron", "add", "<name>"),
        ("/cron", "edit", "<name>"),
        ("/cron", "remove", "<name>"),
        ("/cron", "run", "<name>"),
        ("/cron", "enable", "<name>"),
        ("/cron", "disable", "<name>"),
        ("/cron", "logs", "<name>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        stubs = {
            "list": (
                "[stub] `/cron list` — 列出所有定时任务。\n"
                "M8 — Cron 里程碑将实现：\n"
                "  - 读取 ~/.auton/cron/jobs.yaml\n"
                "  - 显示任务名/调度规则/状态/下次执行时间\n\n"
                "存储位置：~/.auton/cron/jobs.yaml"
            ),
            "add": (
                "[stub] `/cron add <name> <schedule>` — 添加定时任务。\n"
                "调度格式：\n"
                "  - `at YYYY-MM-DD HH:MM` — 一次性\n"
                "  - `every 1h/30m/1d` — 间隔\n"
                "  - `cron 0 9 * * 1-5` — Cron 表达式"
            ),
            "edit": "[stub] `/cron edit <name>` — 编辑任务配置。",
            "remove": "[stub] `/cron remove <name>` — 删除定时任务。",
            "run": "[stub] `/cron run <name>` — 立即执行（跳过调度）。",
            "enable": "[stub] `/cron enable <name>` — 启用任务。",
            "disable": "[stub] `/cron disable <name>` — 禁用任务。",
            "logs": "[stub] `/cron logs <name>` — 查看任务执行日志。",
        }
        content = stubs.get(sub, stubs["list"])
        return CommandResult(content=content)
