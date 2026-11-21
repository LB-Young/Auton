import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_agent import agent as agent
from test_agent import create, generate, result, wait
from test_assessment import assessment as assessment
from test_context import USER
from test_context import context as context

from auton.agent.contracts import Acceptance, AgentConfig, AgentRun, RunLimits
from auton.agent.service import AgentRuntime
from auton.assess.service import Assessment
from auton.delegation.contracts import (
    ChildSpec,
    DelegationCommand,
    DelegationConfig,
    DelegationCreate,
    DelegationView,
)
from auton.delegation.factory import DelegationFactory
from auton.delegation.service import Delegation, DelegationDependencies
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult, ToolCall


def plan(**changes: object) -> DelegationCreate:
    child_limits = RunLimits(max_steps=3, max_tokens=8000, max_cost_microusd=4000, max_tool_calls=1)
    return DelegationCreate.model_validate(
        {
            "request_id": "supervisor-test",
            "project_id": "project",
            "workspace_id": "workspace",
            "goal": "Write two verified fragments as one delivery.",
            "limits": AgentConfig().model_dump(include=set(RunLimits.model_fields)),
            "children": [
                ChildSpec(
                    id=key,
                    role="worker",
                    goal="Write hello then a newline to notes.md.",
                    model_id="fixture-model",
                    limits=child_limits,
                    allowed_tools=("file.write",),
                    acceptance=Acceptance(
                        kind="file", path="notes.md", sha256=hashlib.sha256(b"hello\n").hexdigest()
                    ),
                ).model_dump(mode="json")
                for key in ("alpha", "beta")
            ],
            "merge_order": ["alpha", "beta"],
            "acceptance": {
                "kind": "file",
                "path": "delivery.md",
                "sha256": hashlib.sha256(b"hello\nhello\n").hexdigest(),
            },
            **changes,
        }
    )


@pytest.fixture
async def supervisor(
    assessment: Assessment, agent: AgentRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Delegation]:
    async def model(request: ModelRequest) -> ModelResult:
        if any(m.role == "tool" for m in request.messages):
            return result(request, "The file write finished.")
        return result(
            request,
            calls=(
                ToolCall(
                    id="write",
                    name="file_write",
                    arguments={"path": "notes.md", "content": "hello\n"},
                ),
            ),
        )

    generate(agent, monkeypatch, model)
    deps = DelegationDependencies(
        agent,
        agent.deps.tools,
        assessment,
        agent.deps.assets,
        agent.deps.runtime,
        RunLimits.model_validate(agent.config.model_dump(include=set(RunLimits.model_fields))),
        agent.deps.models,
        True,
    )
    service = DelegationFactory().create(
        DelegationConfig(directory=tmp_path / "delegation"), deps, agent.deps.events
    )
    assert isinstance(service, Delegation)
    await service.start()
    yield service
    await service.close()


async def control(
    service: Delegation, value: DelegationView, action: str, child: str | None = None
) -> DelegationView:
    return await service.command(
        USER,
        value.id,
        DelegationCommand.model_validate(
            {
                "request_id": action + "-" + str(value.version) + ("-" + child if child else ""),
                "expected_version": value.version,
                "action": action,
                "child_id": child,
            }
        ),
    )


async def await_parent(service: Delegation, parent: str, target: str) -> DelegationView:
    async with asyncio.timeout(20):
        while True:
            value = await service.get(USER, parent)
            if value.status == target:
                return value
            if value.status == "blocked":
                raise AssertionError(value.reason)
            await asyncio.sleep(0.02)


async def approve_workers(service: Delegation, parent: str) -> DelegationView:
    async with asyncio.timeout(20):
        while True:
            value = await service.get(USER, parent)
            if value.status == "waiting_approval":
                return value
            if value.status == "blocked":
                raise AssertionError(value.reason)
            pending = next((c for c in value.children if c.status == "waiting_approval"), None)
            if pending:
                try:
                    await control(service, value, "approve_child", pending.id)
                except ApplicationError as error:
                    if error.code != "delegation_version_changed":
                        raise
            await asyncio.sleep(0.02)


async def test_parallel_private_workers_need_separate_merge_approval_and_parent_check(
    supervisor: Delegation, agent: AgentRuntime
) -> None:
    root = await supervisor.create(USER, plan())
    assert (await supervisor.create(USER, plan())).id == root.id
    with pytest.raises(ApplicationError):
        await supervisor.create(USER, plan(goal="Different parent revision under same id"))
    await control(supervisor, root, "start")
    ready = await approve_workers(supervisor, root.id)
    assert all(c.status == "verified" and c.report_id for c in ready.children)
    assert (
        ready.integration and ready.integration.requires_approval and not ready.approved_integration
    )
    assert len({c.command.workspace_id for c in ready.children if c.command}) == 2
    assert all(
        c.command and c.command.asset_snapshot_id == root.input_snapshot_id for c in ready.children
    )
    assert (
        ready.total_tokens > 0
        and ready.total_tool_calls == 2
        and ready.benefit_claim == "not_established"
    )
    with pytest.raises(ApplicationError):
        await agent.deps.tools.artifact(USER, ready.integration.operation_id)
    await control(supervisor, ready, "approve_integration")
    done = await await_parent(supervisor, root.id, "integrated")
    assert done.integration_receipt and done.total_tool_calls == 3
    _, data = await agent.deps.tools.artifact(USER, done.integration_receipt.operation_id)
    assert data == b"hello\nhello\n" and done.attribution == "interaction-group-only"
    with pytest.raises(ApplicationError):
        await supervisor.get(USER.model_copy(update={"owner": "other"}), root.id)
    with pytest.raises(ApplicationError):
        await supervisor.command(
            USER.model_copy(update={"role": "runtime"}),
            root.id,
            DelegationCommand(
                request_id="self-approve",
                expected_version=done.version,
                action="approve_integration",
            ),
        )


async def test_dag_cycle_budget_and_parent_output_conflicts_fail_closed(
    supervisor: Delegation,
) -> None:
    command = plan()
    with pytest.raises(ValidationError, match="Cyclic"):
        plan(
            children=[
                {**c.model_dump(), "depends_on": ["beta" if c.id == "alpha" else "alpha"]}
                for c in command.children
            ]
        )
    with pytest.raises(ValidationError, match="budget"):
        plan(limits=command.limits.model_copy(update={"max_tokens": 1000}))
    with pytest.raises(ValidationError, match="relative"):
        plan(acceptance=command.acceptance.model_copy(update={"path": "../outside"}))
    with pytest.raises(ValidationError, match="relative"):
        plan(acceptance=command.acceptance.model_copy(update={"path": "folder//delivery.md"}))
    root = await supervisor.create(USER, command)
    with pytest.raises(ApplicationError) as conflict:
        await supervisor.create(USER, plan(request_id="competing-supervisor"))
    assert conflict.value.code == "delegation_write_conflict"
    with pytest.raises(ApplicationError) as alias:
        await supervisor.create(
            USER,
            plan(
                request_id="same-output-alias",
                acceptance=command.acceptance.model_copy(update={"path": "DELIVERY.md"}),
            ),
        )
    assert alias.value.code == "delegation_write_conflict"
    await control(supervisor, root, "cancel")
    await await_parent(supervisor, root.id, "cancelled")
    assert (await supervisor.create(USER, plan(request_id="after-cancellation"))).id != root.id


async def test_parent_cancel_stops_new_dependencies_and_child_effects(
    supervisor: Delegation,
) -> None:
    original = plan()
    dependent = original.children[1].model_copy(update={"depends_on": ("alpha",)})
    root = await supervisor.create(
        USER, original.model_copy(update={"children": (original.children[0], dependent)})
    )
    await control(supervisor, root, "start")
    async with asyncio.timeout(10):
        while True:
            value = await supervisor.get(USER, root.id)
            if value.children[0].status == "waiting_approval":
                break
            await asyncio.sleep(0.02)
    assert value.children[1].run_id is None
    await control(supervisor, value, "cancel")
    cancelled = await await_parent(supervisor, root.id, "cancelled")
    assert cancelled.children[1].run_id is None and not cancelled.approved_integration
    assert cancelled.children[0].status == "cancelled"


async def test_children_success_does_not_override_parent_acceptance(supervisor: Delegation) -> None:
    command = plan()
    root = await supervisor.create(
        USER,
        command.model_copy(
            update={"acceptance": command.acceptance.model_copy(update={"sha256": "0" * 64})}
        ),
    )
    await control(supervisor, root, "start")
    with pytest.raises(AssertionError, match="integration_parent_acceptance_failed"):
        await approve_workers(supervisor, root.id)
    value = await supervisor.get(USER, root.id)
    assert value.status == "blocked" and value.integration_receipt is None


async def test_per_run_limits_pin_budget_and_keep_legacy_request_digest(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    command = create()
    old_payload = json.dumps(
        command.model_dump(
            mode="json", exclude={"limits", "asset_snapshot_id", "prior_messages", "prior_runs"}
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    assert command.digest == hashlib.sha256(old_payload.encode()).hexdigest()
    # Frozen pre-conversation digest: an empty new field must not invalidate old retries.
    assert command.digest == "d6cefb175ecc4771a014fd327f64ad973c28a0e253ab537fc344fa54bd801c0c"
    with pytest.raises(ApplicationError) as denied:
        await agent.create(
            USER,
            create(
                request_id="oversized-budget",
                limits=RunLimits(
                    max_steps=9, max_tokens=4000, max_cost_microusd=4000, max_tool_calls=1
                ),
            ),
        )
    assert denied.value.code == "run_limit_escalation"

    async def model(req: ModelRequest) -> ModelResult:
        return result(req, "Unverified answer")

    generate(agent, monkeypatch, model)
    limits = RunLimits(
        max_steps=1, max_tokens=512, max_cost_microusd=1, max_tool_calls=1, max_output_tokens=32
    )
    created = await agent.create(USER, create(request_id="tight-budget", limits=limits))
    done: AgentRun = await wait(agent, created.id)
    assert done.status == "blocked" and done.reason == "run_budget_limit"
    assert not done.model_results and done.budget_limits == limits.model_dump()
    assert (await agent.find_creation(USER, created.command)).id == done.id  # type: ignore[union-attr]


async def test_dependency_handoff_is_pinned_and_launches_only_after_verification(
    supervisor: Delegation,
) -> None:
    original = plan()
    dependent = original.children[1].model_copy(update={"depends_on": ("alpha",)})
    root = await supervisor.create(
        USER, original.model_copy(update={"children": (original.children[0], dependent)})
    )
    await control(supervisor, root, "start")
    ready = await approve_workers(supervisor, root.id)
    second = ready.children[1]
    assert second.command and "Untrusted dependency data" in second.command.goal
    assert '"alpha": "hello\\n"' in second.command.goal
    assert second.command.asset_snapshot_id == root.input_snapshot_id


async def test_lost_child_create_ack_is_found_before_parent_cancel(
    supervisor: Delegation, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_create = agent.create
    calls = 0

    async def lost(principal: object, command: object) -> AgentRun:
        nonlocal calls
        calls += 1
        await real_create(principal, command)  # type: ignore[arg-type]
        raise ApplicationError(503, "synthetic_create_ack_lost", "Synthetic acknowledgement loss")

    monkeypatch.setattr(agent, "create", lost)
    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    blocked = await await_parent(supervisor, root.id, "blocked")
    assert calls == 1 and blocked.reason == "synthetic_create_ack_lost"
    assert blocked.children[0].run_id and blocked.children[0].status == "cancelled"
    assert blocked.children[1].run_id is None
    await control(supervisor, blocked, "cancel")
    await await_parent(supervisor, root.id, "cancelled")


async def test_restart_preserves_leases_and_requires_explicit_resume(
    supervisor: Delegation, agent: AgentRuntime
) -> None:
    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    async with asyncio.timeout(10):
        while True:
            value = await supervisor.get(USER, root.id)
            if all(c.status == "waiting_approval" for c in value.children):
                break
            await asyncio.sleep(0.02)
    await supervisor.close()
    restarted = DelegationFactory().create(supervisor.config, supervisor.deps, agent.deps.events)
    assert isinstance(restarted, Delegation)
    await restarted.start()
    try:
        restored = await restarted.get(USER, root.id)
        assert (
            restored.status == "blocked"
            and restored.reason == "process_interrupted_explicit_resume_required"
        )
        assert not restarted.tasks and all(
            c.status == "waiting_approval" for c in restored.children
        )
        with pytest.raises(ApplicationError) as conflict:
            await restarted.create(USER, plan(request_id="overlap-after-restart"))
        assert conflict.value.code == "delegation_write_conflict"
        await control(restarted, restored, "resume")
        ready = await approve_workers(restarted, root.id)
        await control(restarted, ready, "approve_integration")
        assert (await await_parent(restarted, root.id, "integrated")).integration_receipt
    finally:
        await restarted.close()


async def test_child_timeout_propagates_cancellation_without_integration(
    supervisor: Delegation,
) -> None:
    from dataclasses import replace
    from datetime import timedelta

    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    async with asyncio.timeout(10):
        while True:
            value = await supervisor.get(USER, root.id)
            if value.children[0].status == "waiting_approval":
                break
            await asyncio.sleep(0.02)
    now = supervisor.deps.runtime.now()
    supervisor.deps = replace(
        supervisor.deps,
        runtime=replace(supervisor.deps.runtime, now=lambda: now + timedelta(seconds=601)),
    )
    blocked = await await_parent(supervisor, root.id, "blocked")
    assert blocked.reason == "child_timeout" and blocked.integration is None
    assert all(not c.run_id or c.status == "cancelled" for c in blocked.children)


async def test_unknown_dispatched_child_usage_keeps_parent_and_lease_blocked(
    supervisor: Delegation, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.model.ports import ModelError

    async def unknown(req: ModelRequest) -> ModelResult:
        raise ModelError(
            "request_result_unknown", "Synthetic remote request uncertainty", dispatched=True
        )

    generate(agent, monkeypatch, unknown)
    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    blocked = await await_parent(supervisor, root.id, "blocked")
    assert blocked.unknown_calls > 0 and "reconciliation_required" in blocked.reason
    assert not blocked.integration_receipt
    with pytest.raises(ApplicationError) as conflict:
        await supervisor.create(USER, plan(request_id="must-not-steal-unknown-output"))
    assert conflict.value.code == "delegation_write_conflict"


async def test_single_multi_cost_contrast_requires_same_input_and_total_budget(
    supervisor: Delegation, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_agent import command as agent_command

    from auton.delegation.contracts import ContrastCommand

    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    ready = await approve_workers(supervisor, root.id)
    await control(supervisor, ready, "approve_integration")
    done = await await_parent(supervisor, root.id, "integrated")
    await agent.deps.tools.create_workspace(USER, "single-baseline", "Independent baseline", False)

    async def model(request: ModelRequest) -> ModelResult:
        if any(m.role == "tool" for m in request.messages):
            return result(request, "The complete file has been written.")
        return result(
            request,
            calls=(
                ToolCall(
                    id="write",
                    name="file_write",
                    arguments={"path": "delivery.md", "content": "hello\nhello\n"},
                ),
            ),
        )

    generate(agent, monkeypatch, model)
    baseline = await agent.create(
        USER,
        create(
            request_id="single-baseline",
            workspace_id="single-baseline",
            goal=root.command.goal,
            allowed_tools=["file.write"],
            acceptance=root.command.acceptance,
            asset_snapshot_id=root.input_snapshot_id,
            limits=root.command.limits,
        ),
    )
    paused = await wait(agent, baseline.id)
    await agent_command(agent, paused, "approve", request_id="single-baseline-approval")
    baseline = await wait(agent, baseline.id)
    assert baseline.status == "succeeded"
    compared = await supervisor.contrast(
        USER,
        done.id,
        ContrastCommand(
            request_id="same-condition-pair",
            baseline_run_id=baseline.id,
            expected_version=baseline.version,
        ),
    )
    assert compared.comparable and compared.baseline_calls == 2 and compared.worker_calls == 4
    assert not compared.improvement_established and compared.source == "test"
    assert compared.worker_tokens > compared.baseline_tokens


async def test_local_judgment_capacity_waits_without_repeating_execution(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.judgment.contracts import JudgmentRequest, JudgmentResult

    original = agent.deps.judgment.decide
    attempts: list[str] = []

    async def busy_then_ready(request: JudgmentRequest) -> JudgmentResult:
        attempts.append(request.request_id)
        if len(attempts) == 1:
            raise ApplicationError(429, "judgment_busy", "Synthetic pre-dispatch capacity refusal")
        return await original(request)

    monkeypatch.setattr(agent.deps.judgment, "decide", busy_then_ready)

    async def model(request: ModelRequest) -> ModelResult:
        return result(request, "No evidence was available.")

    generate(agent, monkeypatch, model)
    created = await agent.create(USER, create(request_id="judgment-capacity-wait"))
    done = await wait(agent, created.id)
    assert len(attempts) == 2 and len(set(attempts)) == 1
    assert len(done.judgments) == 1 and len(done.model_results) == 1
    assert done.runtime_revision == "single-agent-v3"


async def test_unknown_merge_keeps_cost_and_lease_until_explicit_cancellation_reconciles(
    supervisor: Delegation, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.constitution.config import Principal
    from auton.tools.contracts import ToolReceipt

    original = agent.deps.tools.execute

    async def uncertain(
        principal: Principal, operation_id: str, approval_id: str | None = None
    ) -> ToolReceipt:
        receipt = await original(principal, operation_id, approval_id)
        if operation_id.startswith("merge-"):
            return receipt.model_copy(
                update={"outcome": "unknown", "code": "synthetic_ack_uncertainty", "artifact": None}
            )
        return receipt

    monkeypatch.setattr(agent.deps.tools, "execute", uncertain)
    root = await supervisor.create(USER, plan())
    await control(supervisor, root, "start")
    ready = await approve_workers(supervisor, root.id)
    await control(supervisor, ready, "approve_integration")
    blocked = await await_parent(supervisor, root.id, "blocked")
    assert blocked.unknown_tools == 1 and blocked.total_tool_calls == 3
    assert blocked.integration_receipt and blocked.integration_receipt.outcome == "unknown"
    with pytest.raises(ApplicationError) as conflict:
        await supervisor.create(USER, plan(request_id="blocked-merge-lease"))
    assert conflict.value.code == "delegation_write_conflict"
    await control(supervisor, blocked, "cancel")
    settled = await await_parent(supervisor, root.id, "cancelled")
    assert settled.unknown_tools == 0 and settled.total_tool_calls == 3
    assert settled.integration_receipt and settled.integration_receipt.outcome == "succeeded"
    assert settled.reason == "user_cancelled_after_integration_committed"
