from datetime import date
import json
from pathlib import Path

from auton.memory.storage_utils import project_storage_base
from auton.adapters.web.session_utils import (
    build_session_from_events,
    list_project_sessions,
    list_recent_date_sessions,
    serialize_messages,
)


def test_serialize_messages_skips_empty():
    events = [
        {"type": "user-message", "content": "你好"},
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "content": "您好！"},
            ],
        },
        {
            "role": "user",
            "parts": [
                {"type": "text", "content": "[tool: read]\n这里是结果"},
            ],
        },
    ]
    messages = serialize_messages(events)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[1]["content"] == "您好！"
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_name"] == "read"
    assert messages[2]["content"] == "这里是结果"


def test_build_session_from_events_preserves_history(tmp_path: Path):
    session_id = "test-session"
    events = [
        {"type": "user-message", "content": "hi", "timestamp": 1},
        {
            "role": "assistant",
            "parts": [{"type": "text", "content": "hello"}],
            "created_at": 2,
        },
    ]
    session = build_session_from_events(session_id, events)
    assert session.meta.session_id == session_id
    assert len(session.messages) == 2
    assert session.messages[0].get_text() == "hi"


def test_list_project_sessions_fallbacks_without_index(tmp_path: Path):
    storage_dir = tmp_path / "memory"
    storage_dir.mkdir()
    project_path = tmp_path / "proj"
    project_path.mkdir()
    base = project_storage_base(storage_dir, project_path)
    session_file = base / "sessions" / "abc.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps({"type": "user-message", "content": "hello"}) + "\n", encoding="utf-8")

    sessions = list_project_sessions(storage_dir, project_path)
    assert sessions
    assert sessions[0]["session_id"] == "abc"
    assert "hello" in sessions[0]["label"]


def test_list_recent_date_sessions_fallbacks_without_index(tmp_path: Path):
    storage_dir = tmp_path / "memory"
    storage_dir.mkdir()
    today = date.today().isoformat()
    session_file = storage_dir / "dates" / today / "sessions" / "sid.jsonl"
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(json.dumps({"type": "user-message", "content": "hi"}) + "\n", encoding="utf-8")

    sessions = list_recent_date_sessions(storage_dir, days=1, limit=5)
    assert sessions
    assert sessions[0]["session_id"] == "sid"
    assert sessions[0]["date"] == today
