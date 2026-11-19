import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import pytest
from test_agent import agent as agent
from test_agent import command, create, wait
from test_assessment import assessment as assessment
from test_context import USER
from test_context import context as context
from test_decision_review import reviewer as reviewer
from test_delegation import supervisor as supervisor
from test_evolution_service import evolution as evolution

from auton.agent.service import AgentRuntime
from auton.assess.contracts import EvaluateCommand
from auton.assess.service import Assessment
from auton.datasets.contracts import (
    DataGrant,
    DataGrantCommand,
    DatasetBuild,
    DatasetConfig,
    DatasetSnapshot,
    SubjectRef,
    TeacherUse,
)
from auton.datasets.curation import validate_loss_mask
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.factory import DatasetPipelineFactory
from auton.datasets.service import Datasets
from auton.decision_review.service import DecisionReview
from auton.delegation.service import Delegation
from auton.evolve.service import Evolution
from auton.genome.ports import GenomePort
from auton.kernel.ports import ApplicationError
from auton.model.gateway import ModelGateway
from auton.model.provider import MockProvider


@pytest.fixture
async def datasets(
    assessment: Assessment,
    agent: AgentRuntime,
    reviewer: DecisionReview,
    supervisor: Delegation,
    evolution: Evolution,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Datasets]:
    models = cast(ModelGateway, agent.deps.models)
    assert isinstance(models.provider, MockProvider)
    models.provider.scenario = "agent_acceptance"
    from types import MethodType

    monkeypatch.setattr(models, "generate", MethodType(ModelGateway.generate, models))
    monkeypatch.setattr(models, "stream", MethodType(ModelGateway.stream, models))
    service = DatasetPipelineFactory().create(
        DatasetConfig(directory=tmp_path / "datasets"),
        DatasetDependencies(
            agent,
            assessment,
            cast(GenomePort, agent.deps.assets),
            agent.deps.context,
            reviewer,
            evolution,
            supervisor,
            agent.deps.events,
            agent.deps.runtime,
            True,
        ),
    )
    assert isinstance(service, Datasets)
    await service.start()
    yield service
    await service.close()


async def source(
    service: Datasets, identity: str, goal: str = "Write hello followed by a newline to notes.md."
) -> SubjectRef:
    actor = service.deps.agent
    assert isinstance(actor, AgentRuntime)
    await actor.deps.tools.create_workspace(USER, identity, "Dataset private source", False)
    created = await actor.create(
        USER,
        create(
            request_id=identity,
            workspace_id=identity,
            goal=goal,
            allowed_tools=("file.write",),
            acceptance={
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
        ),
    )
    assert isinstance(actor, AgentRuntime)
    paused = await wait(actor, created.id)
    assert paused.status == "waiting_approval", paused.reason
    await command(actor, paused, "approve", request_id="approve-" + identity)
    done = await wait(actor, created.id)
    assert done.status == "succeeded", done.reason
    checked = await service.deps.assess.evaluate(
        USER,
        EvaluateCommand(
            request_id="check-" + identity,
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert checked.report and checked.report.outcome == "pass"
    return SubjectRef(
        run_id=done.id,
        expected_version=done.version,
        assessment_report_id=checked.report.id,
        family=identity,
        origin_group=identity,
    )


async def grant(
    service: Datasets, ref: SubjectRef, identity: str = "grant-data", teacher: bool = True
) -> DataGrant:
    run = await service.deps.agent.get(USER, ref.run_id)
    return await service.grant(
        USER,
        DataGrantCommand(
            request_id=identity,
            project_id="project",
            run_ids=(ref.run_id,),
            purposes=("executor", "decision", "router"),
            data_license_reference="Owned synthetic fixture for component testing only",
            local_training_authorized=True,
            allow_local_only_data=True,
            teacher_uses=(
                TeacherUse(
                    model_id=run.command.model_id,
                    declared_revision=str(run.executor_spec["declared_revision"]),
                    terms_reference="Synthetic fixture license; not a real provider attestation",
                    training_use_confirmed_by_user=teacher,
                ),
            ),
        ),
    )


async def test_actual_journal_to_canonical_action_loss_mask_and_fixture_gate(
    datasets: Datasets,
) -> None:
    ref = await source(datasets, "dataset-one")
    allowed = await grant(datasets, ref)
    build = DatasetBuild(
        request_id="canonical",
        project_id="project",
        kind="executor",
        grant_id=allowed.id,
        subjects=(ref,),
    )
    snapshot = await datasets.build(USER, build)
    assert snapshot.status == "engineering_only" and not snapshot.training_ready, snapshot.rejected
    assert len(snapshot.examples) == 1 and snapshot.current_evidence_valid
    assert await datasets.build(USER, build) == snapshot
    example = snapshot.examples[0]
    assert example.target_message and example.target_message.tool_calls[0].name == "file_write"
    assert example.following_tool_results and example.following_tool_results[0].role == "tool"
    assert example.loss_message_indices == (len(example.input_messages),)
    assert all(message not in example.input_messages for message in example.following_tool_results)
    encoded = datasets.renderer.encode(snapshot.examples)
    assert b"loss_message_indices" in encoded and b"input_message_count" in encoded
    assert b"proofs" not in encoded and b"following_tool_results" not in encoded
    with pytest.raises(ApplicationError) as masked:
        validate_loss_mask(example.model_copy(update={"loss_message_indices": (0,)}))
    assert masked.value.code == "dataset_wrong_loss_mask"
    with pytest.raises(ApplicationError) as truncated:
        validate_loss_mask(example.model_copy(update={"following_tool_results": ()}))
    assert truncated.value.code == "dataset_truncated_tool_pair"
    from auton.datasets.contracts import ExportCommand

    with pytest.raises(ApplicationError) as fixture:
        await datasets.export(
            USER,
            snapshot.id,
            ExportCommand(
                request_id="no-fixture-training",
                expected_content_digest=snapshot.content_digest,
                split="train",
                purpose="local_training",
            ),
        )
    assert fixture.value.code == "dataset_not_exportable"


async def test_same_prompt_new_origin_cannot_cross_permanent_split(datasets: Datasets) -> None:
    first = await source(datasets, "train-source")
    consent = await grant(datasets, first)
    train = await datasets.build(
        USER,
        DatasetBuild(
            request_id="train-split",
            project_id="project",
            kind="executor",
            grant_id=consent.id,
            subjects=(first,),
        ),
    )
    assert train.examples
    second = await source(datasets, "validation-source")
    other = await grant(datasets, second, "other-grant")
    validation = await datasets.build(
        USER,
        DatasetBuild(
            request_id="cannot-relabel",
            project_id="project",
            kind="executor",
            grant_id=other.id,
            subjects=(
                second.model_copy(
                    update={
                        "split": "validation",
                        "family": "changed-family",
                        "origin_group": "changed-origin",
                    }
                ),
            ),
        ),
    )
    assert not validation.examples and not validation.training_ready
    assert any("dataset_group_split_conflict" in r.reasons for r in validation.rejected)
    assert (await datasets.get(USER, train.id)).current_evidence_valid


async def test_unknown_teacher_rights_and_source_withdrawal_block_reuse(datasets: Datasets) -> None:
    ref = await source(datasets, "rights-source")
    unknown = await grant(datasets, ref, teacher=False)
    build = DatasetBuild(
        request_id="unknown-rights",
        project_id="project",
        kind="executor",
        grant_id=unknown.id,
        subjects=(ref,),
    )
    blocked = await datasets.build(USER, build)
    assert not blocked.examples and any(
        "dataset_teacher_terms_unknown" in r.reasons for r in blocked.rejected
    )
    allowed = await grant(datasets, ref, "known-fixture-rights")
    good = await datasets.build(
        USER, build.model_copy(update={"request_id": "fixture-only", "grant_id": allowed.id})
    )
    assert good.examples
    from auton.datasets.contracts import DatasetWithdrawal

    impacted = await datasets.withdraw(
        USER,
        DatasetWithdrawal(
            request_id="withdraw-source",
            project_id="project",
            run_id=ref.run_id,
            reason="Remove this exact source from all future training uses.",
        ),
    )
    assert good.id in impacted
    stale = await datasets.get(USER, good.id)
    assert not stale.current_evidence_valid and not stale.training_ready
    assert "dataset_source_withdrawn" in stale.invalidation_reasons
    assert not (await datasets.build(USER, good.command)).current_evidence_valid
    with pytest.raises(ApplicationError):
        await datasets.get(USER.model_copy(update={"owner": "other"}), good.id)


async def test_grant_withdrawal_is_idempotent_and_request_scope_is_immutable(
    datasets: Datasets,
) -> None:
    from auton.datasets.contracts import DatasetWithdrawal

    ref = await source(datasets, "withdraw-grant")
    allowed = await grant(datasets, ref)
    snapshot = await datasets.build(
        USER,
        DatasetBuild(
            request_id="withdraw-build",
            project_id="project",
            kind="executor",
            grant_id=allowed.id,
            subjects=(ref,),
        ),
    )
    command = DatasetWithdrawal(
        request_id="same-withdraw",
        project_id="project",
        grant_id=allowed.id,
        reason="Explicit scoped test withdrawal",
    )
    affected = await datasets.withdraw(USER, command)
    assert snapshot.id in affected
    assert await datasets.withdraw(USER, command) == affected
    assert (await datasets.get(USER, snapshot.id)).status == "blocked"
    with pytest.raises(ApplicationError) as conflict:
        await datasets.withdraw(
            USER,
            command.model_copy(update={"reason": "Different immutable withdrawal explanation"}),
        )
    assert conflict.value.code == "datasets_request_conflict"


async def test_protected_holdout_cannot_be_relabeled_with_new_family(datasets: Datasets) -> None:
    from auton.assess.contracts import normalize_protected_input
    from auton.kernel.documents import key
    from auton.kernel.events import Event

    ref = await source(datasets, "protected-source")
    allowed = await grant(datasets, ref)
    run = await datasets.deps.agent.get(USER, ref.run_id)
    await datasets.deps.events.append(
        [
            Event(
                event_id="assess-protected:"
                + key(USER.owner, normalize_protected_input(run.command.goal)),
                kind="test.protected_marker",
                timestamp=datasets.deps.runtime.now(),
                source="test",
                payload={},
            )
        ]
    )
    snapshot = await datasets.build(
        USER,
        DatasetBuild(
            request_id="protected-build",
            project_id="project",
            kind="executor",
            grant_id=allowed.id,
            subjects=(ref,),
        ),
    )
    assert snapshot.status == "blocked" and not snapshot.examples
    assert snapshot.rejected[0].reasons == ("dataset_protected_holdout",)


async def test_optimization_baseline_request_is_excluded(
    datasets: Datasets, monkeypatch: pytest.MonkeyPatch
) -> None:
    ref = await source(datasets, "protected-arena-baseline")
    allowed = await grant(datasets, ref)

    async def protected(*args: object) -> tuple[str, ...]:
        return ("protected-arena-baseline",)

    monkeypatch.setattr(datasets.deps.optimization, "optimization_request_ids", protected)
    snapshot = await datasets.build(
        USER,
        DatasetBuild(
            request_id="arena-block",
            project_id="project",
            kind="executor",
            grant_id=allowed.id,
            subjects=(ref,),
        ),
    )
    assert snapshot.status == "blocked"
    assert snapshot.rejected[0].reasons == ("dataset_optimization_input",)


async def test_decision_requires_current_keep_and_router_requires_observed_pair(
    datasets: Datasets,
) -> None:
    from auton.datasets.contracts import RouterPair

    first = await source(datasets, "decision-no-keep")
    allowed = await grant(datasets, first)
    decision = await datasets.build(
        USER,
        DatasetBuild(
            request_id="no-keep-label",
            project_id="project",
            kind="decision",
            grant_id=allowed.id,
            subjects=(first.model_copy(update={"review_id": "0" * 64}),),
        ),
    )
    assert decision.status == "blocked" and not decision.examples
    assert decision.rejected[0].reasons == ("dataset_decision_not_keep",)
    router = await datasets.build(
        USER,
        DatasetBuild(
            request_id="no-counterfactual",
            project_id="project",
            kind="router",
            grant_id=allowed.id,
            subjects=(first,),
            router_pairs=(
                RouterPair(left_run_id=first.run_id, right_run_id="missing-observed-run"),
            ),
        ),
    )
    assert router.status == "blocked" and not router.examples


async def test_revoked_grant_after_lost_ack_recovers_without_repeating_commit(
    datasets: Datasets, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.datasets.contracts import DatasetWithdrawal

    ref = await source(datasets, "lost-withdraw-ack")
    allowed = await grant(datasets, ref)
    command = DatasetWithdrawal(
        request_id="lost-ack",
        project_id="project",
        grant_id=allowed.id,
        reason="Simulated acknowledgment loss after durable revocation",
    )
    original = datasets.store.audit
    raised = False

    async def audit(
        kind: str, owner: str, identity: str, version: int, value: dict[str, Any], created: float
    ) -> None:
        nonlocal raised
        if kind == "grant" and version == 1 and not raised:
            raised = True
            raise RuntimeError("Simulated process loss after durable commit")
        await original(kind, owner, identity, version, value, created)

    monkeypatch.setattr(datasets.store, "audit", audit)
    with pytest.raises(RuntimeError, match="Simulated process loss"):
        await datasets.withdraw(USER, command)
    monkeypatch.setattr(datasets.store, "audit", original)
    assert (await datasets.load_grant(USER, allowed.id)).revoked
    assert await datasets.withdraw(USER, command) == ()
    assert (await datasets.load_grant(USER, allowed.id)).version == 1


async def test_export_disk_faults_and_source_change_recheck(
    datasets: Datasets, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I/O fault injection only: substitute admission, never claim runtime qualification."""
    from auton.datasets.contracts import ExportCommand

    ref = await source(datasets, "io-component-fixture")
    allowed = await grant(datasets, ref)
    fixture = await datasets.build(
        USER,
        DatasetBuild(
            request_id="io-fixture",
            project_id="project",
            kind="executor",
            grant_id=allowed.id,
            subjects=(ref,),
        ),
    )
    assert fixture.status == "engineering_only"
    approved_stub = fixture.model_copy(update={"status": "ready", "training_ready": True})

    async def admission_stub(*args: object) -> DatasetSnapshot:
        return approved_stub

    monkeypatch.setattr(datasets, "get", admission_stub)
    command = ExportCommand(
        request_id="io-export",
        expected_content_digest=fixture.content_digest,
        purpose="local_training",
    )
    artifact = await datasets.export(USER, fixture.id, command)
    path = datasets.artifact_path(artifact.id)
    assert path.stat().st_mode & 0o777 == 0o600
    saved, content = await datasets.read_artifact(USER, artifact.id)
    assert saved == artifact and hashlib.sha256(content).hexdigest() == artifact.sha256
    path.unlink()
    with pytest.raises(ApplicationError) as missing:
        await datasets.read_artifact(USER, artifact.id)
    assert missing.value.code == "dataset_artifact_unavailable"
    assert await datasets.export(USER, fixture.id, command) == artifact
    path.write_bytes(b"tampered")
    with pytest.raises(ApplicationError) as corrupt:
        await datasets.read_artifact(USER, artifact.id)
    assert corrupt.value.code == "dataset_artifact_corrupt"
    with pytest.raises(ApplicationError) as collision:
        await datasets.export(USER, fixture.id, command)
    assert collision.value.code == "dataset_export_collision"
    path.write_bytes(content)
    calls = 0

    async def changing_admission(*args: object) -> DatasetSnapshot:
        nonlocal calls
        calls += 1
        return (
            approved_stub
            if calls == 1
            else approved_stub.model_copy(update={"current_evidence_valid": False})
        )

    monkeypatch.setattr(datasets, "get", changing_admission)
    with pytest.raises(ApplicationError) as withdrawn:
        await datasets.read_artifact(USER, artifact.id)
    assert withdrawn.value.code == "dataset_artifact_withdrawn" and calls == 2
