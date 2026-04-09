from fastapi import HTTPException

from auton.agent.message import Message
from auton.agent.session import Session
from auton.agent.session_store import SessionStore
from auton.web.app import (
    _build_project_context_message,
    _ensure_project_path,
    _inject_project_context_message,
)
from auton.web.session_utils import build_session_from_events


def test_ensure_project_path_non_strict_returns_none(tmp_path):
    missing = tmp_path / "missing"
    assert _ensure_project_path(str(missing), strict=False) is None


def test_ensure_project_path_strict_raises(tmp_path):
    missing = tmp_path / "missing"
    try:
        _ensure_project_path(str(missing))
    except HTTPException as exc:
        assert exc.status_code == 400
    else:  # pragma: no cover
        assert False, "Expected HTTPException for missing path"


def test_build_project_context_message_readme(tmp_path):
    project = tmp_path / "demo"
    project.mkdir()
    readme = project / "README.md"
    readme.write_text("Demo project README", encoding="utf-8")
    text = _build_project_context_message(project)
    assert "demo" in text.lower()
    assert "README" in text
    assert "Demo project README" in text


def test_inject_project_context_message_persists(tmp_path):
    storage_dir = tmp_path / "memory"
    project = tmp_path / "proj"
    project.mkdir()
    (project / "README.md").write_text("hello context", encoding="utf-8")
    session = Session.create()
    store = SessionStore(storage_dir=storage_dir)
    _inject_project_context_message(session, store, project, is_new_session=True)
    assert session.messages
    assert session.messages[0].role == "system"
    assert "hello context" in session.messages[0].get_text()
    events = store.read_session(session.meta.session_id)
    assert any(ev.get("type") == "system" for ev in events)


def test_build_session_from_events_replays_compacted_shape():
    events = [
        {"type": "system", "content": "系统提示", "timestamp": 1},
        {"type": "user-message", "content": "任务 1", "timestamp": 2},
        {"role": "assistant", "parts": [{"type": "text", "content": "完成 1"}], "message_id": "a1", "created_at": 3},
        {"type": "user-message", "content": "任务 2", "timestamp": 4},
        {"role": "assistant", "parts": [{"type": "text", "content": "完成 2"}], "message_id": "a2", "created_at": 5},
        {"type": "user-message", "content": "任务 3", "timestamp": 6},
        {"role": "assistant", "parts": [{"type": "text", "content": "完成 3"}], "message_id": "a3", "created_at": 7},
        {
            "type": "compact",
            "session_id": "s1",
            "timestamp": 8,
            "before_count": 4,
            "summary": "[历史压缩] 合并 4 条消息，保留关键信息：\n- [user] 任务 1\n- [assistant] 完成 1",
        },
        {
            "type": "system",
            "content": "[历史压缩] 合并 4 条消息，保留关键信息：\n- [user] 任务 1\n- [assistant] 完成 1",
            "timestamp": 9,
        },
    ]

    session = build_session_from_events("s1", events)

    texts = [msg.get_text() for msg in session.messages]
    assert texts == [
        "系统提示",
        "[历史压缩] 合并 4 条消息，保留关键信息：\n- [user] 任务 1\n- [assistant] 完成 1",
        "任务 3",
        "完成 3",
    ]
    assert session.meta.compaction_count == 1


def test_build_session_from_events_replays_multiple_compacts(tmp_path):
    store = SessionStore(storage_dir=tmp_path / "memory")
    session = Session.create()
    system = Message(role="system")
    system.add_text("系统提示")
    session.messages.append(system)
    store.append_system_message(session.meta.session_id, "系统提示")

    for user_text, assistant_text in [
        ("任务 1", "完成 1"),
        ("任务 2", "完成 2"),
        ("任务 3", "完成 3"),
        ("任务 4", "完成 4"),
    ]:
        session.add_user_message(user_text)
        store.append_user_message(session.meta.session_id, user_text)
        assistant = session.add_assistant_message()
        assistant.add_text(assistant_text)
        store.append_assistant_message(session.meta.session_id, assistant)

    first = session.compact(protect_turns=1, recent_token_budget=10_000)
    store.append_compact_event(
        session.meta.session_id,
        before_count=first.compacted_count,
        summary=first.summary_text,
        meta={"summary_message_id": first.summary_message_id},
    )
    store.append_system_message(session.meta.session_id, first.summary_text)

    session.add_user_message("任务 5")
    store.append_user_message(session.meta.session_id, "任务 5")
    assistant = session.add_assistant_message()
    assistant.add_text("完成 5")
    store.append_assistant_message(session.meta.session_id, assistant)

    second = session.compact(protect_turns=1, recent_token_budget=10_000)
    store.append_compact_event(
        session.meta.session_id,
        before_count=second.compacted_count,
        summary=second.summary_text,
        meta={"summary_message_id": second.summary_message_id},
    )
    store.append_system_message(session.meta.session_id, second.summary_text)

    rebuilt = build_session_from_events(
        session.meta.session_id,
        store.read_session(session.meta.session_id),
    )

    assert [msg.get_text() for msg in rebuilt.messages] == [
        msg.get_text() for msg in session.messages
    ]
    assert rebuilt.meta.compaction_count == session.meta.compaction_count
