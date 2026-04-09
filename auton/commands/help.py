"""Help Command — /help"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult, CommandRegistry


class HelpCommand(Command):
    name = "help"
    description = "显示所有可用命令及其说明"
    patterns = [("/help",)]

    def __init__(self, registry: CommandRegistry) -> None:
        super().__init__()
        self.registry = registry

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        lines = [
            "# Auton Commands",
            "",
            "## Slash Commands",
            "",
        ]

        for cmd in self.registry.list_commands():
            lines.append(f"**/{cmd.name}** — {cmd.description}")
            for pattern in cmd.patterns:
                if len(pattern) > 1:
                    lines.append(f"  Usage: `{pattern[0]} {pattern[1]}`")

        lines.append("")
        lines.append("## Tips")
        lines.append("- Commands are processed locally, without LLM")
        lines.append("- Use `/help <command>` for detailed command info")

        return CommandResult(content="\n".join(lines))
