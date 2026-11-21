import asyncio
import json
from pathlib import Path
from typing import cast

import pytest
from test_agent import agent as agent
from test_agent import command as control
from test_agent import context as context
from test_agent import generate, result, wait
from test_context import USER

from auton.agent.contracts import AgentRun, CreateRun, checkpoint_event_id
from auton.agent.service import AgentRuntime
from auton.assess.checkers import DeterministicChecker
from auton.constitution.config import Principal
from auton.conversation.contracts import (
    ConversationCreate,
    ConversationTurn,
)
from auton.conversation.factory import WorkspaceConversationFactory
from auton.conversation.ports import WorkspaceConversationPort
from auton.conversation.service import ConversationDependencies
from auton.genome.ports import GenomePort
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult, ToolCall


def service(agent: AgentRuntime) -> WorkspaceConversationPort:
    return WorkspaceConversationFactory().create(
        ConversationDependencies(
            agent,
            cast(GenomePort, agent.deps.assets),
            agent.deps.tools,
            agent.deps.models,
            agent.deps.events,
            agent.deps.runtime,
        ),
        Path(agent.config.directory) / "conversation-history",
    )


async def test_conversation_multiturn_persistence_idempotency_and_owner_isolation(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[ModelRequest] = []

    async def respond(request: ModelRequest) -> ModelResult:
        calls.append(request)
        return result(request, "好的，小李。" if len(calls) == 1 else "你叫小李。")

    generate(agent, monkeypatch, respond)
    conversations = service(agent)
    create = ConversationCreate(request_id="chat", title="记住名字")
    conversation = await conversations.create(USER, create)
    assert await conversations.create(USER, create) == conversation
    first = ConversationTurn(
        request_id="first", expected_turns=0, text="我叫小李", model_id="fixture-model"
    )
    run = await conversations.send(USER, conversation.id, first)
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert done.check and done.check.checker == "response-present-v1"
    assert done.judgment_ids, "Conversation must retain the decision trajectory"
    checkpoint = await agent.deps.events.lookup(
        checkpoint_event_id(USER.owner, done.id, done.version)
    )
    assert checkpoint is not None
    signals = await DeterministicChecker(agent.deps.tools, agent.deps.context).check(
        USER, done, checkpoint, None
    )
    assert not any(signal.name == "citation_structure" for signal in signals)
    business = next(signal for signal in signals if signal.name == "business")
    assert business.verdict == "unknown", "A nonempty chat response is not verified task quality"

    # A new service instance represents a process-independent view of the same durable events.
    restored = service(agent)
    assert (await restored.send(USER, conversation.id, first)).id == run.id
    second = await restored.send(
        USER,
        conversation.id,
        ConversationTurn(
            request_id="second",
            expected_turns=1,
            text="我叫什么？",
            model_id="fixture-model",
        ),
    )
    assert (await wait(agent, second.id)).status == "succeeded"
    assert any(m.content == "我叫小李" for m in calls[-1].messages)
    assert any(m.role == "assistant" and m.content == "好的，小李。" for m in calls[-1].messages)
    assert len((await restored.view(USER, conversation.id)).turns) == 2
    assert len(calls) == 2
    assert [c.id for c in await restored.list(USER)] == [conversation.id]
    other = Principal(owner="another-owner", role="user")
    assert await restored.list(other) == []
    with pytest.raises(ApplicationError, match="No owned conversation"):
        await restored.view(other, conversation.id)
    with pytest.raises(ApplicationError) as conflict:
        await restored.send(USER, conversation.id, first.model_copy(update={"text": "changed"}))
    assert conflict.value.code == "conversation_turn_conflict"


async def test_conversation_rejects_remote_without_consent_and_overlapping_turns(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="concurrent", title="Concurrent")
    )
    catalog = agent.deps.models.catalog(USER)
    monkeypatch.setattr(
        agent.deps.models,
        "catalog",
        lambda principal=None: [m.model_copy(update={"location": "remote"}) for m in catalog],
    )
    first = ConversationTurn(
        request_id="one", expected_turns=0, text="hello", model_id="fixture-model"
    )
    with pytest.raises(ApplicationError) as denied:
        await conversations.send(USER, conversation.id, first)
    assert denied.value.code == "conversation_remote_consent"
    assert not (await conversations.view(USER, conversation.id)).turns
    monkeypatch.setattr(agent.deps.models, "catalog", lambda principal=None: catalog)
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request: ModelRequest) -> ModelResult:
        started.set()
        await release.wait()
        return result(request, "hello")

    generate(agent, monkeypatch, respond)
    run = await conversations.send(USER, conversation.id, first)
    await asyncio.wait_for(started.wait(), 5)
    try:
        with pytest.raises(ApplicationError) as active:
            await conversations.send(
                USER,
                conversation.id,
                first.model_copy(update={"expected_turns": 1, "request_id": "two"}),
            )
        assert active.value.code == "conversation_turn_active"
    finally:
        release.set()
    assert (await wait(agent, run.id)).status == "succeeded"


async def test_conversation_file_effects_keep_exact_approval_gate(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="write", title="写文件")
    )

    async def respond(request: ModelRequest) -> ModelResult:
        if any(m.role == "tool" for m in request.messages):
            return result(request, "已写入文件。")
        return result(
            request,
            calls=(
                ToolCall(
                    id="write",
                    name="file_write",
                    arguments={"path": "hello.txt", "content": "hello"},
                ),
            ),
        )

    generate(agent, monkeypatch, respond)
    run = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(
            request_id="write-turn",
            expected_turns=0,
            text="创建 hello.txt",
            model_id="fixture-model",
        ),
    )
    pending = await wait(agent, run.id)
    assert pending.status == "waiting_approval"
    assert not pending.receipts
    await control(agent, pending, "approve")
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert done.receipts[-1].outcome == "succeeded"
    assert done.check and done.check.checker == "response-present-v1"


async def test_disconnected_sender_does_not_orphan_or_repeat_the_turn(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="disconnect", title="Disconnect")
    )
    created, release = asyncio.Event(), asyncio.Event()
    original = agent.create

    async def delayed_create(principal: Principal, command: CreateRun) -> AgentRun:
        run = await original(principal, command)
        created.set()
        await release.wait()
        return run

    monkeypatch.setattr(agent, "create", delayed_create)
    first = ConversationTurn(
        request_id="disconnect-turn", expected_turns=0, text="hello", model_id="fixture-model"
    )
    sender = asyncio.create_task(conversations.send(USER, conversation.id, first))
    await asyncio.wait_for(created.wait(), 5)
    sender.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sender
    release.set()
    await conversations.close()
    restored = service(agent)
    view = await restored.view(USER, conversation.id)
    assert len(view.turns) == 1
    assert (await restored.send(USER, conversation.id, first)).id == view.turns[0].id
    await wait(agent, view.turns[0].id)


async def test_text_only_local_executor_does_not_require_tool_protocol(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = agent.deps.models.catalog(USER)
    monkeypatch.setattr(
        agent.deps.models,
        "catalog",
        lambda principal=None: [m.model_copy(update={"capabilities": ("text",)}) for m in catalog],
    )
    calls: list[ModelRequest] = []

    async def respond(request: ModelRequest) -> ModelResult:
        calls.append(request)
        return result(request, "你好！")

    generate(agent, monkeypatch, respond)
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="text-only", title="Text only")
    )
    run = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(
            request_id="greet",
            expected_turns=0,
            text="hi",
            model_id="fixture-model",
        ),
    )
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert not done.command.allowed_tools
    assert not calls[-1].tools


async def test_selected_project_is_persistently_bound_and_read_through_agent_tools(
    agent: AgentRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "selected"
    project.mkdir()
    (project / "README.md").write_text("This is the selected project, marker: selected-project.")
    conversations = service(agent)
    create = ConversationCreate(
        request_id="selected-project",
        title="分析项目",
        project_path=str(project / ".." / "selected"),
    )
    conversation = await conversations.create(USER, create)
    assert conversation.project_path == str(project.resolve())
    assert await conversations.create(USER, create) == conversation
    calls: list[ModelRequest] = []

    async def respond(request: ModelRequest) -> ModelResult:
        calls.append(request)
        if len(calls) == 1:
            return result(
                request, calls=(ToolCall(id="list", name="file_list", arguments={"path": ""}),)
            )
        if len(calls) == 2:
            return result(
                request,
                calls=(ToolCall(id="read", name="file_read", arguments={"path": "README.md"}),),
            )
        assert any(
            m.role == "tool" and "selected-project" in (m.content or "") for m in request.messages
        )
        return result(request, "已读取所选项目的 README。")

    generate(agent, monkeypatch, respond)
    run = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(
            request_id="analyze", expected_turns=0, text="分析这个项目", model_id="fixture-model"
        ),
    )
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert [receipt.tool for receipt in done.receipts] == ["file.list", "file.read"]
    assert (await agent.deps.tools.workspace(USER, conversation.workspace_id)).root_path == str(
        project.resolve()
    )
    restored = await service(agent).view(USER, conversation.id)
    assert restored.conversation.project_path == str(project.resolve())
    assert len(restored.turns) == 1


async def test_history_path_exports_owned_durable_snapshot_and_refreshes_same_file(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="history", title="历史分析")
    )
    calls = 0

    async def respond(request: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        return result(request, f"第 {calls} 轮回复")

    generate(agent, monkeypatch, respond)
    first = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(request_id="one", expected_turns=0, text="你好", model_id="fixture-model"),
    )
    await wait(agent, first.id)
    record = await conversations.export_history(USER, conversation.id)
    path = Path(record.path)
    assert path.is_absolute() and (await asyncio.to_thread(path.is_file))
    assert (await asyncio.to_thread(path.stat)).st_mode & 0o777 == 0o600
    assert (await asyncio.to_thread(path.parent.stat)).st_mode & 0o777 == 0o700
    body = json.loads(await asyncio.to_thread(path.read_text))
    assert body["durable_snapshot"] and body["conversation"]["id"] == conversation.id
    assert [m["content"] for m in body["messages"]] == ["你好", "第 1 轮回复"]
    assert body["turns"][0]["status"] == "succeeded"
    assert body["turns"][0]["judgments"]
    assert record.size_bytes == (await asyncio.to_thread(path.stat)).st_size
    second = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(request_id="two", expected_turns=1, text="继续", model_id="fixture-model"),
    )
    await wait(agent, second.id)
    assert (await conversations.export_history(USER, conversation.id)).path == record.path
    assert len(json.loads(await asyncio.to_thread(path.read_text))["messages"]) == 4
    assert calls == 2, "Export must not replay model requests"
    with pytest.raises(ApplicationError) as denied:
        await conversations.export_history(Principal(owner="other", role="user"), conversation.id)
    assert denied.value.status == 404
    with pytest.raises(ApplicationError) as runtime:
        await conversations.export_history(
            USER.model_copy(update={"role": "runtime"}), conversation.id
        )
    assert runtime.value.status == 403
    # Replacing the export filename cannot redirect a write outside the private directory.
    victim = path.parent.parent / "untouched.txt"
    await asyncio.to_thread(victim.write_text, "untouched")
    await asyncio.to_thread(path.unlink)
    await asyncio.to_thread(path.symlink_to, victim)
    await conversations.export_history(USER, conversation.id)
    assert (await asyncio.to_thread(victim.read_text)) == "untouched" and not (
        await asyncio.to_thread(path.is_symlink)
    )


async def test_history_export_includes_blocking_reason_before_any_assistant_reply(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def blocked(request: ModelRequest) -> ModelResult:
        raise ApplicationError(503, "fixture_blocked", "Temporary model failure")

    generate(agent, monkeypatch, blocked)
    conversations = service(agent)
    conversation = await conversations.create(
        USER, ConversationCreate(request_id="blocked-history", title="分析阻塞原因")
    )
    run = await conversations.send(
        USER,
        conversation.id,
        ConversationTurn(
            request_id="blocked-turn",
            expected_turns=0,
            text="分析项目",
            model_id="fixture-model",
        ),
    )
    done = await wait(agent, run.id)
    assert done.status == "blocked"
    record = await conversations.export_history(USER, conversation.id)
    body = json.loads(await asyncio.to_thread(Path(record.path).read_text))
    assert body["turns"][0]["reason"] == done.reason
    assert body["messages"][1]["status"] == "blocked"
    assert body["messages"][1]["content"] == ""
