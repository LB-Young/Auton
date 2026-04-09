"""E2E: 启动问候记忆模式关键逻辑测试。"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auton.agent.session_store import SessionStore
from auton.cli.greeting_context import collect_greeting_context
from auton.cli.greeting_generator import build_greeting_prompt
from auton.cli.project_mode_intent import parse_project_mode_reply
from auton.memory.global_memory import GlobalMemory
from auton.memory.storage_utils import project_storage_dir_name


def test_has_existing_project_history():
    storage_dir = Path(tempfile.mkdtemp(prefix="auton_test_history_")) / "memory"
    project_dir = storage_dir / "projects" / project_storage_dir_name(Path("/tmp/demo"))
    project_dir.mkdir(parents=True, exist_ok=True)

    store = SessionStore(storage_dir=storage_dir)
    assert store.has_existing_project_history(Path("/tmp/demo")) is True
    assert store.has_existing_project_history(Path("/tmp/other")) is False


def test_archive_session_updates_project_modify():
    temp_root = Path(tempfile.mkdtemp(prefix="auton_test_archive_"))
    storage_dir = temp_root / "memory"
    project_root = temp_root / "workspace" / "demo"
    project_root.mkdir(parents=True, exist_ok=True)

    store = SessionStore(storage_dir=storage_dir, project_root=project_root)
    session_id = "session_for_project_modify"

    # 先写一个 session 事件，确保路径存在
    store.append_event(session_id, {"type": "user-message", "content": "hello"})
    store.archive_session(
        session_id=session_id,
        started_at="2026-01-01T00:00:00",
        ended_at="2026-01-01T00:10:00",
        compaction_count=0,
    )

    project_modify = storage_dir / "project_modify.md"
    assert project_modify.exists()
    content = project_modify.read_text(encoding="utf-8")
    expected_rel = store.session_path(session_id).relative_to(storage_dir)
    assert str(expected_rel) in content


def test_collect_greeting_context_reads_dates_and_project_modify():
    storage_dir = Path(tempfile.mkdtemp(prefix="auton_test_greeting_ctx_")) / "memory"
    gm = GlobalMemory(storage_dir)

    today = date.today()
    yesterday = gm.get_today_and_yesterday()[1]
    gm.append_memory_entry(today, "- 今天处理了启动问候优化")
    gm.append_memory_entry(yesterday, "- 昨天整理了记忆索引")

    project_dir = storage_dir / "projects" / project_storage_dir_name(Path("/tmp/demo"))
    project_memory = project_dir / "memory"
    project_memory.mkdir(parents=True, exist_ok=True)
    (project_memory / "MEMORY.md").write_text(
        "本文档是项目记忆顶层索引。\n- 项目最近修复了 session 模式判断\n",
        encoding="utf-8",
    )
    session_path = project_dir / "sessions" / "sid.jsonl"
    gm.record_project_session_path(today, str(session_path))

    ctx = collect_greeting_context(
        storage_dir=storage_dir,
        cwd=Path("/tmp/demo"),
        has_project_history=False,
    )
    assert ctx.should_ask_project_mode is True
    assert any("启动问候优化" in s for s in ctx.date_memory_snippets)
    assert any("session 模式判断" in s for s in ctx.project_memory_snippets)

    prompt = build_greeting_prompt(ctx)
    assert "是否按项目模式开启" in prompt


def test_parse_project_mode_reply():
    assert parse_project_mode_reply("是，按项目模式开启") is True
    assert parse_project_mode_reply("不用，按闲聊模式就行") is False
    assert parse_project_mode_reply("不是项目模式，先别切") is False
    assert parse_project_mode_reply("不可以项目模式") is False
    assert parse_project_mode_reply("我们先看看") is None
