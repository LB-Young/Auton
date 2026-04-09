"""Compact Command — /compact"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult
from .context import CommandContext


class CompactCommand(Command):
    name = "compact"
    description = "手动触发上下文压缩，减少 token 消耗"
    patterns = [("/compact",)]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        # compact 逻辑由 SessionProcessor 处理
        # 这里只是通知用户即将触发
        return CommandResult(
            content=(
                "[compact] 正在触发上下文压缩...\n"
                "系统将保留首尾消息，中间历史压缩为摘要。"
            ),
            handled=True,
        )

    async def execute_compact(self, ctx: CommandContext) -> int:
        """执行实际的 compact 操作"""
        compacted = ctx.session.compact()
        ctx.session_store.append_compact_event(
            session_id=ctx.session.meta.session_id,
            before_count=compacted,
            summary="[manual /compact triggered]",
        )
        return compacted
