"""Utilities for estimating token usage for session messages."""

from __future__ import annotations

import json
from typing import Sequence

from .message import Message, TextPart, ToolPart


def estimate_tokens_from_messages(messages: Sequence[Message]) -> int:
    """Rudimentary token estimation based on character counts."""
    total = 0
    for msg in messages:
        total += _estimate_message_tokens(msg)
    return max(1, total)


def estimate_context_tokens(messages: Sequence[Message], system_prompt: str = "") -> int:
    """Estimate tokens for the entire LLM context (system + history)."""
    message_tokens = estimate_tokens_from_messages(messages)
    system_tokens = len(system_prompt) // 4 if system_prompt else 0
    return message_tokens + system_tokens


def _estimate_message_tokens(msg: Message) -> int:
    char_count = 0
    for part in msg.parts:
        if isinstance(part, TextPart):
            char_count += len(part.content)
        elif isinstance(part, ToolPart):
            char_count += len(json.dumps(part.tool_input, ensure_ascii=False))
            if part.tool_output:
                char_count += len(part.tool_output)
    if char_count == 0:
        char_count = 4  # minimal overhead
    return char_count // 4 + 1
