"""Command Context — 命令执行上下文

传递给每个命令 handler，包含执行命令所需的全部状态。
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from ..agent.session import Session
    from ..agent.session_store import SessionStore
    from ..core.config import AutonConfig
    from ..llm.base import LLMProvider


@dataclass
class CommandContext:
    """命令执行上下文——命令 handler 的所有依赖通过此对象传入"""

    # ─── 会话状态 ─────────────────────────────────────────────────────────
    session: "Session"
    session_store: "SessionStore"

    # ─── LLM（部分命令需要切换 provider）──────────────────────────────────
    llm: "LLMProvider"

    # ─── 配置 ──────────────────────────────────────────────────────────────
    config: "AutonConfig"

    # ─── IO（用于交互式命令）──────────────────────────────────────────────
    input_stream: TextIO = field(default_factory=lambda: sys.stdin)
    output_stream: TextIO = field(default_factory=lambda: sys.stdout)

    # ─── 命令路由回调 ─────────────────────────────────────────────────────
    # 当命令需要 agent 继续处理时，设置此回调
    continue_agent: bool = False

    # ─── 工具方法 ─────────────────────────────────────────────────────────

    def print(self, text: str) -> None:
        """输出到命令输出流"""
        print(text, file=self.output_stream)

    async def input(self, prompt: str = "") -> str:
        """从输入流读取一行（交互式命令用）"""
        if self.input_stream is sys.stdin:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(prompt)
            )
        return self.input_stream.readline().strip()
