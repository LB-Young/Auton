"""Session Command — /session"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult
from .context import CommandContext


class SessionCommand(Command):
    name = "session"
    description = "查看当前会话信息或历史会话"
    patterns = [
        ("/session",),
        ("/session", "current"),
        ("/session", "info"),
        ("/session", "list"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "current"

        if sub in ("current", "info"):
            return self._current_info(args)
        if sub == "list":
            return self._list_sessions(args)

        return self._current_info(args)

    def _current_info(self, args: dict[str, Any]) -> CommandResult:
        lines = [
            "# Current Session",
            "",
            f"- **Session ID**: `{self._session_id()}`",
            f"- **Status**: running",
            f"- **Messages**: (in memory)",
            f"- **Compaction count**: 0",
            "",
            "Use `/session list` to see historical sessions.",
        ]
        return CommandResult(content="\n".join(lines))

    def _list_sessions(self, args: dict[str, Any]) -> CommandResult:
        return CommandResult(
            content=(
                "[stub] `/session list` — Session history listing.\n"
                "Full session history available in:\n"
                "  项目模式：`{项目根}/.auton/memory/sessions/`\n"
                "  日期模式：`~/.auton/memory/dates/YYYY-MM-DD/sessions/`\n\n"
                "Use `auton replay <session_id>` to replay a session."
            ),
        )

    def _session_id(self) -> str:
        return "current-session"
