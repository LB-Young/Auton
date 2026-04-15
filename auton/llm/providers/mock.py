"""Mock LLM Provider — 离线测试专用"""

from __future__ import annotations

from typing import AsyncIterator

from ...agent.message import Message
from ...agent.types import LLMContext
from ..base import LLMProvider, TextDeltaEvent, TextFinishEvent, TextStartEvent


class MockProvider(LLMProvider):
    """返回可预测回复的离线 Provider，用于本地测试。"""

    def __init__(
        self,
        model: str = "mock-echo",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        timeout: float = 1.0,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )
        self.context_window = 16_000

    async def stream(self, ctx: LLMContext) -> AsyncIterator:
        """生成简单的 Echo 回复，模拟流式输出。"""
        reply = self._build_reply(ctx)
        yield TextStartEvent()
        for chunk in _chunk(reply, size=60):
            yield TextDeltaEvent(delta=chunk)
        yield TextFinishEvent(full_text=reply)

    def _build_reply(self, ctx: LLMContext) -> str:
        user = _extract_last_user_message(ctx.messages)
        summary = user or "(empty message)"
        return (
            f"[mock:{self.model_name}] 我已收到你的请求，以下是离线环境的模拟回答：\n"
            f"{summary}\n\n"
            "提示：要使用真实模型，请在配置中设置有效的 API Key 并选择实际 provider。"
        )


def _extract_last_user_message(messages: list[Message]) -> str:
    """提取最近一条用户文本内容。"""
    for message in reversed(messages):
        if message.role != "user":
            continue
        parts: list[str] = []
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
        if parts:
            return "\n".join(parts)
    return ""


def _chunk(text: str, size: int) -> list[str]:
    """按固定大小切分字符串，模拟增量输出。"""
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]
