"""compress/pruner.py — 工具输出截断（Pre-pass，无 LLM 调用）"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent.message import Message


TOOL_OUTPUT_PLACEHOLDER = "[工具输出已清理]"
TOOL_OUTPUT_THRESHOLD = 200  # 字符数，超过此长度截断


def prune_tool_results(
    messages: "list[Message]",
    protect_tail_count: int = 15,
) -> "tuple[list[Message], int]":
    """将超过阈值的工具输出替换为占位符（无 LLM 调用）。

    从后往前遍历：保护最近 protect_tail_count 条消息不被截断，
    其余超过阈值的工具输出替换为占位符。

    Args:
        messages:            消息列表
        protect_tail_count:  尾部保留的工具结果数量

    Returns:
        (处理后的消息列表, 截断数量)
    """
    result: list[Message] = []
    pruned = 0
    prune_boundary = len(messages) - protect_tail_count

    for i, msg in enumerate(messages):
        if i < prune_boundary and msg.role == "tool":
            content = msg.get_text()
            if len(content) > TOOL_OUTPUT_THRESHOLD:
                result.append(_replace_tool_with_placeholder(msg))
                pruned += 1
                continue
        result.append(msg)

    return result, pruned


def _replace_tool_with_placeholder(msg: "Message") -> "Message":
    """将工具消息的内容替换为占位符，返回新消息（不修改原消息）。"""
    from ..agent.message import Message

    new_msg = Message(role="tool")
    new_msg.add_text(TOOL_OUTPUT_PLACEHOLDER)
    # 保留 tool_call_id（如有）
    if hasattr(msg, "_tool_call_id") and msg._tool_call_id:
        new_msg._tool_call_id = msg._tool_call_id
    return new_msg
