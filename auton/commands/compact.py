"""Compact Command — /compact

手动触发上下文 LLM 压缩，失败时降级为截断摘要。
"""

from __future__ import annotations

from typing import Any

from .base import Command, CommandResult
from .context import CommandContext
from ..agent.session import CompactResult


class CompactCommand(Command):
    name = "compact"
    description = "手动触发上下文压缩，减少 token 消耗"
    patterns = [("/compact",)]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        return CommandResult(
            content=(
                "[compact] 正在触发上下文压缩...\n"
                "系统将保留最近几轮对话，中间历史通过 LLM 压缩为结构化摘要。"
            ),
            handled=True,
        )

    async def execute_compact(
        self,
        ctx: CommandContext,
        *,
        protect_turns: int = 2,
        recent_token_budget: int = 40_000,
    ) -> CompactResult:
        """执行 compact：优先 LLM 结构化摘要，失败时降级为截断。

        持久化由 SessionProcessor._finalize_compact() 统一负责。
        """
        from ..agent.compact_prompts import generate_compact_summary

        preparation = ctx.session.prepare_compact(
            protect_turns=protect_turns,
            recent_token_budget=recent_token_budget,
        )
        if preparation.is_empty:
            return CompactResult()

        try:
            summary_text = await generate_compact_summary(
                ctx.llm,
                ctx.session.meta.session_id,
                preparation.build_llm_input(),
                has_prior_summary=preparation.has_prior_summary,
            )
            return ctx.session.apply_compact(summary_text, preparation)
        except Exception as exc:
            # LLM 不可用时降级：用截断文本保证 compact 仍然完成
            fallback_lines = [
                f"[{m.role}] {m.get_text()[:100]}"
                for m in preparation.messages_to_compress[:6]
                if m.get_text()
            ]
            fallback_text = (
                f"合并 {len(preparation.messages_to_compress)} 条消息"
                f"（LLM 摘要不可用：{exc}，保留片段）：\n"
                + "\n".join(fallback_lines)
            )
            return ctx.session.apply_compact(fallback_text, preparation)
