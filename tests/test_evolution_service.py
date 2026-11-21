import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from test_agent import agent as agent
from test_agent import generate, result
from test_assessment import assessment as assessment
from test_assessment import file_run
from test_context import USER
from test_context import context as context
from test_evolution import CONTENT, proposed

from auton.agent.contracts import RunLimits
from auton.agent.service import AgentRuntime
from auton.assess.contracts import EvalCase, EvaluateCommand, ImportCases
from auton.assess.service import Assessment
from auton.evolve.contracts import (
    ArenaCommand,
    ArenaControl,
    ArenaView,
    DiagnoseCommand,
    EvolutionConfig,
    Proposal,
    SubmitProposal,
    ToolCheckpoint,
)
from auton.evolve.dependencies import EvolutionDependencies
from auton.evolve.factory import EvolutionFactory
from auton.evolve.service import Evolution
from auton.genome.contracts import Asset
from auton.genome.ports import GenomePort
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult, ToolCall


@pytest.fixture
async def evolution(
    assessment: Assessment, agent: AgentRuntime, tmp_path: Path
) -> AsyncIterator[Evolution]:
    assets = cast(GenomePort, agent.deps.assets)
    service = EvolutionFactory().create(
        EvolutionConfig(directory=tmp_path / "evolve", reflection_model="fixture-model"),
        EvolutionDependencies(
            assets,
            assets,
            assets,
            assessment,
            agent.deps.models,
            agent,
            agent.deps.tools,
            agent.deps.context,
            agent.deps.runtime,
            RunLimits.model_validate(agent.config.model_dump(include=set(RunLimits.model_fields))),
            True,
        ),
        agent.deps.events,
    )
    assert isinstance(service, Evolution)
    await service.start()
    yield service
    await service.close()


async def prepare(
    service: Evolution, agent: AgentRuntime, assessment: Assessment, monkeypatch: pytest.MonkeyPatch
) -> tuple[Proposal, ArenaView]:
    genome = cast(GenomePort, agent.deps.assets)
    view = await genome.view(USER, "project")
    changed = await genome.propose(
        USER,
        "project",
        Asset(
            id="skill",
            name="Skill",
            kind="skill",
            content=CONTENT,
            origin="user_explicit",
            source="public synthetic test",
        ),
        view.candidates_revision,
    )
    assert changed.revision and changed.candidates_revision
    await genome.promote(USER, "project", "skill", changed.revision, changed.candidates_revision)
    base = await genome.resolve(USER, "project")
    done = await file_run(agent, monkeypatch)
    evidence = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="diagnosis-evidence",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert evidence.report
    diagnosis = await service.diagnose(
        USER,
        DiagnoseCommand(
            request_id="triage",
            project_id="project",
            asset_id="skill",
            report_ids=(evidence.report.id,),
        ),
    )
    command = proposed().command.model_copy(
        update={"diagnosis_id": diagnosis.id, "base_snapshot_id": base.id}
    )
    proposal = await service.propose(USER, command)
    assert proposal.status == "proposed", proposal.reasons
    assert await service.propose(USER, command) == proposal
    bank = await assessment.bank(USER)
    cases = (
        EvalCase(
            id="core",
            family="core",
            origin_group="core-origin",
            split="train",
            prompt="Write hello then a newline to notes.md.",
            kind="file",
            target_path="notes.md",
            expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
            source="test_fixture",
            data_domain="public",
        ),
        EvalCase(
            id="dev",
            family="dev",
            origin_group="dev-origin",
            split="development",
            prompt="Deliver the literal bytes hello followed by a newline into notes.md.",
            kind="file",
            target_path="notes.md",
            expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
            source="test_fixture",
            data_domain="public",
        ),
    )
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="evo-cases", expected_revision=bank.revision, cases=cases)
    )

    async def model(request: ModelRequest) -> ModelResult:
        value = (
            result(request, "The file operation finished.")
            if any(m.role == "tool" for m in request.messages)
            else result(
                request,
                calls=(
                    ToolCall(
                        id="write",
                        name="file_write",
                        arguments={"path": "notes.md", "content": "hello\n"},
                    ),
                ),
            )
        )
        return value.model_copy(update={"system_fingerprint": "fixture-fingerprint"})

    generate(agent, monkeypatch, model)
    arena = await service.create_arena(
        USER,
        ArenaCommand(
            request_id="arena",
            proposal_id=proposal.id,
            expected_proposal_version=proposal.version,
            bank_revision=bank.revision,
            train_cases=("core",),
            development_cases=("dev",),
            repeats=1,
            model_id="fixture-model",
            limits=RunLimits(
                max_steps=3, max_tokens=8000, max_cost_microusd=4000, max_tool_calls=1
            ),
            checkpoints=(ToolCheckpoint(name="old-digest"),),
        ),
    )
    return proposal, arena


async def control(service: Evolution, arena: ArenaView, action: str) -> ArenaView:
    return await service.control_arena(
        USER,
        arena.id,
        ArenaControl.model_validate(
            {
                "request_id": f"{action}-{arena.version}",
                "expected_version": arena.version,
                "action": action,
            }
        ),
    )


async def finish(service: Evolution, arena: ArenaView) -> ArenaView:
    await control(service, arena, "start")
    async with asyncio.timeout(30):
        while True:
            current = await service.arena(USER, arena.id)
            if current.status == "waiting_approval":
                assert next(
                    t for t in current.trials if t.id == current.current_trial
                ).pending_preview
                await control(service, current, "approve_current")
            elif current.status == "complete":
                return current
            elif current.status in {"blocked", "cancelled"}:
                pytest.fail(current.reason)
            await asyncio.sleep(0.02)


async def test_manual_proposal_full_isolated_arena_review_queue_replay_and_release_guard(
    evolution: Evolution,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, arena = await prepare(evolution, agent, assessment, monkeypatch)
    completed = await finish(evolution, arena)
    assert len(completed.trials) == 6 and completed.total_model_calls == 12
    assert all(t.outcome == "pass" and t.environment_verified for t in completed.trials)
    assert not completed.ready_for_release
    assert next(g for g in completed.gates if g.name == "G3_repeated_validation").verdict == "hold"
    updated = await evolution.proposal(USER, proposal.id)
    assert updated.current_arena_id == arena.id and updated.status == "blocked"
    genome = cast(GenomePort, agent.deps.assets)
    before = await genome.view(USER, "project")
    submit = SubmitProposal(
        request_id="reviewed",
        expected_version=updated.version,
        arena_id=arena.id,
        expected_learning_revision=before.candidates_revision,
        direction_reviewed=True,
    )
    original = evolution.deps.proposals.propose

    async def lost_ack(*args: object, **kwargs: object) -> object:
        await original(*args, **kwargs)  # type: ignore[arg-type]
        raise ApplicationError(503, "fixture_ack_lost", "Learning committed before response loss")

    monkeypatch.setattr(evolution.deps.proposals, "propose", lost_ack)
    with pytest.raises(ApplicationError) as interrupted:
        await evolution.submit(USER, proposal.id, submit)
    assert interrupted.value.code == "fixture_ack_lost"
    committed_revision = (await genome.view(USER, "project")).candidates_revision
    monkeypatch.setattr(evolution.deps.proposals, "propose", original)
    queued = await evolution.submit(USER, proposal.id, submit)
    assert queued.status == "review_queue" and queued.activation == "not_activated"
    assert await evolution.submit(USER, proposal.id, submit) == queued
    after = await genome.view(USER, "project")
    assert after.candidates_revision == committed_revision
    assert (
        after.revision == before.revision and after.candidates_revision == queued.learning_revision
    )
    assert after.assets[0].asset.content == CONTENT
    assert after.candidates[0].asset.content == proposal.candidate_content
    with pytest.raises(ApplicationError) as blocked:
        assert after.revision and after.candidates_revision
        await genome.promote(USER, "project", "skill", after.revision, after.candidates_revision)
    assert blocked.value.code == "release_control_required"
    assert (await evolution.playbook(USER, "project"))[0].outcome == "review_queue"
    assert await evolution.arenas(USER, "project") == (completed,)
    with pytest.raises(ApplicationError):
        await evolution.proposal(USER.model_copy(update={"owner": "other"}), proposal.id)


async def test_cancel_draft_never_dispatches_and_allows_new_arena(
    evolution: Evolution,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, arena = await prepare(evolution, agent, assessment, monkeypatch)
    await control(evolution, arena, "cancel")
    async with asyncio.timeout(5):
        await asyncio.gather(*list(evolution.runner.tasks.values()))
    latest = await evolution.arena(USER, arena.id)
    assert latest.status == "cancelled"
    assert not any(t.run_id for t in latest.trials)
    updated = await evolution.proposal(USER, proposal.id)
    assert updated.status == "blocked"
    new = await evolution.create_arena(
        USER,
        arena.command.model_copy(
            update={"request_id": "retry", "expected_proposal_version": updated.version}
        ),
    )
    assert new.id != arena.id
    with pytest.raises(ApplicationError):
        await control(evolution, latest, "resume")


async def test_changed_delivery_blocks_learning_submission(
    evolution: Evolution,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, arena = await prepare(evolution, agent, assessment, monkeypatch)
    completed = await finish(evolution, arena)
    trial = completed.trials[-1]
    root = agent.deps.tools.config.directory if hasattr(agent.deps.tools, "config") else None
    assert root is not None
    matches = list(root.rglob("notes.md"))
    assert matches
    # File check freshness must observe the actual private artifact, not the saved pass label.
    for path in matches:
        if trial.workspace_id in str(path):
            path.write_text("changed\n")
    updated = await evolution.proposal(USER, proposal.id)
    current = await evolution.deps.assets.view(USER, "project")
    with pytest.raises(ApplicationError) as changed:
        await evolution.submit(
            USER,
            proposal.id,
            SubmitProposal(
                request_id="stale",
                expected_version=updated.version,
                arena_id=arena.id,
                expected_learning_revision=current.candidates_revision,
                direction_reviewed=True,
            ),
        )
    assert changed.value.code == "evolution_evidence_changed"


async def test_restart_waiting_approval_and_changed_bank_cancellation_settles_original_child(
    evolution: Evolution,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, arena = await prepare(evolution, agent, assessment, monkeypatch)
    await control(evolution, arena, "start")
    async with asyncio.timeout(10):
        while True:
            current = await evolution.arena(USER, arena.id)
            if current.status == "waiting_approval":
                break
            await asyncio.sleep(0.02)
    await evolution.close()
    await evolution.start()
    stopped = await evolution.arena(USER, arena.id)
    assert stopped.status == "blocked"
    assert (await evolution.proposal(USER, proposal.id)).status == "blocked"
    bank = await assessment.bank(USER)
    await assessment.import_cases(
        USER,
        ImportCases(
            request_id="new-bank",
            expected_revision=bank.revision,
            cases=(
                EvalCase(
                    id="more-core",
                    family="more-core",
                    origin_group="more-origin",
                    split="train",
                    prompt="Produce a third unrelated public task.",
                    kind="file",
                    expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
                    target_path="notes.md",
                    source="test_fixture",
                ),
            ),
        ),
    )
    await control(evolution, stopped, "cancel")
    async with asyncio.timeout(5):
        await asyncio.gather(*list(evolution.runner.tasks.values()))
    cancelled = await evolution.arena(USER, arena.id)
    assert (
        cancelled.status == "cancelled" and cancelled.total_model_calls == stopped.total_model_calls
    )
    run_id = next(t.run_id for t in cancelled.trials if t.run_id)
    assert run_id and (await agent.get(USER, run_id)).status == "cancelled"
    assert all(t.run_id is None for t in cancelled.trials[1:])
