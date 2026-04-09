import json
from datetime import date
from pathlib import Path

from auton.agent.session_store import SessionStore
from auton.memory.storage_utils import project_storage_base


def _write_session_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "user-message", "content": content}
    path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")


def test_project_mode_limits_memory_sources(tmp_path: Path) -> None:
    storage_dir = tmp_path / "memory"
    project_root = tmp_path / "proj"
    other_project = tmp_path / "other"
    project_root.mkdir()
    other_project.mkdir()

    own_sessions = project_storage_base(storage_dir, project_root) / "sessions"
    other_sessions = project_storage_base(storage_dir, other_project) / "sessions"

    _write_session_file(own_sessions / "own.jsonl", "own project")
    _write_session_file(other_sessions / "other.jsonl", "other project")
    _write_session_file(
        storage_dir / "dates" / "2024-01-02" / "sessions" / "chat.jsonl",
        "global chat",
    )

    store = SessionStore(storage_dir=storage_dir, project_root=project_root)
    assert store.mode == "project"

    assert store.read_session_by_id("own")  # same project is accessible
    assert store.read_session_by_id("other") == []
    assert store.read_session_by_id("chat") == []


def test_date_mode_can_access_all_memory_sources(tmp_path: Path, monkeypatch) -> None:
    storage_dir = tmp_path / "memory"
    storage_dir.mkdir()
    project_root = tmp_path / "proj"
    project_root.mkdir()

    today = date.today().isoformat()
    _write_session_file(
        storage_dir / "dates" / today / "sessions" / "today_chat.jsonl",
        "today chat",
    )
    _write_session_file(
        storage_dir / "dates" / "2000-01-01" / "sessions" / "old_chat.jsonl",
        "old chat",
    )
    _write_session_file(
        project_storage_base(storage_dir, project_root) / "sessions" / "project_sid.jsonl",
        "project history",
    )

    # 确保 _find_project_root() 不会找到当前仓库
    monkeypatch.chdir(tmp_path)
    store = SessionStore(storage_dir=storage_dir)
    assert store.mode == "date"

    assert store.read_session_by_id("today_chat")
    assert store.read_session_by_id("old_chat")
    assert store.read_session_by_id("project_sid")


def test_read_session_scope_all_cross_project(tmp_path: Path) -> None:
    storage_dir = tmp_path / "memory"
    project_root = tmp_path / "proj"
    other_project = tmp_path / "other"
    project_root.mkdir()
    other_project.mkdir()

    other_sessions = project_storage_base(storage_dir, other_project) / "sessions"
    _write_session_file(other_sessions / "cross.jsonl", "cross project")

    store = SessionStore(storage_dir=storage_dir, project_root=project_root)
    assert store.read_session_by_id("cross") == []
    assert store.read_session_by_id("cross", scope="all")


def test_set_date_mode_overrides_project(tmp_path: Path) -> None:
    storage_dir = tmp_path / "memory"
    project_root = tmp_path / "proj"
    project_root.mkdir()

    store = SessionStore(storage_dir=storage_dir, project_root=project_root)
    assert store.mode == "project"

    specific_date = date(2024, 1, 2)
    store.set_date_mode(specific_date)
    assert store.mode == "date"
    assert store.base == storage_dir / "dates" / specific_date.isoformat()
