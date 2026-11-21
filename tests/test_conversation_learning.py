"""Pipeline tests use synthetic journals; none of these records are production labels."""

import asyncio
from pathlib import Path
from types import MethodType
from typing import cast

import pytest
from fastapi.testclient import TestClient
from test_agent import agent as agent
from test_agent import wait
from test_assessment import assessment as assessment
from test_context import USER
from test_context import context as context
from test_conversations import service as conversations_for
from test_datasets import datasets as datasets
from test_decision_review import reviewer as reviewer
from test_delegation import supervisor as supervisor
from test_evolution_service import evolution as evolution

from auton.agent.contracts import AgentRun
from auton.agent.lineage import conversation_ancestors
from auton.agent.service import AgentRuntime
from auton.assess.contracts import EvalCase, EvalJob, EvalReport, EvaluateCommand
from auton.assess.service import Assessment
from auton.constitution.config import Principal
from auton.conversation.contracts import ConversationCreate, ConversationTurn
from auton.conversation.ports import WorkspaceConversationPort
from auton.datasets.contracts import (
    DatasetArtifact,
    DatasetBuild,
    DatasetSnapshot,
    DatasetWithdrawal,
    TeacherUse,
)
from auton.datasets.service import Datasets
from auton.kernel.ports import ApplicationError
from auton.learning.contracts import LearningConfig, LearningPolicyCommand, LearningRetry
from auton.learning.dependencies import LearningDependencies
from auton.learning.factory import ConversationLearningFactory
from auton.learning.service import ConversationLearning
from auton.model.contracts import ModelMessage
from auton.model.gateway import ModelGateway


@pytest.fixture
def restore_assessment_gateway(datasets: Datasets, monkeypatch: pytest.MonkeyPatch) -> None:
    # The decision-review fixture installs its own JSON reviewer on the shared judge gateway.
    assessment = cast(Assessment, datasets.deps.assess)
    models = cast(ModelGateway, assessment.deps.models)
    monkeypatch.setattr(models, "generate", MethodType(ModelGateway.generate, models))


def learner(
    pipeline: Datasets,
    conversations: WorkspaceConversationPort,
    path: Path,
    background: bool = False,
) -> ConversationLearning:
    deps = pipeline.deps
    port = ConversationLearningFactory().create(
        LearningConfig(directory=path, background=background, poll_seconds=0.1),
        LearningDependencies(
            conversations,
            deps.agent,
            deps.assess,
            deps.reviews,
            pipeline,
            deps.events,
            deps.runtime,
            True,
        ),
    )
    assert isinstance(port, ConversationLearning)
    conversations.bind_observer(port)
    return port


async def turn(
    conversations: WorkspaceConversationPort,
    agent: AgentRuntime,
    identity: str | None = None,
    index: int = 0,
) -> tuple[str, AgentRun]:
    if identity is None:
        conversation = await conversations.create(
            USER, ConversationCreate(request_id="learning-chat", title="Fixture chat")
        )
        identity = conversation.id
    run = await conversations.send(
        USER,
        identity,
        ConversationTurn(
            request_id="turn-" + str(index),
            expected_turns=index,
            text="[TEST FIXTURE] Remember my name."
            if index == 0
            else "[TEST FIXTURE] What did I say?",
            model_id="fixture-model",
        ),
    )
    return identity, await wait(agent, run.id)


def authorized(run: AgentRun, **changes: object) -> LearningPolicyCommand:
    return LearningPolicyCommand.model_validate(
        {
            "enabled": True,
            "local_training_authorized": True,
            "data_license_reference": "Owned synthetic component fixture; not real provider rights",
            "allow_local_only_data": True,
            "allow_remote_review": True,
            "max_review_calls": 20,
            "teacher_uses": [
                TeacherUse(
                    model_id=run.command.model_id,
                    declared_revision=str(run.executor_spec["declared_revision"]),
                    terms_reference="Synthetic fixture terms only, no real provider attestation",
                    training_use_confirmed_by_user=True,
                ).model_dump()
            ],
            **changes,
        }
    )


async def test_discovery_without_consent_restart_grouping_and_owner_isolation(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
) -> None:
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    try:
        identity, first = await turn(conversations, agent)
        _, second = await turn(conversations, agent, identity, 1)
        assert first.status == second.status == "succeeded"
        state = await learning.tick(USER)
        assert len(state.cases) == 2 and state.policy is None
        assert {c.stage for c in state.cases} == {"collected"}
        assert len({c.split for c in state.cases}) == 1
        assert state.reserved_review_calls == 0
        assert len(await conversation_ancestors(USER, second, agent)) == 1
        assert not (await learning.status(Principal(owner="another", role="user"))).cases
    finally:
        await learning.close()
    restored = learner(datasets, conversations, tmp_path / "auto-learning")
    await restored.start()
    try:
        assert len((await restored.tick(USER)).cases) == 2
        assert (await restored.status(USER)).reserved_review_calls == 0
    finally:
        await restored.close()


async def test_explicit_transfer_and_lifetime_call_allowance_precede_dispatch(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
) -> None:
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    try:
        _, run = await turn(conversations, agent)
        await learning.configure(USER, authorized(run, allow_remote_review=False))
        state = await learning.tick(USER)
        case = state.cases[0]
        assert case.stage == "hold" and case.reasons == ("learning_review_transfer_not_authorized",)
        await learning.configure(USER, authorized(run, expected_version=0, max_review_calls=1))
        await learning.retry(USER, case.id, LearningRetry(expected_version=case.version))
        state = await learning.tick(USER)
        assert state.reserved_review_calls == 0
        assert state.cases[0].reasons == ("learning_review_call_budget",)
    finally:
        await learning.close()


@pytest.mark.usefixtures("restore_assessment_gateway")
async def test_uncalibrated_response_and_shadow_decisions_never_become_training_data(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
) -> None:
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    try:
        _, run = await turn(conversations, agent)
        await learning.configure(USER, authorized(run))
        state = await learning.tick(USER)
        case = state.cases[0]
        assert case.stage == "hold"
        assert "independent_assessment_not_qualified" in case.reasons
        assert state.reserved_review_calls == 2 and not case.artifact_ids
        assert case.decision_outcomes
        assert set(case.decision_outcomes.values()) == {"HOLD:shadow_answer_not_eligible"}
        assert (await learning.tick(USER)).reserved_review_calls == 2
    finally:
        await learning.close()


async def test_interrupted_dispatch_is_not_automatically_replayed(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    calls = 0

    async def interrupted(principal: Principal, command: EvaluateCommand) -> EvalJob:
        nonlocal calls
        calls += 1
        raise RuntimeError("Simulated connection loss after dispatch")

    monkeypatch.setattr(datasets.deps.assess, "evaluate", interrupted)
    try:
        _, run = await turn(conversations, agent)
        await learning.configure(USER, authorized(run))
        with pytest.raises(RuntimeError):
            await learning.tick(USER)
        assert (await learning.status(USER)).cases[0].stage == "assessing"
    finally:
        await learning.close()
    restored = learner(datasets, conversations, tmp_path / "auto-learning")
    await restored.start()
    try:
        state = await restored.tick(USER)
        assert calls == 1 and state.reserved_review_calls == 2
        assert state.cases[0].stage == "hold" and not state.cases[0].artifact_ids
    finally:
        await restored.close()


async def fixture_semantic_pass(pipeline: Datasets, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate a calibrated reviewer, retaining synthetic source exclusion downstream."""
    original = pipeline.deps.assess.evaluate
    read = pipeline.deps.assess.report
    reports: dict[str, EvalReport] = {}

    async def evaluate(principal: Principal, command: EvaluateCommand) -> EvalJob:
        job = await original(principal, command)
        assert job.report
        report = job.report.model_copy(
            update={
                "semantic_verdict": "pass",
                "outcome": "pass",
                "reasons": (),
                "judges": tuple(
                    j.model_copy(
                        update={
                            "verdict": "pass",
                            "source": "remote",
                            "self_eval_bias": False,
                            "dispatch_outcome": "confirmed",
                        }
                    )
                    for j in job.report.judges
                ),
            }
        )
        reports[report.id] = report
        return job.model_copy(update={"report": report})

    async def report(principal: Principal, identity: str) -> EvalReport:
        return reports[identity] if identity in reports else await read(principal, identity)

    monkeypatch.setattr(pipeline.deps.assess, "evaluate", evaluate)
    monkeypatch.setattr(pipeline.deps.assess, "report", report)


@pytest.mark.usefixtures("restore_assessment_gateway")
async def test_multiturn_original_frames_to_assistant_only_sft_keep_synthetic_gate(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await fixture_semantic_pass(datasets, monkeypatch)
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    try:
        identity, first = await turn(conversations, agent)
        _, second = await turn(conversations, agent, identity, 1)
        await learning.configure(USER, authorized(first))
        state = await learning.tick(USER)
        assert state.reserved_review_calls == 4
        assert all(
            c.stage == "hold" and "synthetic_data_not_training_qualified" in c.reasons
            for c in state.cases
        )
        snapshots = [await datasets.get(USER, c.dataset_ids[0]) for c in state.cases]
        assert all(s.status == "engineering_only" and not s.training_ready for s in snapshots)
        example = snapshots[1].examples[0]
        assert example.target_message and example.target_message.content == second.final_text
        assert any(m.content == first.command.goal for m in example.input_messages)
        assert example.loss_message_indices == (len(example.input_messages),)
        assert not example.following_tool_results and example.engineering_only
        assert any(first.id in token for token in example.lineage_tokens)
        assert not any(c.artifact_ids for c in state.cases)
        affected = await datasets.withdraw(
            USER,
            DatasetWithdrawal(
                request_id="withdraw-history",
                project_id=first.command.project_id,
                run_id=first.id,
                reason="Withdraw this fixture and any historical descendants",
            ),
        )
        assert set(affected) == {snapshot.id for snapshot in snapshots}
        invalid = await datasets.get(USER, snapshots[1].id)
        assert not invalid.current_evidence_valid
        assert "dataset_history_source_withdrawn" in invalid.invalidation_reasons
        rebuilt = await datasets.build(
            USER, snapshots[1].command.model_copy(update={"request_id": "retry-withdrawn-history"})
        )
        assert not rebuilt.examples and rebuilt.rejected[0].reasons == (
            "dataset_history_source_withdrawn",
        )

    finally:
        await learning.close()


@pytest.mark.usefixtures("restore_assessment_gateway")
async def test_qualified_branch_exports_once_and_revalidates_revocation(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise orchestration after the qualification port; keep real fixture exclusion above.
    await fixture_semantic_pass(datasets, monkeypatch)
    build = datasets.build
    snapshots: dict[str, DatasetSnapshot] = {}
    exports: list[str] = []

    async def qualified(principal: Principal, command: DatasetBuild) -> DatasetSnapshot:
        snapshot = await build(principal, command)
        assert snapshot.status == "engineering_only"
        simulated = snapshot.model_copy(update={"status": "ready", "training_ready": True})
        snapshots[simulated.id] = simulated
        return simulated

    async def get(principal: Principal, identity: str) -> DatasetSnapshot:
        return snapshots[identity]

    async def export(principal: Principal, identity: str, command: object) -> DatasetArtifact:
        from auton.datasets.contracts import ExportCommand

        assert isinstance(command, ExportCommand)
        exports.append(identity)
        return DatasetArtifact(
            id="a" * 64,
            snapshot_id=identity,
            command=command,
            sha256="b" * 64,
            size=10,
            example_count=1,
            manifest_digest="c" * 64,
        )

    monkeypatch.setattr(datasets, "build", qualified)
    monkeypatch.setattr(datasets, "get", get)
    monkeypatch.setattr(datasets, "export", export)
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning")
    await learning.start()
    try:
        _, run = await turn(conversations, agent)
        await learning.configure(USER, authorized(run))
        state = await learning.tick(USER)
        assert state.cases[0].stage == "ready" and len(exports) == 1
        assert (await learning.tick(USER)).cases[0].stage == "ready" and len(exports) == 1
        snapshot = snapshots[exports[0]]
        snapshots[snapshot.id] = snapshot.model_copy(
            update={
                "current_evidence_valid": False,
                "invalidation_reasons": ("data_grant_revoked",),
            }
        )
        status = await learning.status(USER)
        assert status.cases[0].stage == "hold" and status.cases[0].reasons == (
            "data_grant_revoked",
        )
    finally:
        await learning.close()


async def test_fabricated_or_changed_history_cannot_become_source(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
) -> None:
    conversations = conversations_for(agent)
    _, run = await turn(conversations, agent)
    forged = run.model_copy(
        update={
            "command": run.command.model_copy(
                update={
                    "prior_messages": (
                        ModelMessage(role="user", content="unproven historical prompt"),
                    ),
                }
            )
        }
    )
    with pytest.raises(ApplicationError) as error:
        await conversation_ancestors(USER, forged, agent)
    assert error.value.code == "conversation_history_unproven"
    # Response meta cases can now calibrate exactly this task kind, never repurposed as train.
    case = EvalCase(
        id="response-meta",
        family="response-family",
        origin_group="independent-human",
        split="meta",
        prompt="Human reference prompt",
        kind="response",
        source="human_seed",
        human_verdict="pass",
        human_answer="Human verified reference answer",
    )
    assert case.kind == "response"


def test_learning_api_observes_browser_conversation_without_frontend_configuration(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/conversations", json={"request_id": "auto-collect", "title": "Auto collect"}
    )
    assert created.status_code == 200, created.text
    sent = client.post(
        "/api/v1/conversations/" + created.json()["id"] + "/turns",
        json={
            "request_id": "turn",
            "expected_turns": 0,
            "text": "hello",
            "model_id": "fixture-model",
        },
    )
    assert sent.status_code == 200, sent.text
    collected = client.post("/api/v1/learning/tick")
    assert collected.status_code == 200, collected.text
    assert len(collected.json()["cases"]) == 1
    assert collected.json()["reserved_review_calls"] == 0
    assert collected.json()["activation"] == "no_training_started"
    assert client.put("/api/v1/learning/policy", json={"enabled": True}).status_code == 422
    disabled = client.put("/api/v1/learning/policy", json={"enabled": False})
    assert disabled.status_code == 200
    assert client.put("/api/v1/learning/policy", json={"enabled": False}).status_code == 409


async def test_background_worker_discovers_new_turn_without_manual_tick(
    datasets: Datasets,
    agent: AgentRuntime,
    tmp_path: Path,
) -> None:
    conversations = conversations_for(agent)
    learning = learner(datasets, conversations, tmp_path / "auto-learning", background=True)
    await learning.start()
    try:
        _, run = await turn(conversations, agent)
        for _ in range(100):
            state = await learning.status(USER)
            if state.cases:
                break
            await asyncio.sleep(0.02)
        assert len(state.cases) == 1 and state.cases[0].run_id == run.id
        assert state.cases[0].stage == "collected" and state.reserved_review_calls == 0
    finally:
        await learning.close()
