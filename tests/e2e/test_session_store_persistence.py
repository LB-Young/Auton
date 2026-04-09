"""E2E Test 3: SessionStore 持久化与回放

测试路径：
  Session.add_user_message → session_store.append_user_message() → jsonl 写入
  → SessionProcessor.run_stream → append_assistant_message / append_tool_result
  → session_store.archive_session() → index.jsonl 更新

目的：
  - 理解 append-only 存储模型（永不修改已有行）
  - 理解 session_store 的完整写入生命周期
  - 理解 index.jsonl 的归档机制
  - 可以在以下位置打断点：
      - auton/agent/session_store.py:50  (append_event)
      - auton/agent/session_store.py:60  (append_message)
      - auton/agent/session_store.py:97  (append_assistant_message)
      - auton/agent/session_store.py:130 (archive_session)
      - auton/agent/agent.py:81          (store user message)
      - auton/agent/agent.py:113         (store assistant message)

运行方式：
  pytest tests/e2e/test_session_store_persistence.py -v
  python -m tests.e2e.test_session_store_persistence
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncIterator

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from auton.agent.session import Session
from auton.agent.session_store import SessionStore
from auton.agent.agent import SessionProcessor
from auton.agent.types import LLMContext
from auton.llm.base import (
    LLMProvider,
    LLMStreamEvent,
    TextStartEvent,
    TextDeltaEvent,
    TextFinishEvent,
)


# ─── Mock LLM：多轮对话模拟 ───────────────────────────────────────────────────

class MockMultiturnProvider(LLMProvider):
    """模拟多轮对话回复"""

    def __init__(self) -> None:
        super().__init__(model="mock-model")
        self._round = 0

    async def stream(self, ctx: LLMContext) -> AsyncIterator[LLMStreamEvent]:
        self._round += 1
        responses = {
            1: "收到你的第一条消息。",
            2: "收到你的第二条消息。",
        }
        text = responses.get(self._round, "消息已收到。")
        yield TextStartEvent()
        for ch in text:
            yield TextDeltaEvent(delta=ch)
        yield TextFinishEvent(full_text=text)


# ─── 测试 ────────────────────────────────────────────────────────────────────

async def test_session_store_persistence():
    """端到端：验证 SessionStore 的完整写入生命周期"""

    import tempfile

    storage_dir = Path(tempfile.mkdtemp(prefix="auton_test_store_"))
    session_store = SessionStore(storage_dir)
    session = Session.create()

    # ── 手动模拟写入流程（不启动完整 processor）───────────────────────────────
    q1 = "这是我的第一个问题"
    q2 = "这是我的第二个问题"

    session.add_user_message(q1)

    # 模拟 user message 存储
    session_store.append_user_message(session.meta.session_id, q1)
    session_store.append_system_message(session.meta.session_id, "System prompt here")

    session.add_assistant_message()
    # 模拟 assistant message 存储（包含 tool_result 等）
    session_store.append_assistant_message(session.meta.session_id, session.messages[-1])

    session.add_user_message(q2)
    session_store.append_user_message(session.meta.session_id, q2)

    session.add_assistant_message()
    session_store.append_assistant_message(session.meta.session_id, session.messages[-1])

    # 模拟会话结束归档
    session_store.archive_session(
        session_id=session.meta.session_id,
        started_at=session.meta.created_at.isoformat(),
        ended_at=session.meta.updated_at.isoformat(),
        compaction_count=0,
    )

    # ── 验证 jsonl 内容 ───────────────────────────────────────────────────────
    session_path = session_store.session_path(session.meta.session_id)
    assert session_path.exists(), f"Session file not created: {session_path}"

    lines: list[dict] = []
    with open(session_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))

    assert len(lines) >= 4, f"Expected >= 4 events, got {len(lines)}"

    # 验证事件类型顺序：user → system → assistant → user → assistant → archive
    types = [e.get("type") for e in lines]
    assert types[0] == "user-message", f"First event should be user-message, got: {types[0]}"
    assert "user-message" in types  # 至少 2 个 user-message
    assert types.count("user-message") == 2, f"Expected 2 user messages, got: {types}"

    # 验证 index.jsonl
    index_path = session_store.index_path()
    assert index_path.exists(), "index.jsonl not created"

    index_entries: list[dict] = []
    with open(index_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                index_entries.append(json.loads(line))

    assert len(index_entries) >= 1
    entry = index_entries[-1]
    assert entry["session_id"] == session.meta.session_id
    assert "started_at" in entry
    assert "ended_at" in entry
    assert entry["compaction_count"] == 0

    # ── 验证读取回放（read_session）───────────────────────────────────────────
    replayed = session_store.read_session(session.meta.session_id)
    assert len(replayed) == len(lines), "read_session should return all lines"
    assert replayed[0]["content"] == q1
    assert replayed[3]["content"] == q2

    print(f"\n[PASS] test_session_store_persistence")
    print(f"  session_id  : {session.meta.session_id}")
    print(f"  events      : {len(lines)}")
    print(f"  event_types : {types}")
    print(f"  index_entry : {entry['session_id']}")
    print(f"  storage_dir : {storage_dir}")

    # 打印 jsonl 内容（方便肉眼核对）
    print(f"\n  jsonl content:")
    for i, line in enumerate(lines):
        print(f"    [{i}] {json.dumps(line, ensure_ascii=False)[:100]}")


if __name__ == "__main__":
    asyncio.run(test_session_store_persistence())
