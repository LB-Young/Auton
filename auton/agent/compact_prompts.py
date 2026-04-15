"""Agent Compact Prompts — 兼容层（实现已迁移至 auton/compress/）

此文件保留是为了向后兼容，现有的 import 路径不会 break。
实际 prompt 逻辑、parse 函数均由 auton.compress 提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# 从新模块导入，保持原有接口不变
from ..compress.prompts import (
    COMPACT_SYSTEM_PROMPT,
    get_base_compact_prompt as get_compact_prompt,
    get_incremental_compact_prompt,
)
from ..compress.parser import parse_compact_summary

if TYPE_CHECKING:
    from .message import Message
    from ..llm.base import LLMProvider


__all__ = [
    "COMPACT_SYSTEM_PROMPT",
    "get_compact_prompt",
    "get_incremental_compact_prompt",
    "parse_compact_summary",
    "generate_compact_summary",
]


async def generate_compact_summary(
    llm: "LLMProvider",
    session_id: str,
    messages_to_summarize: "list[Message]",
    *,
    has_prior_summary: bool = False,
) -> str:
    """调用 LLM 生成压缩摘要（兼容接口，内部使用 StandaloneCompressor 逻辑）。

    Args:
        llm:                   LLM Provider 实例
        session_id:            当前会话 ID
        messages_to_summarize: 待摘要的消息列表
        has_prior_summary:     是否存在历史压缩摘要

    Returns:
        解析后的摘要文本
    """
    from .message import Message
    from .types import LLMContext

    prompt = (
        get_incremental_compact_prompt()
        if has_prior_summary
        else get_compact_prompt()
    )

    compact_request = Message(role="user")
    compact_request.add_text(prompt)
    all_messages = list(messages_to_summarize) + [compact_request]

    ctx = LLMContext(
        session_id=session_id,
        messages=all_messages,
        tools=[],
        system_prompt=COMPACT_SYSTEM_PROMPT,
        model=llm.model_name,
        max_tokens=min(8192, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    if not full_text.strip():
        raise ValueError("LLM compact 调用未返回有效文本")

    return parse_compact_summary(full_text)
