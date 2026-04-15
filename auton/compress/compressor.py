"""compress/compressor.py — 实时压缩主流程（StandaloneCompressor）"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger

from .boundary import compute_compress_boundary
from .config import CompressConfig
from .parser import parse_compact_summary
from .prompts import (
    COMPACT_SYSTEM_PROMPT,
    get_base_compact_prompt,
    get_incremental_compact_prompt,
)
from .pruner import prune_tool_results

if TYPE_CHECKING:
    from ..agent.message import Message
    from ..llm.base import LLMProvider


class StandaloneCompressor:
    """独立会话压缩组件。

    完全独立于主 agent / subagent 体系，可在任何地方直接使用：

        compressor = StandaloneCompressor(llm=llm_provider, config=CompressConfig())
        compressed_messages = await compressor.compress(messages, session_id="xxx")
    """

    def __init__(
        self,
        llm: "LLMProvider",
        config: CompressConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or CompressConfig()
        self._compression_count = 0
        self._last_compression_time: float | None = None
        self._logger = logger.bind(name="StandaloneCompressor")

    async def compress(
        self,
        messages: "list[Message]",
        session_id: str,
    ) -> "list[Message]":
        """执行完整压缩流程。

        流程：
          1. 防抖检查
          2. 工具输出截断（pre-pass，无 LLM）
          3. 计算压缩边界（tool pair 对齐）
          4. LLM 生成摘要（base 或 incremental）
          5. 组装压缩后消息
          （post-pass sanitize 在 dict 层做，此处对 Message 层暂跳过）

        Args:
            messages:   原始消息列表
            session_id: 会话 ID（用于日志）

        Returns:
            压缩后的消息列表；若防抖或无内容可压缩则原样返回
        """
        if not self._can_compress():
            self._logger.info("compress skipped (cooldown or limit reached)")
            return messages

        # Phase 1: 工具输出截断（pre-pass）
        pruned_messages, pruned_count = prune_tool_results(
            messages,
            protect_tail_count=self.config.protect_tail_tool_results,
        )
        if pruned_count > 0:
            self._logger.info("pre-pass: pruned {} tool result(s)", pruned_count)

        # Phase 2: 计算压缩边界
        boundary = compute_compress_boundary(
            pruned_messages,
            protect_turns=self.config.protect_turns,
            tail_token_budget=self.config.tail_token_budget,
        )

        if boundary.is_empty:
            self._logger.info("nothing to compress (boundary is empty)")
            return messages

        # Phase 3: LLM 生成摘要
        try:
            if boundary.has_prior_summary:
                summary_text = await self._generate_incremental_summary(boundary, session_id)
            else:
                summary_text = await self._generate_base_summary(boundary, session_id)
        except Exception as exc:
            self._logger.warning("LLM compress failed: {}; returning original messages", exc)
            return messages

        # Phase 4: 组装压缩后消息
        compressed = self._assemble_messages(boundary, summary_text)

        self._compression_count += 1
        self._last_compression_time = time.monotonic()
        self._logger.info(
            "compressed session={} count={} original={} result={}",
            session_id,
            self._compression_count,
            boundary.original_count,
            len(compressed),
        )

        return compressed

    # ─── 内部方法 ──────────────────────────────────────────────────────────

    def _can_compress(self) -> bool:
        """防抖检查：是否可以执行压缩"""
        if self._compression_count >= self.config.max_compressions_per_session:
            return False
        if self._last_compression_time is not None:
            elapsed = time.monotonic() - self._last_compression_time
            if elapsed < self.config.compression_cooldown_seconds:
                return False
        return True

    async def _generate_base_summary(
        self,
        boundary: "object",
        session_id: str,
    ) -> str:
        return await self._call_llm(get_base_compact_prompt(), boundary, session_id)

    async def _generate_incremental_summary(
        self,
        boundary: "object",
        session_id: str,
    ) -> str:
        return await self._call_llm(get_incremental_compact_prompt(), boundary, session_id)

    async def _call_llm(
        self,
        prompt: str,
        boundary: "object",
        session_id: str,
    ) -> str:
        from ..agent.message import Message
        from ..agent.types import LLMContext

        all_messages = boundary.build_llm_input()
        compact_request = Message(role="user")
        compact_request.add_text(prompt)
        all_messages.append(compact_request)

        ctx = LLMContext(
            session_id=session_id,
            messages=all_messages,
            tools=[],
            system_prompt=COMPACT_SYSTEM_PROMPT,
            model=self.llm.model_name,
            max_tokens=min(self.config.max_summary_tokens, self.llm.max_tokens),
            temperature=self.config.summary_temperature,
        )

        full_text = ""
        async for event in self.llm.stream(ctx):
            if event.type == "text_delta":
                full_text += getattr(event, "delta", "")

        if not full_text.strip():
            raise ValueError("LLM compact 调用未返回有效文本")

        return parse_compact_summary(full_text)

    def _assemble_messages(
        self,
        boundary: "object",
        summary_text: str,
    ) -> "list[Message]":
        from ..agent.message import Message

        full_summary = f"[历史压缩] {summary_text}"
        summary_msg = Message(role="system")
        summary_msg.add_text(full_summary)

        return (
            list(boundary.stable_prefix)
            + [summary_msg]
            + list(boundary.messages_to_keep)
        )
