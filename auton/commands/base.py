"""Command Base — 命令基类与上下文

每个斜杠命令（/xxx）是一个 Command 对象，
注册到 CommandRegistry，由 SessionProcessor 统一调度。

命令格式：
  /help                 — 无参数
  /model <name>         — 带参数
  /compact              — 无参数
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from ..agent.session import Session


@dataclass
class CommandResult:
    """命令执行结果"""
    content: str  # 用户可见的输出内容
    success: bool = True
    error: str | None = None
    # 命令执行后是否需要 agent 继续处理
    handled: bool = True  # True = 命令已处理完，不需要 LLM；False = 需要继续发给 LLM
    # 附加元数据（如 plan_id 等，供调用方使用）
    metadata: dict[str, Any] | None = None


class Command(ABC):
    """命令基类

    子类必须实现：
      name:       命令名称（如 "help"、"model"）
      description: 命令描述（供 /help 显示）
      patterns:   匹配规则（见下面说明）

    可选覆盖：
      is_enabled():  动态判断命令是否可用

    匹配规则格式：
      ("/help",)                    — 精确匹配，无参数
      ("/model", "<name>")          — 固定参数
      ("/memory", "list"|"get"|...) — 多选一
      ("/memory", "list")           — 子命令

    参数解析后通过 self.args 访问（dict）。
    """

    name: str = ""
    description: str = ""
    patterns: list[tuple[str, ...]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Command.name is required")
        if not self.patterns:
            raise ValueError(f"Command.{self.name}: patterns is required")

    def is_enabled(self) -> bool:
        """动态判断命令是否可用（默认全部可用）"""
        return True

    @abstractmethod
    async def handle(self, args: dict[str, Any]) -> CommandResult:
        """执行命令，返回结果"""
        ...

    # ─── 匹配 ────────────────────────────────────────────────────────────

    def match(self, text: str) -> bool:
        """检查文本是否匹配此命令"""
        for pattern in self.patterns:
            if self._match_pattern(pattern, text):
                return True
        return False

    def _match_pattern(self, pattern: tuple[str, ...], text: str) -> bool:
        """检查文本是否匹配指定模式"""
        if not text.startswith("/"):
            return False

        parts = text.strip().split()
        cmd = parts[0].lower()

        # 匹配命令名称（支持 /help 和 /help@session1 格式）
        if cmd != f"/{self.name.lower()}":
            return False

        # 无参数模式
        if len(pattern) == 1:
            return len(parts) == 1

        # 有参数模式
        if len(parts) < 2:
            return False

        arg = parts[1].lower()

        # 多选一参数
        if pattern[1].startswith("("):
            # 提取选项列表: "(list|get|edit)"
            options_str = pattern[1][1:-1]
            options = options_str.split("|")
            if arg not in options:
                return False

        return True

    def parse(self, text: str) -> dict[str, Any] | None:
        """解析命令参数，返回参数字典或 None（不匹配时）"""
        for pattern in self.patterns:
            if self._match_pattern(pattern, text):
                return self._parse_args(pattern, text)
        return None

    def _parse_args(
        self,
        pattern: tuple[str, ...],
        text: str,
    ) -> dict[str, Any]:
        """根据 pattern 解析 text，返回参数字典"""
        parts = text.strip().split(maxsplit=len(pattern) - 1)

        args: dict[str, Any] = {}

        for i, segment in enumerate(pattern[1:], start=1):
            if i >= len(parts):
                break

            # 固定参数名
            if not segment.startswith("("):
                args[segment] = parts[i]
            else:
                # 多选一：无命名参数，只返回位置值
                args["_subcommand"] = parts[i]

        return args


# ─── 命令注册 ───────────────────────────────────────────────────────────────

class CommandRegistry:
    """命令注册表"""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        if command.name in self._commands:
            raise ValueError(f"Command already registered: {command.name}")
        self._commands[command.name] = command

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def list_commands(self, *, enabled_only: bool = True) -> list[Command]:
        if enabled_only:
            return [c for c in self._commands.values() if c.is_enabled()]
        return list(self._commands.values())

    def match(self, text: str) -> tuple[Command | None, dict[str, Any] | None]:
        """从文本中匹配命令，返回 (command, args) 或 (None, None)"""
        if not text.strip().startswith("/"):
            return None, None

        for command in self._commands.values():
            if command.match(text):
                args = command.parse(text)
                return command, args
        return None, None

    def help_text(self) -> str:
        """生成 /help 文本"""
        lines = ["## Available Commands\n"]
        for command in self.list_commands():
            lines.append(f"- **{command.name}** — {command.description}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._commands)

    def __contains__(self, name: str) -> bool:
        return name in self._commands
