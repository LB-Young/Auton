"""OpenAI Chat Completions 兼容 Provider 基类

所有遵循 OpenAI Chat Completions API 格式的平台（OpenAI、Qwen、DeepSeek、
豆包、Kimi、OpenRouter、Gemini 等）均继承此基类，避免重复实现消息格式转换
和流式事件解析逻辑。

子类只需声明：
    DEFAULT_BASE_URL  — 平台 API endpoint
    ENV_API_KEY       — 读取 API key 的环境变量名
    DEFAULT_MODEL     — 默认模型名
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, AsyncIterator

from openai import AsyncOpenAI

from ...agent.message import Message
from ...agent.types import LLMContext
from ..base import (
    LLMProvider,
    LLMStreamEvent,
    ReasoningDeltaEvent,
    ReasoningFinishEvent,
    ReasoningStartEvent,
    TextDeltaEvent,
    TextFinishEvent,
    TextStartEvent,
    ToolUseEvent,
)
from ..retry_utils import retry_stream

if TYPE_CHECKING:
    pass


class OpenAICompatProvider(LLMProvider):
    """OpenAI Chat Completions 兼容接口 Provider 基类。

    子类通过类变量定制平台差异，无需覆写流式逻辑。
    """

    DEFAULT_BASE_URL: str | None = None
    ENV_API_KEY: str = "OPENAI_API_KEY"
    DEFAULT_MODEL: str = "gpt-4o"
    DEFAULT_CONTEXT_WINDOW: int = 8_192    # 子类覆盖以匹配各模型实际值

    # 部分平台（如 DeepSeek-R1）在 delta 中携带 reasoning_content 字段
    SUPPORT_REASONING_FIELD: bool = False

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        effective_model = model or self.DEFAULT_MODEL
        super().__init__(effective_model, api_key, base_url, max_tokens, temperature, timeout)
        key = api_key or os.environ.get(self.ENV_API_KEY, "") or "placeholder"
        url = base_url or self.DEFAULT_BASE_URL
        self._client = AsyncOpenAI(
            api_key=key,
            base_url=url,
            timeout=timeout,
        )
        self.context_window = self.DEFAULT_CONTEXT_WINDOW

    # ── 格式转换 ──────────────────────────────────────────────────────────────

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 Anthropic 工具 schema 格式（input_schema）转换为 OpenAI function calling 格式。"""
        result = []
        for t in tools:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return result

    def _convert_messages(
        self,
        messages: list[Message],
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        """将内部 Message 列表 + system_prompt 转换为 OpenAI messages 数组。

        处理规则：
        - role=system 的消息（compact 摘要等）收集后与 system_prompt 合并，
          放在数组首位。
        - role=assistant 中的 tool 调用 → tool_calls 字段。
        - tool 调用结果 → 紧随其后的 role=tool 消息。
        """
        system_parts: list[str] = []
        if system_prompt:
            system_parts.append(system_prompt)

        body: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                text = msg.get_text()
                if text:
                    system_parts.append(text)
                continue

            text_parts: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []

            for part in msg.parts:
                if part.type == "text":
                    text_parts.append(part.content)
                elif part.type == "tool" and msg.role == "assistant":
                    tool_part = part
                    tool_calls.append({
                        "id": tool_part.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_part.tool_name,
                            "arguments": json.dumps(
                                tool_part.tool_input,
                                ensure_ascii=False,
                            ),
                        },
                    })
                    if tool_part.tool_output is not None:
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tool_part.tool_call_id,
                            "content": str(tool_part.tool_output),
                        })

            if msg.role == "user":
                content = "\n".join(text_parts) if text_parts else ""
                body.append({"role": "user", "content": content})
            elif msg.role == "assistant":
                entry: dict[str, Any] = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                }
                if tool_calls:
                    entry["tool_calls"] = tool_calls
                body.append(entry)
                body.extend(tool_results)

        result: list[dict[str, Any]] = []
        if system_parts:
            result.append({"role": "system", "content": "\n\n".join(system_parts)})
        result.extend(body)
        return result

    # ── 流式生成 ──────────────────────────────────────────────────────────────

    async def stream(self, ctx: LLMContext) -> AsyncIterator[LLMStreamEvent]:
        oai_messages = self._convert_messages(ctx.messages, ctx.system_prompt or "")
        oai_tools = self._convert_tools(ctx.tools or [])

        def _make_stream() -> AsyncIterator[LLMStreamEvent]:
            return self._raw_stream(ctx, oai_messages, oai_tools)

        async for event in retry_stream(_make_stream):
            yield event

    async def _raw_stream(
        self,
        ctx: LLMContext,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LLMStreamEvent]:
        kwargs: dict[str, Any] = {
            "model": ctx.model,
            "messages": messages,
            "max_tokens": ctx.max_tokens,
            "temperature": ctx.temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # 工具调用 delta 缓冲：index → {id, name, arguments}
        tool_calls_buf: dict[int, dict[str, str]] = {}
        text_started = False
        text_finish_emitted = False
        full_text_buf = ""
        reasoning_started = False
        reasoning_finish_emitted = False

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            finish_reason = choice.finish_reason

            # ── Reasoning（DeepSeek-R1 等专属字段）────────────────────────
            if self.SUPPORT_REASONING_FIELD:
                reasoning_text = getattr(delta, "reasoning_content", None)
                if reasoning_text:
                    if not reasoning_started:
                        yield ReasoningStartEvent(id="")
                        reasoning_started = True
                    yield ReasoningDeltaEvent(delta=reasoning_text)

            # ── 文本内容 ──────────────────────────────────────────────────
            if delta.content:
                if not text_started:
                    yield TextStartEvent()
                    text_started = True
                full_text_buf += delta.content
                yield TextDeltaEvent(delta=delta.content)

            # ── 工具调用 delta ────────────────────────────────────────────
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_buf:
                        tool_calls_buf[idx] = {"id": "", "name": "", "arguments": ""}
                    buf = tool_calls_buf[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["arguments"] += tc_delta.function.arguments

            # ── 结束信号 ──────────────────────────────────────────────────
            # 部分网关/代理会在多帧中重复带 finish_reason，只应发出一次
            # TextFinish/ReasoningFinish，否则 Web 端会收到多条 message 而重复整段展示。
            if finish_reason in ("stop", "end_turn", "length"):
                if reasoning_started and not reasoning_finish_emitted:
                    yield ReasoningFinishEvent()
                    reasoning_finish_emitted = True
                if text_started and not text_finish_emitted:
                    yield TextFinishEvent(full_text=full_text_buf)
                    text_finish_emitted = True

            elif finish_reason == "tool_calls":
                if reasoning_started and not reasoning_finish_emitted:
                    yield ReasoningFinishEvent()
                    reasoning_finish_emitted = True
                if text_started and not text_finish_emitted:
                    yield TextFinishEvent(full_text=full_text_buf)
                    text_finish_emitted = True
                for buf in tool_calls_buf.values():
                    try:
                        tool_input = json.loads(buf["arguments"]) if buf["arguments"] else {}
                    except json.JSONDecodeError:
                        tool_input = {}
                    yield ToolUseEvent(
                        id=buf["id"],
                        name=buf["name"],
                        input=tool_input,
                    )

    def schema(self) -> list[dict]:
        return []
