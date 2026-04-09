"""Anthropic Claude Provider"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, AsyncIterator

from anthropic import AsyncAnthropic

from ..agent.message import Message
from ..agent.types import LLMContext
from .base import (
    LLMProvider,
    LLMStreamEvent,
    TextDeltaEvent,
    TextStartEvent,
    TextFinishEvent,
    ToolUseEvent,
    ReasoningDeltaEvent,
    ReasoningStartEvent,
    ReasoningFinishEvent,
)

if TYPE_CHECKING:
    pass


class AnthropicProvider(LLMProvider):
    """Anthropic Claude 流式 Provider"""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        super().__init__(model, api_key, base_url, max_tokens, temperature, timeout)
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = AsyncAnthropic(api_key=key, timeout=timeout)

    def _message_to_anthropic(
        self,
        messages: list[Message],
    ) -> tuple[list[dict[str, Any]], str]:
        """将内部 Message 列表转换为 Anthropic 格式。

        Anthropic messages 数组只接受 role=user/assistant；
        role=system 的消息（如 compact 摘要、项目上下文注入等）会被单独
        收集后返回为 extra_system，调用方应将其追加到顶层 system 参数。

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

        tools = ctx.tools or []
        async with self._client.messages.stream(
            model=ctx.model,
            max_tokens=ctx.max_tokens,
            temperature=ctx.temperature,
            system=system or None,
            messages=anthropic_messages,  # type: ignore
            tools=tools or None,
        ) as stream:
            # SDK v0.88.0: AsyncMessageStream is directly async-iterable via __anext__
            async for event in stream:
                # text block start
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "text":
                        yield TextStartEvent()
                    # tool_use and thinking: tracked via block index

                # derived convenience events (built from content_block_delta internally)
                elif event.type == "text":
                    # TextEvent.snapshot has full accumulated text
                    yield TextDeltaEvent(delta=event.text)

                elif event.type == "thinking":
                    # ThinkingEvent.snapshot has full accumulated thinking
                    yield ReasoningDeltaEvent(delta=event.thinking)

                elif event.type == "input_json":
                    # Tool input JSON delta — accumulated in message_snapshot.input
                    pass  # InputJsonEvent is informational; full input at content_block_stop

                # content block stop
                elif event.type == "content_block_stop":
                    block = event.content_block
                    if block.type == "text":
                        # snapshot has full text
                        yield TextFinishEvent(full_text=block.text)
                    elif block.type == "tool_use":
                        yield ToolUseEvent(
                            id=block.id,
                            name=block.name,
                            input=dict(block.input),
                        )
                    elif block.type == "thinking":
                        yield ReasoningFinishEvent()

    def schema(self) -> list[dict]:
        """返回 Anthropic 工具 schema（由调用者传入）"""
        return []
