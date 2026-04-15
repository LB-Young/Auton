"""memory/memory_indexer.py — MEMORY.md 索引生成与更新"""

from __future__ import annotations

import re
from pathlib import Path


def format_memory_entry(session_id: str, short_id: str, intent: str) -> str:
    """生成 MEMORY.md 索引条目。

    格式：- [ShortID] — 用户意图一句话描述

    Args:
        session_id: 完整 session ID
        short_id:   短 ID（前 8 位）
        intent:     用户意图摘要

    Returns:
        索引条目字符串
    """
    return f"- [{short_id}] — {intent}"


def update_memory_index(
    memory_path: Path,
    session_id: str,
    intent: str,
) -> None:
    """追加或更新 MEMORY.md 中的索引条目。

    如果 session 已存在索引条目，则更新；否则追加。

    Args:
        memory_path: MEMORY.md 的绝对路径
        session_id:  完整 session ID
        intent:      用户意图摘要
    """
    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    entry = format_memory_entry(session_id, short_id, intent)

    memory_path.parent.mkdir(parents=True, exist_ok=True)

    if memory_path.exists():
        text = memory_path.read_text(encoding="utf-8")
        pattern = re.compile(rf"- \[{re.escape(short_id)}\] — .+")
        if pattern.search(text):
            text = pattern.sub(entry, text)
        else:
            text = text.rstrip("\n") + f"\n{entry}\n"
    else:
        text = f"# 记忆索引\n\n{entry}\n"

    memory_path.write_text(text, encoding="utf-8")


def extract_intent_from_events(events: list[dict]) -> str:
    """从事件列表提取第一条用户意图（用于 MEMORY.md 条目）。

    Args:
        events: session jsonl 事件列表

    Returns:
        意图字符串；若找不到则返回"（无用户消息）"
    """
    for ev in events:
        if ev.get("type") == "user-message":
            content = ev.get("content", "").strip()
            if content:
                return content[:100] + ("…" if len(content) > 100 else "")
    return "（无用户消息）"
