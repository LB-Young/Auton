"""Helpers for listing and loading session records for the web UI."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ...agent.message import Message
from ...agent.session import Session
from ...agent.session_store import SessionStore
from ...memory.storage_utils import project_storage_base


def _stable_compact_prefix_end(messages: list[Message]) -> int:
    """返回 compact 时应稳定保留的前缀长度。

    规则需与 `Session.compact()` 保持一致：首条系统消息之后，连续的
    `[历史压缩]` system 摘要都属于稳定前缀，不能再被误裁掉。
    """
    if not messages:
        return 0
    stable_prefix_end = 1
    while stable_prefix_end < len(messages):
        msg = messages[stable_prefix_end]
        text = msg.get_text().strip()
        if msg.role == "system" and text.startswith("[历史压缩]"):
            stable_prefix_end += 1
            continue
        break
    return stable_prefix_end


def _read_index_file(base_dir: Path) -> list[dict[str, Any]]:
    path = base_dir / SessionStore.INDEX_FILE
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def _session_file_from_entry(base_dir: Path, entry: dict[str, Any]) -> Path | None:
    rel = entry.get("path")
    if not rel:
        return None
    path = base_dir / rel
    return path if path.exists() else None


def _load_preview(session_path: Path) -> str:
    """Return the first user message snippet as preview text."""
    try:
        with open(session_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") == "user-message":
                    text = payload.get("content", "").strip()
                    if text:
                        return text[:80]
                elif payload.get("role") == "user":
                    parts = payload.get("parts") or []
                    for part in parts:
                        if part.get("type") == "text":
                            text = (part.get("content") or "").strip()
                            if text:
                                return text[:80]
    except FileNotFoundError:
        return ""
    return ""


def _list_sessions_from_directory(
    base: Path,
    *,
    limit: int,
    date_label: str | None = None,
) -> list[dict[str, Any]]:
    sessions_dir = base / SessionStore.SESSIONS_DIR
    if not sessions_dir.exists():
        return []
    try:
        files = sorted(
            [p for p in sessions_dir.glob("*.jsonl") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except FileNotFoundError:
        return []

    rows: list[dict[str, Any]] = []
    for path in files:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        except FileNotFoundError:
            continue
        preview = _load_preview(path)
        rows.append({
            "session_id": path.stem,
            "started_at": mtime,
            "ended_at": mtime,
            "label": preview or path.stem,
            "date": date_label or mtime[:10],
        })
        if len(rows) >= limit:
            break
    return rows


def list_project_sessions(
    storage_dir: Path,
    project_path: Path,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List recent sessions for a project."""
    base = project_storage_base(storage_dir, project_path)
    entries = _read_index_file(base)
    result: list[dict[str, Any]] = []
    if entries:
        for entry in reversed(entries):
            session_file = _session_file_from_entry(base, entry)
            preview = _load_preview(session_file) if session_file else ""
            result.append({
                "session_id": entry.get("session_id"),
                "started_at": entry.get("started_at"),
                "ended_at": entry.get("ended_at"),
                "label": preview or entry.get("session_id"),
                "date": (entry.get("started_at") or "")[:10],
            })
            if len(result) >= limit:
                break
        return result
    return _list_sessions_from_directory(base, limit=limit)


def list_recent_date_sessions(
    storage_dir: Path,
    *,
    days: int = 7,
    limit: int = 40,
) -> list[dict[str, Any]]:
    """List sessions from the past N days (date mode)."""
    today = date.today()
    rows: list[dict[str, Any]] = []
    for offset in range(days):
        d = today - timedelta(days=offset)
        base = storage_dir / "dates" / d.isoformat()
        entries = _read_index_file(base)
        if entries:
            for entry in entries:
                session_file = _session_file_from_entry(base, entry)
                preview = _load_preview(session_file) if session_file else ""
                rows.append({
                    "session_id": entry.get("session_id"),
                    "started_at": entry.get("started_at"),
                    "ended_at": entry.get("ended_at"),
                    "label": preview or entry.get("session_id"),
                    "date": d.isoformat(),
                })
        else:
            rows.extend(_list_sessions_from_directory(
                base,
                limit=limit,
                date_label=d.isoformat(),
            ))
        if len(rows) >= limit:
            break
    rows.sort(key=lambda r: r.get("ended_at") or "", reverse=True)
    return rows[:limit]


def resolve_session_path(
    storage_dir: Path,
    session_id: str,
    *,
    project_path: Path | None = None,
    session_date: str | None = None,
    search_days: int = 7,
) -> Path | None:
    """Locate a session jsonl file."""
    if project_path:
        base = project_storage_base(storage_dir, project_path)
        session_path = base / SessionStore.SESSIONS_DIR / f"{session_id}.jsonl"
        if session_path.exists():
            return session_path

    if session_date:
        base = storage_dir / "dates" / session_date
        session_path = base / SessionStore.SESSIONS_DIR / f"{session_id}.jsonl"
        if session_path.exists():
            return session_path

    today = date.today()
    for offset in range(search_days):
        d = today - timedelta(days=offset)
        base = storage_dir / "dates" / d.isoformat()
        session_path = base / SessionStore.SESSIONS_DIR / f"{session_id}.jsonl"
        if session_path.exists():
            return session_path

    return None


def load_session_events(session_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not session_path.exists():
        return events
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def build_session_from_events(
    session_id: str,
    events: list[dict[str, Any]],
    *,
    project_path: Path | None = None,
) -> Session:
    session = Session.create(
        project_path=str(project_path) if project_path else None,
        session_id=session_id,
    )
    session.messages.clear()
    timestamps: list[float] = []
    pending_compact_summaries: list[str] = []
    for event in events:
        if event.get("type") == "compact":
            session.meta.compaction_count += 1
            before_count = int(event.get("before_count") or 0)
            summary = str(event.get("summary") or "").strip()
            if before_count > 0 and summary and session.messages:
                stable_prefix_end = _stable_compact_prefix_end(session.messages)
                tail_start = min(len(session.messages), stable_prefix_end + before_count)
                summary_msg = Message(role="system")
                summary_msg.created_at = float(event.get("timestamp") or summary_msg.created_at)
                summary_msg.add_text(summary)
                session.messages = [
                    *session.messages[:stable_prefix_end],
                    summary_msg,
                    *session.messages[tail_start:],
                ]
                pending_compact_summaries.append(summary)
                timestamps.append(summary_msg.created_at)
            continue

        msg = Message.from_record(event)
        if msg:
            if (
                msg.role == "system"
                and pending_compact_summaries
                and msg.get_text().strip() == pending_compact_summaries[0]
            ):
                pending_compact_summaries.pop(0)
                continue
            session.messages.append(msg)
            timestamps.append(float(msg.created_at))

    if timestamps:
        created = min(timestamps)
        updated = max(timestamps)
        session.meta.created_at = datetime.fromtimestamp(created)
        session.meta.updated_at = datetime.fromtimestamp(updated)
    return session


def create_session_store(
    storage_dir: Path,
    project_path: Path | None,
    *,
    base_override: Path | None = None,
) -> SessionStore:
    store = SessionStore(
        storage_dir=storage_dir,
        project_root=project_path,
    )
    if base_override is not None:
        store._base = base_override  # type: ignore[attr-defined]
    elif project_path is None:
        # SessionStore.__init__ 在 project_root=None 时会从 CWD 自动向上检测 .git，
        # 若服务器恰好在某个 git 仓库内运行，就会错误地切换到 project 模式，
        # 导致日期模式的 session 被写入 projects/ 而不是 dates/。
        # 显式调用 set_date_mode() 覆盖这一自动检测结果。
        store.set_date_mode()
    return store


def serialize_messages(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert raw events to simplified chat messages for the UI."""
    messages: list[dict[str, Any]] = []
    for event in events:
        msg = Message.from_record(event)
        if not msg:
            continue
        text = msg.get_text()
        if not text and msg.role != "assistant":
            continue
        tool_info = _extract_tool_payload(msg.role, text)
        if tool_info:
            tool_name, tool_output = tool_info
            messages.append({
                "role": "tool",
                "tool_name": tool_name,
                "content": tool_output,
                "timestamp": msg.created_at,
            })
            continue
        messages.append({
            "role": msg.role,
            "content": text,
            "timestamp": msg.created_at,
        })
    return messages


def _extract_tool_payload(role: str, content: str) -> tuple[str, str] | None:
    if role != "user":
        return None
    if not content.startswith("[tool:"):
        return None
    header, _, body = content.partition("]\n")
    if not body:
        body = content[len(header) + 1 :]
    name = header[6:].strip(" []")
    body = body.strip()
    return name or "tool", body
