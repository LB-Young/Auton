"""LLM Provider — 抽象接口与事件类型"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, AsyncIterator, Literal

if TYPE_CHECKING:
    from ..agent.types import LLMContext


# ─── 流事件 ────────────────────────────────────────────────────────────────

@dataclass
class LLMStreamEvent:
    """LLM 流事件基类"""
    type: str


@dataclass
class TextStartEvent(LLMStreamEvent):
    type: Literal["text_start"] = "text_start"


@dataclass
class TextDeltaEvent(LLMStreamEvent):
    type: Literal["text_delta"] = "text_delta"
    delta: str = ""


@dataclass
class TextFinishEvent(LLMStreamEvent):
    type: Literal["text_finish"] = "text_finish"
    full_text: str = ""


@dataclass
class ReasoningStartEvent(LLMStreamEvent):
    type: Literal["reasoning_start"] = "reasoning_start"
    id: str = ""


@dataclass
class ReasoningDeltaEvent(LLMStreamEvent):
    type: Literal["reasoning_delta"] = "reasoning_delta"
    delta: str = ""


@dataclass
class ReasoningFinishEvent(LLMStreamEvent):
    type: Literal["reasoning_finish"] = "reasoning_finish"


@dataclass
class ToolUseEvent(LLMStreamEvent):
    """LLM 请求工具调用"""
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class ContentBlockStopEvent(LLMStreamEvent):
    """内容块结束"""
    type: Literal["content_block_stop"] = "content_block_stop"


LLMEvent = (
    TextStartEvent | TextDeltaEvent | TextFinishEvent
    | ReasoningStartEvent | ReasoningDeltaEvent | ReasoningFinishEvent
    | ToolUseEvent | ContentBlockStopEvent
)


# ─── Provider 接口 ────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        self.model_name = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    @abstractmethod
    async def stream(self, ctx: "LLMContext") -> AsyncIterator[LLMEvent]:
        """流式生成，返回 AsyncIterator[LLMEvent]"""
        ...

    def schema(self) -> dict:
        """返回当前 provider 支持的工具 schema"""
        return {}
