import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import apsw
import pytest
from test_agent import agent as agent
from test_agent import command, create, wait
from test_context import USER, publish
from test_context import context as context

from auton.agent.contracts import AgentRun, RunCommand, checkpoint_event_id
from auton.agent.service import AgentRuntime
from auton.constitution.config import Principal
from auton.constitution.secrets import SecretStoreFactory
from auton.experience.contracts import ExperienceConfig, RecoveryCommand
from auton.experience.factory import ExperienceFactory
from auton.experience.projection import SQLiteProjection
from auton.experience.service import ExperienceDependencies, ExperienceService
from auton.kernel.events import Event, EventScope, StoredEvent
from auton.kernel.ports import ApplicationError
from auton.model.config import ModelConfig, ModelSpec
from auton.model.contracts import ModelChunk, ModelRequest
from auton.model.factory import ProviderFactory
from auton.model.gateway import ModelGateway


@pytest.fixture
async def experience(agent: AgentRuntime, tmp_path: Path) -> AsyncIterator[ExperienceService]:
    models = agent.deps.models
    assert isinstance(models, ModelGateway)
    await models.provider.close()
    models.provider = ProviderFactory().create(
        ModelConfig(backend="mock", fixture_scenario="agent_acceptance"),
        SecretStoreFactory().create(),
    )
    await models.provider.start()
    service = ExperienceFactory().create(
        ExperienceConfig(directory=tmp_path / "experience"),
        ExperienceDependencies(
            agent.deps.events, agent, agent.deps.assets, agent.deps.context, agent.deps.runtime
        ),
    )
    assert isinstance(service, ExperienceService)
    await service.start()
    yield service
    await service.close()


async def finished(agent: AgentRuntime) -> AgentRun:
    from auton.context.service import ContextEngine

    assert isinstance(agent.deps.context, ContextEngine)
    await publish(
        agent.deps.context,
        "notes",
        "Context retrieval preserves provenance and project boundaries.",
    )
    run = await agent.create(USER, create())
    result = await wait(agent, run.id)
    assert result.status == "succeeded", result.reason
    return result


async def paused(agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch) -> AgentRun:
    gateway = agent.deps.models
    assert isinstance(gateway, ModelGateway)
    entered, release = asyncio.Event(), asyncio.Event()
    original = gateway.provider.stream
    first = True

    async def gated(request: ModelRequest, spec: ModelSpec) -> AsyncGenerator[ModelChunk, None]:
        nonlocal first
        if first:
            first = False
            entered.set()
            await release.wait()
        async for item in original(request, spec):
            yield item

    monkeypatch.setattr(gateway.provider, "stream", gated)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)
    await command(agent, await agent.get(USER, run.id), "pause")
    release.set()
    result = await wait(agent, run.id)
    assert result.status == "paused", result.reason
    return result


async def test_projection_rebuild_preserves_trace_authorization_and_privacy(
    experience: ExperienceService, agent: AgentRuntime
) -> None:
    run = await finished(agent)
    before = await experience.trajectory(USER, "project", run.id)
    assert before.caught_up and not before.missing_references
    assert any(n.kind == "model.completed" for n in before.nodes)
    assert any(e.relation == "authorization" for e in before.edges)
    assert USER.owner not in before.model_dump_json()
    assert before.tokens_used == run.tokens_used and before.usage_complete
    assert len(before.episodes) == 1 and before.episodes[0].observed_tokens == run.tokens_used
    assert before.checkpoint_state["asset_versions"]
    await experience.rebuild(USER)
    after = await experience.trajectory(USER, "project", run.id)
    assert [(n.id, n.cursor, n.details) for n in before.nodes] == [
        (n.id, n.cursor, n.details) for n in after.nodes
    ]
    assert before.edges == after.edges and before.checkpoint == after.checkpoint
    with pytest.raises(ApplicationError):
        await experience.trajectory(Principal(owner="other", role="user"), "project", run.id)
    with pytest.raises(ApplicationError):
        await experience.trajectory(USER, "project", run.id, "training")
    with pytest.raises(ApplicationError):
        await experience.trajectory(
            USER.model_copy(update={"role": "evolution"}), "project", run.id
        )


async def test_safe_recovery_is_idempotent_and_bound_to_checkpoint(
    experience: ExperienceService, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await paused(agent, monkeypatch)
    view = await experience.trajectory(USER, "project", run.id, "recovery")
    assert view.recovery_available, view.recovery_reasons
    assert view.checkpoint
    request = RecoveryCommand(
        request_id="recover",
        expected_version=run.version,
        expected_goal_revision=1,
        checkpoint_event_id=view.checkpoint.event_id,
    )
    accepted = await experience.recover(USER, "project", run.id, request)
    again = await experience.recover(USER, "project", run.id, request)
    assert accepted.id == again.id and again.version >= accepted.version
    with pytest.raises(ApplicationError) as error:
        await experience.recover(
            USER, "project", run.id, request.model_copy(update={"checkpoint_event_id": "different"})
        )
    assert error.value.code == "recovery_request_conflict"
    await wait(agent, run.id)


async def test_stale_recovery_and_concurrent_state_change_are_rejected(
    experience: ExperienceService, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await paused(agent, monkeypatch)
    view = await experience.trajectory(USER, "project", run.id, "recovery")
    assert view.checkpoint
    request = RecoveryCommand(
        request_id="racy-recover",
        expected_version=run.version,
        expected_goal_revision=1,
        checkpoint_event_id=view.checkpoint.event_id,
    )
    original = agent.command

    async def race(principal: Principal, identity: str, action: RunCommand) -> AgentRun:
        await original(
            principal,
            identity,
            RunCommand(request_id="interleaved-pause", action="pause", expected_goal_revision=1),
        )
        return await original(principal, identity, action)

    monkeypatch.setattr(agent, "command", race)
    with pytest.raises(ApplicationError) as error:
        await experience.recover(USER, "project", run.id, request)
    assert error.value.code == "agent_checkpoint_changed"
    assert (await agent.get(USER, run.id)).status == "paused"


async def test_missing_snapshot_blocks_recovery_without_dispatch(
    experience: ExperienceService, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = await paused(agent, monkeypatch)

    async def missing(principal: Principal, project: str, identity: str) -> object:
        raise ApplicationError(404, "context_not_found", "Missing retained snapshot")

    monkeypatch.setattr(experience.deps.context, "snapshot", missing)
    view = await experience.trajectory(USER, "project", run.id, "recovery")
    assert not view.recovery_available and view.missing_references
    assert "source_evidence_missing_or_unavailable" in view.recovery_reasons
    assert (await agent.get(USER, run.id)).version == run.version


async def test_unknown_checkpoint_version_is_visible_and_never_resumed(
    experience: ExperienceService, agent: AgentRuntime
) -> None:
    run = await finished(agent)
    version = run.version + 1
    event = Event(
        event_id=checkpoint_event_id(USER.owner, run.id, version),
        kind="agent.checkpoint",
        timestamp=agent.deps.runtime.now(),
        scope=EventScope.model_validate({"project_id": "project", "run_id": run.id}),
        source="test",
        payload={
            "run": {
                **run.model_dump(mode="json"),
                "version": version,
                "runtime_revision": "future-v99",
            }
        },
    )
    await agent.deps.events.append([event])
    view = await experience.trajectory(USER, "project", run.id)
    assert not view.recovery_available and "checkpoint_schema_incompatible" in view.recovery_reasons


async def test_bounded_projection_reports_lag_then_catches_up(
    experience: ExperienceService, agent: AgentRuntime
) -> None:
    run = await finished(agent)
    await agent.deps.events.append(
        [
            Event(
                event_id=f"filler-{i}",
                kind="test.filler",
                timestamp=agent.deps.runtime.now(),
                source="test",
            )
            for i in range(200)
        ]
    )
    experience.config = experience.config.model_copy(update={"max_catchup_events": 100})
    lagging = await experience.trajectory(USER, "project", run.id)
    assert not lagging.caught_up and "projection_behind" in lagging.recovery_reasons
    for _ in range(4):
        await experience.catch_up()
    assert (await experience.trajectory(USER, "project", run.id)).caught_up


async def test_consumer_batch_rollback_duplicate_replay_and_schema_migration(
    tmp_path: Path,
) -> None:
    store = SQLiteProjection(tmp_path / "cache")
    await store.start()
    from datetime import UTC, datetime

    def event(identity: str) -> Event:
        return Event(
            event_id=identity, kind="test.index", timestamp=datetime.now(UTC), source="test"
        )

    first = StoredEvent(cursor=1, event=event("first"))
    try:
        with pytest.raises(apsw.ConstraintError):
            await store.apply([first, StoredEvent(cursor=2, event=first.event)], "processed")
        assert await store.position() == 0
        await store.apply([first], "first-processing")
        await store.apply([first], "duplicate-processing")
        assert await store.position() == 1
        with pytest.raises(ApplicationError):
            await store.apply([StoredEvent(cursor=1, event=event("changed"))], "bad")
    finally:
        await store.close()

    def downgrade() -> None:
        db = apsw.Connection(str(tmp_path / "cache/projections.sqlite3"))
        db.pragma("user_version", 1)
        db.close()

    await asyncio.to_thread(downgrade)
    migrated = SQLiteProjection(tmp_path / "cache")
    await migrated.start()
    try:
        assert await migrated.position() == 0
    finally:
        await migrated.close()


@pytest.mark.parametrize("preparation", ["prepare", "crash"])
async def test_real_process_restart_recovers_without_repeating_confirmed_write(
    tmp_path: Path,
    preparation: str,
) -> None:
    import sys

    script = Path(__file__).parent / "helpers/recovery_process.py"
    for phase in (preparation, "resume"):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            str(tmp_path),
            phase,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        async with asyncio.timeout(40):
            output, error = await process.communicate()
        assert process.returncode == 0, error.decode()
        if phase == "resume":
            assert b'"tool_dispatches": 1' in output


async def test_late_old_revision_event_stays_in_its_original_episode(
    experience: ExperienceService, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    run = await paused(agent, monkeypatch)
    revised = await command(agent, run, "revise", goal="Revised context research goal")
    assert revised.goal_revision == 2
    event = Event(
        event_id="late-old-revision",
        kind="model.received",
        timestamp=agent.deps.runtime.now() - timedelta(hours=1),
        scope=EventScope.model_validate(
            {"goal_id": "agent-goal-" + run.id, "goal_revision": 1, "operation_id": "late-fixture"}
        ),
        source="test",
        payload={
            "result": {
                "request_id": "late-fixture",
                "usage": {"input_tokens": 0, "output_tokens": 0, "estimated_cost_microusd": 0},
            }
        },
    )
    await agent.deps.events.append([event])
    view = await experience.trajectory(USER, "project", run.id)
    late = next(node for node in view.nodes if node.id == event.event_id)
    assert late.late_revision_result and late.event_time != late.processed_at
    old = next(e for e in view.episodes if e.goal_revision == 1)
    current = next(e for e in view.episodes if e.goal_revision == 2)
    assert "late-fixture" in old.model_request_ids and not current.model_request_ids


async def test_projection_index_is_not_authority_for_cross_run_events(
    experience: ExperienceService, agent: AgentRuntime
) -> None:
    run = await finished(agent)
    event = Event(
        event_id="foreign-index-fact",
        kind="model.started",
        timestamp=agent.deps.runtime.now(),
        scope=EventScope.model_validate({"goal_id": "another-private-run"}),
        source="test",
        payload={"model_spec": {"id": "private-other-model"}},
    )
    await agent.deps.events.append([event])
    await experience.catch_up()
    store = experience.projection
    assert isinstance(store, SQLiteProjection)
    await store._call(
        lambda: store._connection().execute(
            "UPDATE events SET run_id=? WHERE event_id=?", (run.id, event.event_id)
        )
    )
    view = await experience.trajectory(USER, "project", run.id)
    assert "private-other-model" not in view.model_dump_json()
    assert any("projection_scope_mismatch" in reference for reference in view.missing_references)


def test_trajectory_http_owner_and_purpose_are_enforced(client: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)
    client.post(
        "/api/v1/projects", json={"id": "trajectory-project", "title": "Trajectory"}
    ).raise_for_status()
    client.post(
        "/api/v1/tools/workspaces",
        json={"id": "trajectory-work", "title": "Trace files", "read_only": True},
    ).raise_for_status()
    run = client.post(
        "/api/v1/agent/runs",
        json=create(project_id="trajectory-project", workspace_id="trajectory-work").model_dump(
            mode="json"
        ),
    ).json()
    path = f"/api/v1/projects/trajectory-project/runs/{run['id']}/trajectory"
    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.json()["purpose"] == "inspect"
    assert client.get(path + "?purpose=training").status_code == 422
    client.cookies.clear()
    client.get("/api/v1/bootstrap")
    assert client.get(path).status_code in {403, 404}


async def test_old_revision_tool_plans_remain_in_the_trajectory_after_revision(
    experience: ExperienceService, agent: AgentRuntime
) -> None:
    import hashlib

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
    assert waiting.status == "waiting_approval"
    operation = waiting.plans[-1].operation_id
    paused_run = await command(agent, waiting, "pause")
    revised = await command(agent, paused_run, "revise", goal="Revised file requirement")
    assert revised.goal_revision == 2 and not revised.plans
    view = await experience.trajectory(USER, "project", run.id)
    assert any(n.kind == "tool.prepared" for n in view.nodes)
    assert operation in next(e for e in view.episodes if e.goal_revision == 1).operation_ids
    assert not any(n.kind == "tool.started" for n in view.nodes)
