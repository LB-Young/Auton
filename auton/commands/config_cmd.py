"""Config Command — /config get/set"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult
from .context import CommandContext


class ConfigCommand(Command):
    name = "config"
    description = "读取或修改配置项"
    patterns = [
        ("/config",),
        ("/config", "get"),
        ("/config", "get", "<key>"),
        ("/config", "set"),
        ("/config", "set", "<key>"),
        ("/config", "set", "<key>", "<value>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        action = args.get("_subcommand") or args.get("get") or args.get("set") or ""

        if action == "get":
            key = args.get("<key>")
            if not key:
                return self._list_all()
            return self._get_value(key)

        if action == "set":
            key = args.get("<key>")
            value = args.get("<value>")
            if not key or value is None:
                return CommandResult(
                    content="Usage: `/config set <key> <value>`",
                    success=False,
                )
            return self._set_value(key, value)

        return self._list_all()

    def _list_all(self) -> CommandResult:
        lines = ["# Auton Configuration\n"]
        # 动态从配置生成
        lines.append("Use `/config get <key>` to read a specific key.")
        lines.append("Use `/config set <key> <value>` to modify (runtime only).")
        lines.append("")
        lines.append("## Config Keys")
        lines.append("- `llm.provider` — LLM provider (anthropic/minimax/openai/ollama)")
        lines.append("- `llm.model` — Model name")
        lines.append("- `memory.storage_dir` — Memory storage directory")
        lines.append("- `security.permission_mode` — Permission mode (default/auto/bypass/yolo)")
        lines.append("- `log.level` — Log level (DEBUG/INFO/WARNING/ERROR)")
        return CommandResult(content="\n".join(lines))

    def _get_value(self, key: str) -> CommandResult:
        # runtime config lookup stub
        return CommandResult(
            content=f"[stub] `/config get {key}` — Runtime config read not yet persisted.\n"
            f"Current value for `{key}`: (load from AutonConfig at runtime)",
        )

    def _set_value(self, key: str, value: str) -> CommandResult:
        return CommandResult(
            content=f"[stub] `/config set {key} {value}` — Runtime config set (not persisted).\n"
            f"Note: Config changes are runtime-only. Restart CLI to apply permanently.\n"
            f"Set `{key}` = `{value}`",
        )
