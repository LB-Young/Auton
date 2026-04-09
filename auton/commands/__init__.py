"""Commands — 斜杠命令系统

所有 /xxx 命令注册到 CommandRegistry，由 SessionProcessor 统一调度。
推荐通过 `get_command_registry()` 获取：

    from auton.commands import get_command_registry
    registry = get_command_registry()
    command, args = registry.match("/help")
"""

from __future__ import annotations

from .base import Command, CommandResult, CommandRegistry
from .context import CommandContext
from .registry import get_command_registry

__all__ = [
    "Command",
    "CommandResult",
    "CommandRegistry",
    "CommandContext",
    "get_command_registry",
]
