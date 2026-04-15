"""Summary Generator — LLM 驱动的会话分段摘要

摘要定位：用于后续新 query 的语义召回，每条摘要对应 session.jsonl 中的一段事件。

设计原则（参考 Claude Code session-memory 的信息密度要求）：
  - 信息完整：包含所有对新 query 可能有用的关键内容（请求、决策、文件、错误、命令）
  - 可检索：摘要文本本身即为语义搜索的语料
  - 有锚点：每条摘要标注来源事件在 session.jsonl 中的行范围，便于追溯

SUMMARY.md 格式：
  # 会话摘要索引 — {scope}

  ## 段落 001 — 会话 abc12345（事件 0–44，sessions/abc12345.jsonl 第 1–45 行）
  **主要请求**：...
  **关键技术内容**：...
  **涉及的文件与代码**：...
  **决策与结论**：...
  **错误与修正**：...（若无则省略）
  **命令与工作流**：...（若无则省略）
  **待处理事项**：...（若无则省略）

  ## 段落 002 — 会话 abc12345（事件 45–89，sessions/abc12345.jsonl 第 46–90 行）
  ...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.base import LLMProvider
    from .compression_improver import CompressionImprover


# ─── 提示词（从独立模块导入，解耦 prompt 与生成逻辑）──────────────────────────

from .summary_prompts import (
    SUMMARY_SYSTEM_PROMPT as _SUMMARY_SYSTEM_PROMPT,
    get_session_summary_prompt as _get_session_summary_prompt,
    build_conversation_text as _build_conversation_text,
    has_meaningful_content as _has_meaningful_content,
)


# ─── 摘要条目格式化 ───────────────────────────────────────────────────────────

def _count_existing_segments(summary_path: Path) -> int:
    """统计 SUMMARY.md 中已有的段落数（用于新段落编号）。"""
    if not summary_path.exists():
        return 0
    text = summary_path.read_text(encoding="utf-8")
    return len(re.findall(r"^## 段落 \d+", text, re.MULTILINE))


def get_last_summarized_idx(summary_path: Path, session_id: str) -> int:
    """从 SUMMARY.md 读取该 session 已摘要到的最大事件索引（end_idx）。

    返回值含义与 _last_summarized_idx 相同：
      -1  → 该 session 尚未被摘要过，下次应从索引 0 开始
      N   → 事件 0–N 已摘要，下次应从 N+1 开始

    设计目的：使 start_idx 可从持久化文件（SUMMARY.md）中恢复，
    解耦对进程内状态（processor._last_summarized_idx）的依赖。
    Web 模式下每次请求都创建新 processor，进程内状态每次都从 -1 重置，
    依赖此函数才能避免重复摘要已处理的事件。

    解析逻辑：匹配 session_id 对应的段落头（含 short_id 前 8 位），
    取最后一个匹配段落的 end_idx。
    """
    if not summary_path.exists():
        return -1

    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    text = summary_path.read_text(encoding="utf-8")

    # 格式: ## 段落 NNN — 会话 abc12345（事件 M–N，...）
    pattern = re.compile(
        rf"## 段落 \d+ — 会话 {re.escape(short_id)}（事件 \d+–(\d+)，",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        return -1

    # 取最大的 end_idx（不一定是最后一条，防止乱序）
    return max(int(m) for m in matches)


def _format_summary_entry(
    segment_idx: int,
    session_id: str,
    start_idx: int,
    end_idx: int,
    summary_text: str,
) -> str:
    """将 LLM 输出格式化为 SUMMARY.md 的一个段落条目。

    每条包含：
      - 段落编号和来源定位（会话 ID + 事件范围 + jsonl 行范围）
      - LLM 生成的结构化摘要正文
    """
    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    start_line = start_idx + 1  # 事件索引 0 → 第 1 行
    end_line = end_idx + 1

    header = (
        f"## 段落 {segment_idx:03d} — 会话 {short_id}"
        f"（事件 {start_idx}–{end_idx}，"
        f"sessions/{session_id}.jsonl 第 {start_line}–{end_line} 行）"
    )
    return f"{header}\n\n{summary_text.strip()}\n"


# ─── LLM 调用 ────────────────────────────────────────────────────────────────

async def _call_llm_for_summary(
    llm: "LLMProvider",
    session_id: str,
    conversation_text: str,
    start_idx: int,
    end_idx: int,
    *,
    custom_prompt: str | None = None,
) -> str:
    """调用 LLM 生成对话片段的结构化摘要。

    Args:
        custom_prompt: 若提供，则替换默认 prompt（用于 CompressionImprover 改进 prompt）

    Returns:
        摘要文本（纯文本，无工具调用）

    Raises:
        ValueError: LLM 未返回有效文本
    """
    from ..agent.message import Message
    from ..agent.types import LLMContext

    if custom_prompt is not None:
        prompt = custom_prompt
    else:
        prompt = _get_session_summary_prompt(
            session_id=session_id,
            start_idx=start_idx,
            end_idx=end_idx,
            conversation_text=conversation_text,
        )

    user_msg = Message(role="user")
    user_msg.add_text(prompt)

    ctx = LLMContext(
        session_id=session_id,
        messages=[user_msg],
        tools=[],
        system_prompt=_SUMMARY_SYSTEM_PROMPT,
        model=llm.model_name,
        max_tokens=min(4096, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    if not full_text.strip():
        raise ValueError("LLM 摘要调用未返回有效文本")

    return full_text.strip()


# ─── 核心接口：生成并追加摘要 ─────────────────────────────────────────────────

async def generate_and_append_summary(
    llm: "LLMProvider",
    session_id: str,
    events: list[dict],
    start_idx: int,
    summary_path: Path,
    scope: str = "",
    compression_improver: "CompressionImprover | None" = None,
) -> int:
    """为 events[start_idx:] 生成 LLM 摘要并追加到 SUMMARY.md。

    Args:
        llm: LLM Provider 实例
        session_id: 当前会话 ID
        events: session jsonl 全部事件列表
        start_idx: 本次摘要起始事件索引（上次摘要结束后的下一条）
        summary_path: SUMMARY.md 的绝对路径
        scope: 标题说明（项目路径或日期）
        compression_improver: 若提供，则用检索质量分析生成改进 prompt，
            替换默认 prompt，逐步提升 summary 的检索命中率。

    Returns:
        新的 last_summarized_idx（即 len(events) - 1）；
        若无需摘要则返回 start_idx - 1（不变）。
    """
    end_idx = len(events) - 1
    if start_idx > end_idx:
        return start_idx - 1

    events_slice = events[start_idx:]
    if not _has_meaningful_content(events_slice):
        return start_idx - 1

    conversation_text = _build_conversation_text(events_slice)
    if not conversation_text.strip():
        return start_idx - 1

    # 尝试用 CompressionImprover 生成改进 prompt（有则用，无则降级到默认 prompt）
    custom_prompt: str | None = None
    if compression_improver is not None:
        try:
            current_summary = (
                summary_path.read_text(encoding="utf-8")
                if summary_path.exists()
                else ""
            )
            custom_prompt = compression_improver.generate_improvement_prompt(
                session_id=session_id,
                session_jsonl=events_slice,
                current_summary=current_summary,
            )
        except Exception:
            custom_prompt = None  # 改进 prompt 生成失败时静默降级

    # 生成 LLM 摘要
    summary_text = await _call_llm_for_summary(
        llm, session_id, conversation_text, start_idx, end_idx,
        custom_prompt=custom_prompt,
    )

    # 确定段落编号（基于已有段落数 + 1）
    segment_idx = _count_existing_segments(summary_path) + 1
    entry = _format_summary_entry(segment_idx, session_id, start_idx, end_idx, summary_text)

    # 写入 SUMMARY.md
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if not summary_path.exists():
        scope_line = f"_{scope}_\n\n" if scope else ""
        header = (
            f"# 会话摘要索引\n\n"
            f"{scope_line}"
            "_每条摘要对应 session.jsonl 中的一段事件，"
            "包含关键信息用于后续语义检索。_\n\n"
        )
        summary_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n" + entry)

    return end_idx
