"""compress/boundary.py — 压缩边界计算"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ..agent.message import Message


# ─── 双阈值触发判断 ────────────────────────────────────────────────────────────

ABSOLUTE_TOKEN_THRESHOLD = 150_000
DEFAULT_THRESHOLD_PERCENT = 0.60


def should_compress(
    token_count: int,
    context_length: int,
    *,
    absolute_threshold: int = ABSOLUTE_TOKEN_THRESHOLD,
    percent_threshold: float = DEFAULT_THRESHOLD_PERCENT,
) -> bool:
    """判断是否需要触发压缩（双阈值，任一满足即触发）。

    Args:
        token_count:        当前消息列表的估算 token 数
        context_length:     模型上下文窗口大小
        absolute_threshold: 绝对 token 阈值（默认 150,000）
        percent_threshold:  上下文窗口比例阈值（默认 60%）

    Returns:
        True 如果需要压缩
    """
    percent_limit = int(context_length * percent_threshold)
    return token_count >= absolute_threshold or token_count >= percent_limit


# ─── 压缩边界 ──────────────────────────────────────────────────────────────────

@dataclass
class CompressBoundary:
    """压缩边界计算结果。

    将消息列表划分为三段：
        stable_prefix        — system prompt + 已有历史摘要（始终保留，不再压缩）
        messages_to_compress — 待 LLM 摘要的中间消息
        messages_to_keep     — 尾部保留的最近几轮对话
    """
    stable_prefix: list["Message"]
    messages_to_compress: list["Message"]
    messages_to_keep: list["Message"]
    has_prior_summary: bool
    original_count: int = 0
    compressed_count: int = 0

    @property
    def is_empty(self) -> bool:
        """没有待压缩内容时返回 True"""
        return not self.messages_to_compress

    def build_llm_input(self) -> "list[Message]":
        """为 LLM 调用构建输入消息列表。

        增量压缩时：将 stable_prefix 中的历史摘要前置，让 LLM 感知已有摘要做增量更新。
        首次压缩时：仅返回 messages_to_compress。
        """
        if not self.has_prior_summary:
            return list(self.messages_to_compress)

        prior_summaries = [
            msg
            for msg in self.stable_prefix
            if msg.role == "system"
            and msg.get_text().strip().startswith("[历史压缩]")
        ]
        return prior_summaries + list(self.messages_to_compress)


# ─── 边界计算 ──────────────────────────────────────────────────────────────────

def compute_compress_boundary(
    messages: "list[Message]",
    *,
    protect_turns: int = 2,
    tail_token_budget: int = 40_000,
    min_tail_messages: int = 2,
) -> CompressBoundary:
    """计算压缩边界，将消息列表划分为三段。

    算法：
      1. 找出稳定前缀（system prompt + 连续的历史压缩摘要）
      2. 确定尾部起点（保留最近 protect_turns 轮用户对话）
      3. 若尾部 token 超出预算，自动缩减保留轮次
      4. 对齐 tool pair 边界（不切断 tool_call + tool_result pair）

    Args:
        messages:          完整消息列表
        protect_turns:     保留最近几轮用户对话
        tail_token_budget: 尾部 token 上限
        min_tail_messages: 尾部最小消息数

    Returns:
        CompressBoundary 对象（不修改原始 messages）
    """
    total = len(messages)
    if total <= 2:
        return CompressBoundary(
            stable_prefix=list(messages),
            messages_to_compress=[],
            messages_to_keep=[],
            has_prior_summary=False,
            original_count=total,
            compressed_count=0,
        )

    # ── Step 1: 找稳定前缀 ─────────────────────────────────────────────────
    stable_prefix_end = 1  # 至少包含 system prompt（或首条消息）
    has_prior_summary = False
    while stable_prefix_end < total:
        msg = messages[stable_prefix_end]
        text = msg.get_text().strip()
        if msg.role == "system" and text.startswith("[历史压缩]"):
            stable_prefix_end += 1
            has_prior_summary = True
        else:
            break

    compressible_total = total - stable_prefix_end
    if compressible_total <= 1:
        return CompressBoundary(
            stable_prefix=list(messages[:stable_prefix_end]),
            messages_to_compress=[],
            messages_to_keep=list(messages[stable_prefix_end:]),
            has_prior_summary=has_prior_summary,
            original_count=total,
            compressed_count=0,
        )

    # ── Step 2: 确定尾部起点 ───────────────────────────────────────────────
    turn_starts = _find_real_user_turn_starts(messages, start=stable_prefix_end)
    preserved_turns = min(protect_turns, len(turn_starts)) if turn_starts else 0

    if preserved_turns > 0:
        tail_start = turn_starts[-preserved_turns]
    else:
        tail_start = max(stable_prefix_end + 1, total - min_tail_messages)

    # ── Step 3: 若尾部 token 超出预算，缩减保留轮次 ──────────────────────
    while tail_start > stable_prefix_end:
        recent_tokens = _estimate_tokens(messages[tail_start:])
        if recent_tokens <= tail_token_budget:
            break
        if preserved_turns > 1:
            preserved_turns -= 1
            tail_start = turn_starts[-preserved_turns]
        elif _contains_internal_messages(messages[tail_start:]):
            break
        else:
            tail_start = min(total - 1, tail_start + 1)

    # ── Step 4: 对齐 tool pair 边界 ───────────────────────────────────────
    tail_start = _align_boundary_backward(messages, tail_start)

    return CompressBoundary(
        stable_prefix=list(messages[:stable_prefix_end]),
        messages_to_compress=list(messages[stable_prefix_end:tail_start]),
        messages_to_keep=list(messages[tail_start:]),
        has_prior_summary=has_prior_summary,
        original_count=total,
        compressed_count=tail_start - stable_prefix_end,
    )


# ─── 内部工具函数 ──────────────────────────────────────────────────────────────

def _find_real_user_turn_starts(
    messages: "Sequence[Message]",
    *,
    start: int = 0,
) -> list[int]:
    """返回真实用户轮次的起点索引。

    工具结果（[tool: xxx]）和命令结果（[command: xxx]）虽然以 user message
    形式写入 session，但不作为"用户轮次"边界，避免将最近一轮工具交互拆断。
    """
    starts = []
    for idx in range(start, len(messages)):
        msg = messages[idx]
        if msg.role != "user":
            continue
        text = msg.get_text().strip()
        if text.startswith("[tool:") or text.startswith("[command:"):
            continue
        starts.append(idx)
    return starts


def _contains_internal_messages(messages: "Sequence[Message]") -> bool:
    """检查消息列表是否包含工具结果等内部消息"""
    for msg in messages:
        if msg.role != "user":
            continue
        text = msg.get_text().strip()
        if text.startswith("[tool:") or text.startswith("[command:"):
            return True
    return False


def _align_boundary_backward(messages: "list[Message]", idx: int) -> int:
    """将边界回拉到 tool pair 开始处，确保 tool_call + tool_result 不被切断。

    本项目中工具结果以 role='user'、内容带 '[tool:' 前缀的消息写入，
    而非标准 role='tool' 格式。对齐逻辑：
      1. 若边界前方紧邻一条或多条工具结果消息，将它们整体划入 tail；
      2. 若工具结果消息之前还有一条携带工具调用的 assistant 消息，
         也一并拉入 tail，避免调用方与结果方分离。
    """
    # Step 1：将所有紧邻的工具结果（[tool:] 前缀 user 消息）拉入 tail
    while idx > 0:
        prev = messages[idx - 1]
        if prev.role == "user" and prev.get_text().strip().startswith("[tool:"):
            idx -= 1
        else:
            break

    # Step 2：若工具结果之前是发起调用的 assistant 消息，也一并拉入
    if idx > 0:
        prev = messages[idx - 1]
        if prev.role == "assistant" and prev.get_tools():
            idx -= 1

    return idx


def _estimate_tokens(messages: "Sequence[Message]") -> int:
    """估算消息列表的 token 数（字符数 / 4 + 固定 overhead）"""
    total = 0
    for msg in messages:
        total += len(msg.get_text()) // 4 + 10
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls or []:
                args = getattr(getattr(tc, "function", None), "arguments", "") or ""
                total += len(args) // 4
    return total
