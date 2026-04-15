"""MiniMax Provider — Anthropic API 兼容"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, AsyncIterator

import anthropic
from anthropic import AsyncAnthropic

from ...agent.message import Message
from ...agent.types import LLMContext
from ..base import (
    LLMProvider,
    LLMStreamEvent,
    ReasoningDeltaEvent,
    ReasoningFinishEvent,
    ReasoningStartEvent,
    TextDeltaEvent,
    TextStartEvent,
    TextFinishEvent,
    ToolUseEvent,
)
from ..retry_utils import retry_stream

if TYPE_CHECKING:
    pass


class MiniMaxProvider(LLMProvider):
    """MiniMax 流式 Provider（Anthropic API 兼容）"""

    DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"

    # MiniMax 各模型上下文窗口（token 数）
    _CONTEXT_WINDOWS: dict[str, int] = {
        "MiniMax-M2":  1_000_000,
        "MiniMax-Text-01": 1_000_000,
        "abab7":       245_760,
        "abab6.5s":    245_760,
        "abab6.5":     8_192,
        "abab5.5s":    8_192,
        "abab5.5":     4_096,
    }

    def __init__(
        self,
        model: str = "MiniMax-M2.7",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(model, api_key, base_url, max_tokens, temperature, timeout)
        key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        url = base_url or self.DEFAULT_BASE_URL
        self._client = AsyncAnthropic(api_key=key, base_url=url, timeout=timeout)
        # 根据 model 名称前缀匹配上下文窗口
        for prefix, cw in self._CONTEXT_WINDOWS.items():
            if model.startswith(prefix):
                self.context_window = cw
                break
        else:
            self.context_window = 32_768  # MiniMax 未知模型保守估计

    def _message_to_anthropic(
        self,
        messages: list[Message],
    ) -> tuple[list[dict[str, Any]], str]:
        """将内部 Message 列表转换为 Anthropic 兼容格式。

        role=system 的消息（compact 摘要等）不放入 messages 数组，
        而是收集后以字符串形式返回，由调用方追加到顶层 system 参数。

        Returns:
            (anthropic_messages, extra_system)
        """
        result: list[dict[str, Any]] = []
        extra_system_parts: list[str] = []

        for msg in messages:
            if msg.role == "system":
                text = msg.get_text()
                if text:
                    extra_system_parts.append(text)
                continue

            content: list[dict[str, Any]] = []
            tool_result_msgs: list[dict[str, Any]] = []
            for part in msg.parts:
                if part.type == "text":
                    content.append({"type": "text", "text": part.content})
                elif part.type == "reasoning":
                    content.append({"type": "thinking", "thinking": part.content})
                elif part.type == "tool":
                    tool_part = part
                    content.append({
                        "type": "tool_use",
                        "id": tool_part.tool_call_id,
                        "name": tool_part.tool_name,
                        "input": tool_part.tool_input,
                    })
                    if tool_part.tool_output:
                        # tool_result 单独发 user message（跟在 assistant 消息之后）
                        tool_result_msgs.append({
                            "type": "tool_result",
                            "tool_use_id": tool_part.tool_call_id,
                            "content": tool_part.tool_output,
                        })
            if content:
                result.append({"role": msg.role, "content": content})
            for tr in tool_result_msgs:
                result.append({"role": "user", "content": [tr]})

        return result, "\n\n".join(extra_system_parts)

    async def stream(self, ctx: LLMContext) -> AsyncIterator[LLMStreamEvent]:
        anthropic_messages, extra_system = self._message_to_anthropic(ctx.messages)
        base_system = ctx.system_prompt or ""
        system = (base_system + "\n\n" + extra_system).strip() if extra_system else base_system

        def _make_stream() -> AsyncIterator[LLMStreamEvent]:
            return self._raw_stream(ctx, anthropic_messages, system)

        async for event in retry_stream(_make_stream):
            yield event

    async def _raw_stream(
        self,
        ctx: LLMContext,
        anthropic_messages: list[dict[str, Any]],
        system: str,
    ) -> AsyncIterator[LLMStreamEvent]:
        async with self._client.messages.stream(
            model=ctx.model,
            max_tokens=ctx.max_tokens,
            temperature=ctx.temperature,
            system=system or None,
            messages=anthropic_messages,  # type: ignore
            tools=ctx.tools or None,
        ) as stream:
            async for event in stream:
                # SDK v0.88.0: AsyncMessageStream is directly async-iterable via __anext__
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        yield TextStartEvent()
                    elif block.type == "thinking":
                        # MiniMax thinking blocks have an id
                        block_id = getattr(block, "id", "") or ""
                        yield ReasoningStartEvent(id=block_id)

                elif event.type == "text":
                    yield TextDeltaEvent(delta=event.text)

                elif event.type == "thinking":
                    yield ReasoningDeltaEvent(delta=event.thinking)

                elif event.type == "input_json":
                    pass  # accumulated via message_snapshot

                elif event.type == "content_block_stop":
                    block = event.content_block
                    if block.type == "text":
                        yield TextFinishEvent(full_text=block.text)
                    elif block.type == "tool_use":
                        yield ToolUseEvent(
                            id=block.id,
                            name=block.name,
                            input=dict(block.input),
                        )
                    elif block.type == "thinking":
                        yield ReasoningFinishEvent()
