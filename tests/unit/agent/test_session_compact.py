from auton.agent.session import Session
from auton.agent.message import Message
from auton.agent.agent import SessionProcessor
from auton.agent.session_store import SessionStore
from auton.agent.policies import DecisionPolicy
from auton.agent.types import LLMContext
from auton.llm.base import LLMProvider


def _prepare_session(rounds: list[tuple[str, str]]) -> Session:
    session = Session.create()
    system_msg = Message(role="system")
    system_msg.add_text("系统提示")
    session.messages.append(system_msg)
    for user_text, assistant_text in rounds:
        session.add_user_message(user_text)
        assistant = session.add_assistant_message()
        assistant.add_text(assistant_text)
    return session


def test_compact_preserves_recent_rounds():
    rounds = [
        ("任务 1", "完成 1"),
        ("任务 2", "完成 2"),
        ("任务 3", "完成 3"),
        ("任务 4", "完成 4"),
    ]
    session = _prepare_session(rounds)

    result = session.compact(protect_turns=1, recent_token_budget=10_000)

    assert result.compacted_count > 0
    assert "[历史压缩]" in result.summary_text
    assert any("任务 1" in line for line in result.summary_text.splitlines())

    # 检查结构：系统消息 + 摘要 + 最近两轮
    assert session.messages[0].role == "system"
    assert session.messages[1].role == "system"
    assert "历史压缩" in session.messages[1].get_text()
    recent_roles = [m.role for m in session.messages[-4:]]
    assert recent_roles.count("user") >= 1 and recent_roles.count("assistant") >= 1


def test_compact_forces_long_recent_history():
    long_text = "x" * 50_000
    rounds = [
        ("旧1", "答1"),
        ("旧2", "答2"),
        (long_text, "答3"),
    ]
    session = _prepare_session(rounds)

    result = session.compact(protect_turns=2, recent_token_budget=1_000)

    # 最近的大段落也被压缩
    assert result.compacted_count >= 2
    assert long_text[:50] not in "".join(m.get_text() for m in session.messages[2:])


class _UnusedProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__(model="mock-model")

    async def stream(self, ctx: LLMContext):
        if False:  # pragma: no cover
            yield ctx


async def test_compact_command_executes_immediately(tmp_path):
    session = _prepare_session([
        ("任务 1", "完成 1"),
        ("任务 2", "完成 2"),
        ("任务 3", "完成 3"),
        ("任务 4", "完成 4"),
    ])
    store = SessionStore(storage_dir=tmp_path / "memory")
    processor = SessionProcessor(
        session=session,
        llm=_UnusedProvider(),
        tools=[],
        session_store=store,
    )

    session.add_user_message("/compact")
    events = []
    async for event in processor.run_stream():
        events.append(event)

    command_events = [event for event in events if hasattr(event, "content")]
    assert command_events, "expected /compact to yield a visible command result"
    assert "已压缩" in command_events[0].content
    assert session.messages[-1].role != "user" or session.messages[-1].get_text() != "/compact"
    assert any("历史压缩" in msg.get_text() for msg in session.messages if msg.role == "system")

    stored = store.read_session(session.meta.session_id)
    assert any(event.get("type") == "compact" for event in stored)
    rebuilt = Session.create(session_id=session.meta.session_id)
    rebuilt.messages.clear()
    from auton.adapters.web.session_utils import build_session_from_events
    replayed = build_session_from_events(session.meta.session_id, stored)
    assert [msg.get_text() for msg in replayed.messages] == [
        msg.get_text() for msg in session.messages
    ]


def test_compact_does_not_summarize_previous_compact_summary():
    session = _prepare_session([
        ("任务 1", "完成 1"),
        ("任务 2", "完成 2"),
        ("任务 3", "完成 3"),
        ("任务 4", "完成 4"),
    ])

    first = session.compact(protect_turns=1, recent_token_budget=10_000)
    assert first.compacted_count > 0

    session.add_user_message("任务 5")
    assistant = session.add_assistant_message()
    assistant.add_text("完成 5")

    second = session.compact(protect_turns=1, recent_token_budget=10_000)

    assert second.compacted_count > 0
    assert "[system] [历史压缩]" not in second.summary_text


def test_compact_preserves_latest_tool_turn_as_one_unit():
    session = Session.create()
    system_msg = Message(role="system")
    system_msg.add_text("系统提示")
    session.messages.append(system_msg)

    session.add_user_message("普通问题")
    assistant = session.add_assistant_message()
    assistant.add_text("普通回答")

    session.add_user_message("请查一下天气")
    tool_call = session.add_assistant_message()
    tool_call.add_text("我先调用工具查询。")
    tool_result = Message(role="user")
    tool_result.add_text("[tool: weather]\n晴天 24 度")
    session.messages.append(tool_result)
    final = session.add_assistant_message()
    final.add_text("今天晴天，24 度。")

    session.compact(protect_turns=1, recent_token_budget=10_000)

    texts = [msg.get_text() for msg in session.messages]
    assert "请查一下天气" in texts
    assert "[tool: weather]\n晴天 24 度" in texts
    assert "今天晴天，24 度。" in texts
    assert "普通问题" not in texts


async def test_compact_command_uses_policy_parameters(tmp_path):
    session = _prepare_session([
        ("旧任务 1", "旧完成 1"),
        ("旧任务 2", "旧完成 2"),
        ("旧任务 3", "旧完成 3"),
    ])
    expected = _prepare_session([
        ("旧任务 1", "旧完成 1"),
        ("旧任务 2", "旧完成 2"),
        ("旧任务 3", "旧完成 3"),
    ])
    long_text = "x" * 50_000
    for target in (session, expected):
        target.add_user_message(long_text)
        assistant = target.add_assistant_message()
        assistant.add_text("长回复")

    expected.compact(protect_turns=2, recent_token_budget=1_000)

    store = SessionStore(storage_dir=tmp_path / "memory")
    processor = SessionProcessor(
        session=session,
        llm=_UnusedProvider(),
        tools=[],
        session_store=store,
        policy=DecisionPolicy(recent_protect_turns=2, recent_token_budget=1_000),
    )

    session.add_user_message("/compact")
    async for _ in processor.run_stream():
        pass

    assert [msg.get_text() for msg in session.messages] == [
        msg.get_text() for msg in expected.messages
    ]


async def test_compact_command_executes_in_non_stream_path(tmp_path):
    session = _prepare_session([
        ("任务 1", "完成 1"),
        ("任务 2", "完成 2"),
        ("任务 3", "完成 3"),
    ])
    store = SessionStore(storage_dir=tmp_path / "memory")
    processor = SessionProcessor(
        session=session,
        llm=_UnusedProvider(),
        tools=[],
        session_store=store,
    )

    session.add_user_message("/compact")
    result = await processor.run()

    assert result.status == "stop"
    assert "已压缩" in result.reason
    assert processor.last_command_result is not None
    assert "已压缩" in processor.last_command_result.content
    assert all(msg.get_text() != "/compact" for msg in session.messages if msg.role == "user")
    stored = store.read_session(session.meta.session_id)
    assert any(event.get("type") == "compact" for event in stored)
    from auton.adapters.web.session_utils import build_session_from_events
    replayed = build_session_from_events(session.meta.session_id, stored)
    assert [msg.get_text() for msg in replayed.messages] == [
        msg.get_text() for msg in session.messages
    ]
