import asyncio
import hashlib
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError
from test_context import USER, publish
from test_context import context as context

from auton.agent.contracts import AgentConfig, AgentRun, CreateRun, RunCommand
from auton.agent.factory import AgentRuntimeFactory
from auton.agent.service import AgentDependencies, AgentRuntime
from auton.constitution.config import Principal
from auton.constitution.ports import ExecutionControlPort
from auton.context.service import ContextEngine
from auton.judgment.config import JudgmentConfig
from auton.judgment.factory import JudgmentFactory
from auton.judgment.service import JudgmentDependencies
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult, ModelUsage, ToolCall
from auton.model.ports import ModelError


@pytest.fixture
async def agent(context: ContextEngine, tmp_path: Path) -> AsyncIterator[AgentRuntime]:
    await context.deps.tools.create_workspace(USER, "workspace", "Workspace", False)
    judgment = JudgmentFactory().create(
        JudgmentConfig(backend="mock"),
        JudgmentDependencies(
            cast(ExecutionControlPort, context.deps.policy),
            context.deps.policy,
            context.deps.events,
            context.deps.runtime,
            context.deps.models,
        ),
    )
    await judgment.start()
    service = AgentRuntimeFactory().create(
        AgentConfig(directory=str(tmp_path / "agent")),
        AgentDependencies(
            context,
            context.deps.models,
            context.deps.tools,
            judgment,
            context.deps.assets,
            context.deps.events,
            context.deps.runtime,
        ),
    )
    assert isinstance(service, AgentRuntime)
    await service.start()
    yield service
    await service.close()
    await judgment.close()


def create(**changes: object) -> CreateRun:
    return CreateRun.model_validate(
        {
            "request_id": "run-1",
            "project_id": "project",
            "workspace_id": "workspace",
            "model_id": "fixture-model",
            "goal": "Research context retrieval and cite [asset:notes].",
            "acceptance": {"kind": "research"},
            **changes,
        }
    )


def result(request: ModelRequest, text: str = "", calls: tuple[ToolCall, ...] = ()) -> ModelResult:
    return ModelResult(
        request_id=request.request_id,
        model_id=request.model_id,
        reported_model="fixture-v1",
        content=text,
        tool_calls=calls,
        finish_reason="tool_calls" if calls else "stop",
        usage=ModelUsage(input_tokens=10, output_tokens=5),
        source="test",
        latency_ms=0,
    )


def generate(
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
    callback: Callable[[ModelRequest], Awaitable[ModelResult]],
) -> None:
    monkeypatch.setattr(agent.deps.models, "generate", callback)


async def wait(agent: AgentRuntime, identity: str, statuses: set[str] | None = None) -> AgentRun:
    wanted = statuses or {
        "succeeded",
        "failed",
        "blocked",
        "waiting_approval",
        "paused",
        "cancelled",
    }
    async with asyncio.timeout(15):
        while True:
            run = await agent.get(USER, identity)
            if run.status in wanted:
                return run
            await asyncio.sleep(0.01)


async def command(agent: AgentRuntime, run: AgentRun, action: str, **changes: object) -> AgentRun:
    return await agent.command(
        USER,
        run.id,
        RunCommand.model_validate(
            {
                "request_id": f"{action}-{run.version}",
                "expected_goal_revision": run.goal_revision,
                "action": action,
                **changes,
            }
        ),
    )


async def test_readonly_research_and_independent_citation_acceptance(
    agent: AgentRuntime, context: ContextEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await publish(context, "notes", "Context retrieval keeps provenance and isolates project data.")

    async def answer(req: ModelRequest) -> ModelResult:
        assert req.tools and all(t.name not in {"file_write", "process_run"} for t in req.tools)
        return result(
            req,
            (
                "This report compares context retrieval and project isolation. "
                "The source states that provenance should remain attached "
                "to retrieved evidence. [asset:notes]"
            ),
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(USER, create())
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert done.check and not done.check.semantic_quality_verified
    assert done.context_ids and done.judgment_ids and done.tokens_used == 15
    name, data = await agent.report(USER, done.id)
    assert name.endswith(".md") and b"[asset:notes]" in data
    assert (await agent.list(USER, "project"))[0].id == run.id
    assert (await agent.create(USER, create())).id == run.id
    with pytest.raises(ApplicationError):
        await agent.create(USER, create(goal="different"))
    with pytest.raises(ApplicationError):
        await agent.get(Principal(owner="other", role="user"), run.id)


async def test_real_file_approval_receipt_and_digest_acceptance(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def answer(req: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return result(
                req,
                calls=(
                    ToolCall(
                        id="write1",
                        name="file_write",
                        arguments={"path": "notes.md", "content": "hello\n"},
                    ),
                ),
            )
        assert req.messages[-1].role == "tool"
        return result(
            req, "The requested file was written. The host must independently verify its digest."
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(
        USER,
        create(
            goal="Write hello newline to notes.md",
            allowed_tools=["file.write"],
            acceptance={
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
        ),
    )
    waiting = await wait(agent, run.id)
    assert waiting.status == "waiting_approval", waiting.reason
    assert calls == 1 and not waiting.receipts
    await command(agent, waiting, "approve")
    done = await wait(agent, run.id)
    assert done.status == "succeeded", done.reason
    assert calls == 2 and len(done.receipts) == 1 and done.check and done.check.outcome == "passed"
    _, data = await agent.deps.tools.artifact(
        USER.model_copy(update={"role": "runtime"}), done.receipts[0].operation_id
    )
    assert data == b"hello\n"


@pytest.mark.parametrize("action", ["cancel", "revise", "pause"])
async def test_inflight_model_cannot_dispatch_after_control_change(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def answer(req: ModelRequest) -> ModelResult:
        entered.set()
        await release.wait()
        return result(
            req, calls=(ToolCall(id="late", name="mcp_sha256", arguments={"text": "late"}),)
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)
    before = await agent.get(USER, run.id)
    requested = await command(
        agent, before, action, **({"goal": "NEW REVISION"} if action == "revise" else {})
    )
    assert requested.status in {"cancelling", "pausing"}
    release.set()
    done = await wait(agent, run.id)
    assert done.status == ("cancelled" if action == "cancel" else "paused"), done.reason
    assert not done.receipts and not done.pending_calls and done.model_results
    if action == "revise":
        assert done.goal_revision == 2 and done.command.goal == "NEW REVISION"
        assert all(m.content != "late" for m in done.history)
        with pytest.raises(ApplicationError) as error:
            await agent.command(
                USER,
                run.id,
                RunCommand(request_id="stale", expected_goal_revision=1, action="resume"),
            )
        assert error.value.code == "agent_stale_revision"


async def test_unknown_tool_requires_reconciliation_before_resume(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = agent.deps.tools.execute

    async def uncertain(
        principal: Principal, identity: str, approval_id: str | None = None
    ) -> object:
        receipt = await original(principal, identity, approval_id)
        return receipt.model_copy(update={"outcome": "unknown", "code": "ack_lost"})

    monkeypatch.setattr(agent.deps.tools, "execute", uncertain)

    async def answer(req: ModelRequest) -> ModelResult:
        return result(
            req, calls=(ToolCall(id="hash", name="mcp_sha256", arguments={"text": "hello"}),)
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(USER, create())
    done = await wait(agent, run.id)
    assert done.reason == "tool_outcome_unknown", done.reason
    with pytest.raises(ApplicationError) as error:
        await command(agent, done, "resume")
    assert error.value.code == "agent_reconcile_required"
    reconciled = await command(agent, done, "reconcile")
    assert reconciled.receipts[0].outcome == "succeeded"
    await command(agent, reconciled, "cancel")


async def test_loop_and_model_disconnect_do_not_succeed(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def repeated(req: ModelRequest) -> ModelResult:
        return result(
            req, calls=(ToolCall(id="hash", name="mcp_sha256", arguments={"text": "repeat"}),)
        )

    generate(agent, monkeypatch, repeated)
    run = await agent.create(USER, create())
    done = await wait(agent, run.id)
    assert done.reason == "repeated_tool_loop" and len(done.receipts) == 2

    async def interrupted(req: ModelRequest) -> ModelResult:
        raise ModelError("stream_interrupted", "connection lost", dispatched=True)

    generate(agent, monkeypatch, interrupted)
    second = await agent.create(USER, create(request_id="disconnected"))
    blocked = await wait(agent, second.id)
    assert blocked.status == "blocked" and blocked.reason == "stream_interrupted"
    assert blocked.model_request_id and not blocked.final_text


async def test_model_claim_alone_never_passes_acceptance(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def invented(req: ModelRequest) -> ModelResult:
        return result(
            req,
            "Success! I have researched all sources and verified every claim. " * 3
            + "[asset:invented]",
        )

    generate(agent, monkeypatch, invented)
    run = await agent.create(USER, create())
    failed = await wait(agent, run.id)
    assert failed.status == "failed" and failed.check and failed.check.outcome == "failed"


async def test_configuration_role_and_single_writer_lease(agent: AgentRuntime) -> None:
    with pytest.raises(ValidationError):
        create(allowed_tools=["file.write"])
    with pytest.raises(ApplicationError):
        await agent.create(USER.model_copy(update={"role": "evolution"}), create())
    other = AgentRuntimeFactory().create(agent.config, agent.deps)
    with pytest.raises(ApplicationError) as error:
        await other.start()
    assert error.value.code == "agent_runtime_owned"


async def test_inflight_write_is_recorded_before_stop_confirmation(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    execute = agent.deps.tools.execute
    model_calls = 0

    async def delayed(
        principal: Principal, identity: str, approval_id: str | None = None
    ) -> object:
        entered.set()
        await release.wait()
        return await execute(principal, identity, approval_id)

    monkeypatch.setattr(agent.deps.tools, "execute", delayed)

    async def answer(req: ModelRequest) -> ModelResult:
        nonlocal model_calls
        model_calls += 1
        return result(
            req,
            calls=(
                ToolCall(
                    id="write",
                    name="file_write",
                    arguments={"path": "notes.md", "content": "hello\n"},
                ),
            ),
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(
        USER,
        create(
            allowed_tools=["file.write"],
            acceptance={
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
        ),
    )
    waiting = await wait(agent, run.id)
    await command(agent, waiting, "approve")
    await asyncio.wait_for(entered.wait(), 10)
    stopping = await command(agent, await agent.get(USER, run.id), "cancel")
    assert stopping.status == "cancelling"
    release.set()
    done = await wait(agent, run.id)
    assert done.status == "cancelled" and model_calls == 1
    assert done.receipts[0].outcome == "succeeded" and done.receipts[0].artifact


async def test_paused_safe_checkpoint_survives_runtime_recreation(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def answer(req: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return result(req, "No source is available; the host should fail citation acceptance.")

    generate(agent, monkeypatch, answer)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)
    await command(agent, await agent.get(USER, run.id), "pause")
    release.set()
    paused = await wait(agent, run.id)
    assert paused.status == "paused" and paused.model_request_id is None
    await agent.close()
    rebuilt = AgentRuntimeFactory().create(agent.config, agent.deps)
    await rebuilt.start()
    try:
        assert (await rebuilt.get(USER, run.id)).version == paused.version
        resumed = await rebuilt.command(
            USER,
            run.id,
            RunCommand(
                request_id="resume-after-restart", expected_goal_revision=1, action="resume"
            ),
        )
        assert resumed.status == "queued"
        assert isinstance(rebuilt, AgentRuntime)
        await wait(rebuilt, run.id, {"failed", "blocked"})
        assert calls == 2
    finally:
        await rebuilt.close()


async def test_run_budget_blocks_before_call_and_command_retries_are_idempotent(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent.config = agent.config.model_copy(update={"max_tokens": 512})

    async def forbidden(req: ModelRequest) -> ModelResult:
        raise AssertionError("Budget failure must happen before the gateway call")

    generate(agent, monkeypatch, forbidden)
    run = await agent.create(USER, create())
    blocked = await wait(agent, run.id)
    assert blocked.reason == "run_budget_limit" and blocked.steps == 0
    cmd = RunCommand(request_id="stable-cancel", expected_goal_revision=1, action="cancel")
    first = await agent.command(USER, run.id, cmd)
    again = await agent.command(USER, run.id, cmd)
    assert first.version == again.version and again.status == "cancelled"
    with pytest.raises(ApplicationError) as error:
        await agent.command(USER, run.id, cmd.model_copy(update={"action": "pause"}))
    assert error.value.code == "agent_command_conflict"


async def test_expired_approval_returns_to_exact_operation_review(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = agent.deps.tools.execute
    attempts = 0

    async def expired(
        principal: Principal, identity: str, approval_id: str | None = None
    ) -> object:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ApplicationError(403, "approval_required", "Approval expired before dispatch")
        return await original(principal, identity, approval_id)

    monkeypatch.setattr(agent.deps.tools, "execute", expired)
    calls = 0

    async def answer(req: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        return (
            result(
                req,
                calls=(
                    ToolCall(
                        id="write",
                        name="file_write",
                        arguments={"path": "notes.md", "content": "hello\n"},
                    ),
                ),
            )
            if calls == 1
            else result(req, "Done, subject to host digest verification.")
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(
        USER,
        create(
            allowed_tools=["file.write"],
            acceptance={
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
        ),
    )
    first = await wait(agent, run.id)
    await command(agent, first, "approve")
    second = await wait(agent, run.id)
    assert second.status == "waiting_approval" and second.reason == "approval_expired_or_revoked"
    assert not second.receipts and not second.approvals
    await command(agent, second, "approve")
    assert (await wait(agent, run.id)).status == "succeeded"


async def test_not_dispatched_tool_is_proven_before_cancellation(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(
        principal: Principal, identity: str, approval_id: str | None = None
    ) -> object:
        raise ApplicationError(403, "budget_exceeded", "No tool budget")

    monkeypatch.setattr(agent.deps.tools, "execute", unavailable)

    async def answer(req: ModelRequest) -> ModelResult:
        return result(
            req, calls=(ToolCall(id="hash", name="mcp_sha256", arguments={"text": "hello"}),)
        )

    generate(agent, monkeypatch, answer)
    run = await agent.create(USER, create())
    blocked = await wait(agent, run.id)
    assert blocked.reason == "budget_exceeded" and not blocked.receipts
    requested = await command(agent, blocked, "cancel")
    assert requested.status == "blocked" and requested.stop_requested
    confirmed = await command(agent, requested, "reconcile")
    assert confirmed.status == "cancelled" and confirmed.reason == "operation_proven_not_dispatched"


def test_agent_http_commands_are_owned_and_do_not_accept_forged_roles(client: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)
    client.post(
        "/api/v1/projects", json={"id": "http-agent", "title": "HTTP agent"}
    ).raise_for_status()
    client.post(
        "/api/v1/tools/workspaces",
        json={"id": "http-agent", "title": "HTTP files", "read_only": True},
    ).raise_for_status()
    body = create(project_id="http-agent", workspace_id="http-agent").model_dump(mode="json")
    first = client.post("/api/v1/agent/runs", json=body)
    assert first.status_code == 200, first.text
    identity = first.json()["id"]
    assert client.post("/api/v1/agent/runs", json=body).json()["id"] == identity
    assert client.get("/api/v1/agent/runs?project_id=http-agent").json()[0]["id"] == identity
    assert (
        client.post("/api/v1/agent/runs", json={**body, "principal": {"role": "admin"}}).status_code
        == 422
    )
    client.cookies.clear()
    client.get("/api/v1/bootstrap")
    assert client.get("/api/v1/agent/runs/" + identity).status_code == 404
