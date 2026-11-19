import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from test_agent import agent as agent
from test_agent import command, create, generate, result, wait
from test_context import USER
from test_context import context as context

from auton.agent.contracts import AgentRun
from auton.agent.service import AgentRuntime
from auton.assess.contracts import (
    AssessConfig,
    BlindWindowCommand,
    EvalCase,
    EvaluateCommand,
    ImportCases,
)
from auton.assess.factory import AssessFactory
from auton.assess.service import AssessDependencies, Assessment
from auton.assess.statistics import aggregate, kappa, wilson
from auton.constitution.config import Principal
from auton.constitution.secrets import SecretStoreFactory
from auton.datasets.contracts import DatasetConfig
from auton.decision_review.contracts import DecisionReviewConfig
from auton.evolve.contracts import EvolutionConfig
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError
from auton.model.config import ModelConfig
from auton.model.contracts import ModelRequest, ModelResult, ToolCall
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies


@pytest.fixture
async def assessment(agent: AgentRuntime, tmp_path: Path) -> AsyncIterator[Assessment]:
    judge_events = EventLogFactory().create(KernelConfig(data_directory=tmp_path / "private-judge"))
    await judge_events.start()
    judge_models = ModelGatewayFactory().create(
        ModelConfig(backend="mock"),
        GatewayDependencies(
            agent.deps.goals, judge_events, agent.deps.runtime, SecretStoreFactory().create()
        ),
    )
    await judge_models.start()
    service = AssessFactory().create(
        AssessConfig(directory=tmp_path / "assess", judge_model="fixture-model"),
        AssessDependencies(
            agent,
            agent.deps.tools,
            agent.deps.context,
            judge_models,
            agent.deps.events,
            agent.deps.runtime,
            True,
        ),
    )
    assert isinstance(service, Assessment)
    await service.start()
    yield service
    await service.close()
    await judge_models.close()
    await judge_events.close()


async def file_run(
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
    request_id: str = "assess-file",
    goal: str = "Write hello followed by a newline to notes.md.",
) -> AgentRun:
    async def model(request: ModelRequest) -> ModelResult:
        if any(m.role == "tool" for m in request.messages):
            return result(
                request, "The file operation finished; an independent verifier must inspect it."
            )
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
    workspace = "scope-" + request_id
    await agent.deps.tools.create_workspace(USER, workspace, "Assessment fixture", False)
    created = await agent.create(
        USER,
        create(
            request_id=request_id,
            workspace_id=workspace,
            goal=goal,
            acceptance={
                "kind": "file",
                "path": "notes.md",
                "sha256": hashlib.sha256(b"hello\n").hexdigest(),
            },
            allowed_tools=["file.write"],
        ),
    )
    paused = await wait(agent, created.id)
    assert paused.status == "waiting_approval"
    await command(agent, paused, "approve", request_id="approve-" + request_id)
    done = await wait(agent, created.id)
    assert done.status == "succeeded"
    return done


async def test_independent_file_check_source_replay_and_unknown_denominator(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = await file_run(agent, monkeypatch)
    request = EvaluateCommand(
        request_id="verify-file",
        project_id="project",
        run_id=done.id,
        expected_version=done.version,
    )
    job = await assessment.evaluate(USER, request)
    assert job.report and job.report.outcome == "pass" and not job.report.quality_release_eligible
    assert job.report.environment_verified and job.report.metrics.usage_complete
    assert job.report.semantic_verdict == "unknown" and job.report.source == "test"
    again = await assessment.evaluate(USER, request)
    assert again.report == job.report
    assert (await assessment.job(USER, job.id)).status == "complete"
    summary = aggregate((job.report, job.report))
    assert summary.total == 1 and summary.known_denominator == 1 and summary.passed == 1
    unknown = job.report.model_copy(update={"case_id": "unknown-case", "outcome": "unknown"})
    failure = job.report.model_copy(update={"case_id": "failure-case", "outcome": "fail"})
    stats = aggregate((job.report, unknown, failure))
    assert (
        stats.total == 3
        and stats.known_denominator == 2
        and stats.pass_rate == 0.5
        and stats.unknown == 1
    )
    assert stats.wilson_lower is not None and stats.wilson_lower < 0.2
    from auton.assess.contracts import JudgeObservation

    judge = JudgeObservation(
        request_id="paid-judge-one",
        rubric_revision="assess-rubric-v1",
        configuration_digest=assessment.config.digest,
        verdict="unknown",
        reason="untrusted",
        source="test",
        cost_microusd=100,
        dispatch_outcome="confirmed",
    )
    paid = job.report.model_copy(update={"judges": (judge,)})
    another = paid.model_copy(
        update={
            "judges": (
                judge.model_copy(update={"request_id": "paid-judge-two", "cost_microusd": None}),
            )
        }
    )
    repeated = aggregate((paid, another, paid))
    assert repeated.total == 1 and repeated.evaluation_cost_microusd == 100
    assert repeated.evaluation_unknown_calls == 1
    with pytest.raises(ApplicationError):
        await assessment.evaluate(USER, request.model_copy(update={"semantic": True}))
    with pytest.raises(ApplicationError):
        await assessment.evaluate(USER.model_copy(update={"role": "training"}), request)
    with pytest.raises(ApplicationError):
        await assessment.job(USER.model_copy(update={"owner": "other"}), job.id)


async def test_business_gold_does_not_trust_actor_success_and_old_artifact_is_not_reused(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = await file_run(agent, monkeypatch)
    bank = await assessment.bank(USER)
    case = EvalCase(
        id="gold",
        family="exact-file",
        origin_group="file-parent",
        split="train",
        prompt=done.command.goal,
        kind="file",
        expected_sha256=hashlib.sha256(b"independent target").hexdigest(),
        target_path="notes.md",
        source="test_fixture",
        critical=True,
    )
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="gold-import", expected_revision=bank.revision, cases=(case,))
    )
    job = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="gold-verify",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
            case_id="gold",
            bank_revision=bank.revision,
        ),
    )
    assert done.check and done.check.outcome == "passed"
    assert (
        job.report
        and job.report.outcome == "fail"
        and any(s.reason == "independent_file_digest_mismatch" for s in job.report.signals)
    )
    # Trusted host fixture simulates an out-of-band artifact mutation. No previous pass is reusable.
    original = agent.deps.tools.artifact

    async def unavailable(principal: Principal, operation: str) -> tuple[str, bytes]:
        raise ApplicationError(409, "artifact_changed", "Artifact changed after verification")

    monkeypatch.setattr(agent.deps.tools, "artifact", unavailable)
    later = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="verify-after-change",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert (
        later.report
        and later.report.outcome == "environment_error"
        and not later.report.quality_release_eligible
    )
    monkeypatch.setattr(agent.deps.tools, "artifact", original)


def case(identity: str, split: str = "train", **changes: object) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": identity,
            "family": identity,
            "origin_group": identity,
            "split": split,
            "prompt": "Question " + identity,
            "kind": "research",
            "source": "test_fixture",
            **changes,
        }
    )


async def test_split_family_origin_normalization_and_retirement_locks(
    assessment: Assessment,
) -> None:
    bank = await assessment.bank(USER)
    first = case("seed", prompt="Solve Case 123")
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="seed-import", expected_revision=bank.revision, cases=(first,))
    )

    for index, leak in enumerate(
        (
            case("other", split="test", family="seed"),
            case("other", split="development", origin_group="seed"),
            case("other", split="test", prompt="  SOLVE case 456  "),
        )
    ):
        with pytest.raises(ApplicationError) as error:
            await assessment.import_cases(
                USER,
                ImportCases(
                    request_id=f"leak-{index}", expected_revision=bank.revision, cases=(leak,)
                ),
            )
        assert error.value.code == "evaluation_split_leak"
    protected = case("protected", split="test")
    bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="protected-import", expected_revision=bank.revision, cases=(protected,)
        ),
    )
    for principal in (
        USER,
        USER.model_copy(update={"role": "training"}),
        USER.model_copy(update={"role": "evolution"}),
    ):
        with pytest.raises(ApplicationError):
            await assessment.store.read_case(principal, "protected", bank.revision, "training")
    train = await assessment.train_cases(USER.model_copy(update={"role": "training"}))
    assert [item.id for item in train] == ["seed"]
    with pytest.raises(ApplicationError):
        await assessment.import_cases(
            USER.model_copy(update={"role": "evolution"}),
            ImportCases(
                request_id="forbidden", expected_revision=bank.revision, cases=(case("evo"),)
            ),
        )
    with pytest.raises(ApplicationError):
        await assessment.import_cases(
            USER,
            ImportCases(
                request_id="move-protected",
                expected_revision=bank.revision,
                cases=(protected.model_copy(update={"split": "train"}),),
            ),
        )
    # Shared event journal stores only references/fingerprints, never private case text or gold.
    rows = await assessment.deps.events.read(limit=1000)
    assert all("Question protected" not in row.event.canonical() for row in rows)


async def test_blind_window_atomic_concurrent_limits_and_train_growth(
    assessment: Assessment,
) -> None:
    bank = await assessment.bank(USER)
    bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="test-pack",
            expected_revision=bank.revision,
            cases=(case("heldout", split="test"),),
        ),
    )
    request = BlindWindowCommand(
        request_id="window",
        bank_revision=bank.revision,
        split="test",
        purpose="release",
        candidate_revision="candidate",
    )
    window = await assessment.open_window(USER, request)
    assert await assessment.open_window(USER, request) == window
    with pytest.raises(ApplicationError):
        await assessment.open_window(
            USER, request.model_copy(update={"request_id": "adaptive-probe"})
        )
    next_bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="new-train", expected_revision=bank.revision, cases=(case("new-train"),)
        ),
    )
    assert next_bank.revision != bank.revision
    assert (
        await assessment.store.split_digest(USER.owner, next_bank.revision, "test")
        == window.split_digest
    )
    outcomes = await asyncio.gather(
        *[
            assessment.store.consume_window(USER.owner, window.id, bank.revision, "test", identity)
            for identity in ("a", "b")
        ],
        return_exceptions=True,
    )
    assert sum(isinstance(value, ApplicationError) for value in outcomes) == 1
    used = "a" if outcomes[0] is None else "b"
    await assessment.store.consume_window(USER.owner, window.id, bank.revision, "test", used)
    changed = case("heldout", split="test", prompt="Changed protected question")
    await assessment.import_cases(
        USER,
        ImportCases(request_id="rotate", expected_revision=next_bank.revision, cases=(changed,)),
    )
    with pytest.raises(ApplicationError):
        await assessment.store.consume_window(USER.owner, window.id, bank.revision, "test", used)


async def test_observed_actor_tasks_cannot_be_relabelled_fresh_holdout(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = await file_run(agent, monkeypatch)
    bank = await assessment.bank(USER)
    protected = EvalCase(
        id="seen",
        family="seen",
        origin_group="seen",
        split="test",
        prompt=done.command.goal,
        kind="file",
        target_path="notes.md",
        expected_sha256=done.command.acceptance.sha256,
        source="human_seed",
    )
    with pytest.raises(ApplicationError) as error:
        await assessment.import_cases(
            USER,
            ImportCases(
                request_id="poison-test", expected_revision=bank.revision, cases=(protected,)
            ),
        )
    assert error.value.code == "protected_case_already_observed"
    assert (await assessment.bank(USER)).revision == bank.revision


def test_wilson_kappa_do_not_promote_small_or_degenerate_samples() -> None:
    assert wilson(0, 0) == (None, None)
    lower, upper = wilson(1, 1)
    assert lower is not None and lower < 0.21 and upper is not None and upper <= 1
    assert kappa(["pass"] * 30, ["pass"] * 30) is None
    assert kappa(["pass", "fail"], ["pass", "fail"]) == 1


async def test_high_confidence_self_judging_and_unknown_usage_are_not_trusted(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from auton.model.ports import ModelError

    done = await file_run(agent, monkeypatch)

    async def judge(request: ModelRequest) -> ModelResult:
        return result(
            request,
            json.dumps(
                {
                    "verdict": "pass",
                    "confidence": 1,
                    "evidence": json.loads(request.messages[-1].content or "{}")["evidence_ids"][
                        :1
                    ],
                    "reason": "I am certain.",
                }
            ),
        )

    monkeypatch.setattr(assessment.deps.models, "generate", judge)
    job = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="self-judge",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
            semantic=True,
        ),
    )
    assert job.report and job.report.judges[0].self_eval_bias
    assert job.report.judges[0].reported_confidence == 1
    assert job.report.semantic_verdict == "unknown" and job.report.outcome == "unknown"

    async def unknown(request: ModelRequest) -> ModelResult:
        raise ModelError("network_outcome_unknown", "No acknowledgement", dispatched=True)

    monkeypatch.setattr(assessment.deps.models, "generate", unknown)
    job = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="unknown-judge",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
            semantic=True,
        ),
    )
    assert job.report and job.report.evaluation_unknown_calls == 1
    assert job.report.evaluation_cost_microusd is None and job.report.judges[0].tokens is None
    summary = aggregate((job.report,))
    assert summary.evaluation_unknown_calls == 1 and summary.known_denominator == 0


async def test_fake_judge_small_perfect_meta_does_not_open_gate_and_train_growth_preserves_split(
    assessment: Assessment, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.assess.contracts import CalibrationCommand, JudgeObservation

    bank = await assessment.bank(USER)
    cases = (
        case(
            "meta-alpha",
            split="meta",
            prompt="Alpha independent question",
            human_answer="good",
            human_verdict="pass",
            critical=True,
        ),
        case(
            "meta-beta",
            split="meta",
            prompt="Beta separate question",
            human_answer="bad",
            human_verdict="fail",
            critical=True,
        ),
    )
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="meta-pack", expected_revision=bank.revision, cases=cases)
    )

    async def judge(
        principal: Principal,
        identity: str,
        prompt: str,
        answer: str,
        public: bool,
        evidence: tuple[str, ...],
        actor_models: tuple[str, ...],
        actor_fingerprints: tuple[str, ...],
        evidence_text: dict[str, str] | None = None,
    ) -> JudgeObservation:
        return JudgeObservation(
            request_id=identity,
            rubric_revision=assessment.config.rubric_revision,
            configuration_digest=assessment.config.digest,
            verdict="pass" if answer == "good" else "fail",
            reason="Synthetic unit fixture, not actual human calibration.",
            source="test",
            reported_model="fixture-judge",
            fingerprint="fixture-fingerprint",
            reported_confidence=1,
            dispatch_outcome="confirmed",
        )

    monkeypatch.setattr(assessment.judge, "evaluate", judge)
    window = await assessment.open_window(
        USER,
        BlindWindowCommand(
            request_id="meta-window",
            bank_revision=bank.revision,
            split="meta",
            purpose="calibration",
            candidate_revision=assessment.config.digest,
        ),
    )
    command_body = CalibrationCommand(
        request_id="calibrate", bank_revision=bank.revision, window_id=window.id
    )
    report = await assessment.calibrate(USER, command_body)
    assert report.agreement == 1 and report.kappa == 1 and report.samples == 2
    assert not report.passed and not report.source_qualified and report.families == 2
    assert report.wilson_lower is not None and report.wilson_lower < 0.8
    assert await assessment.calibrate(USER, command_body) == report
    next_bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="train-growth",
            expected_revision=bank.revision,
            cases=(case("separate-train"),),
        ),
    )
    assert (
        await assessment.store.split_digest(USER.owner, next_bank.revision, "meta")
        == report.meta_digest
    )
    with pytest.raises(ApplicationError):
        await assessment.open_window(
            USER,
            BlindWindowCommand(
                request_id="adaptive-after-train",
                bank_revision=next_bank.revision,
                split="meta",
                purpose="calibration",
                candidate_revision=assessment.config.digest,
            ),
        )
    rows = await assessment.deps.events.read(limit=1000)
    assert all(
        "Alpha independent question" not in row.event.canonical()
        and "Beta separate question" not in row.event.canonical()
        for row in rows
    )


async def test_correlated_numeric_rewrites_are_one_calibration_family(
    assessment: Assessment, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.assess.contracts import CalibrationCommand, JudgeObservation

    bank = await assessment.bank(USER)
    cases = tuple(
        case(
            f"meta-{index}",
            split="meta",
            prompt=f"Check question {index}",
            human_answer="good" if index % 2 else "bad",
            human_verdict="pass" if index % 2 else "fail",
            critical=index < 5,
        )
        for index in range(30)
    )
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="rewrites", expected_revision=bank.revision, cases=cases)
    )

    async def judge(
        principal: Principal,
        identity: str,
        prompt: str,
        answer: str,
        public: bool,
        evidence: tuple[str, ...],
        actor_models: tuple[str, ...],
        actor_fingerprints: tuple[str, ...],
        evidence_text: dict[str, str] | None = None,
    ) -> JudgeObservation:
        return JudgeObservation(
            request_id=identity,
            rubric_revision=assessment.config.rubric_revision,
            configuration_digest=assessment.config.digest,
            verdict="pass" if answer == "good" else "fail",
            reason="Synthetic unit fixture.",
            source="test",
            reported_model="fixture-judge",
            fingerprint="same-fixture",
            dispatch_outcome="confirmed",
        )

    monkeypatch.setattr(assessment.judge, "evaluate", judge)
    window = await assessment.open_window(
        USER,
        BlindWindowCommand(
            request_id="rewrite-window",
            bank_revision=bank.revision,
            split="meta",
            purpose="calibration",
            candidate_revision=assessment.config.digest,
        ),
    )
    report = await assessment.calibrate(
        USER,
        CalibrationCommand(
            request_id="rewrite-calibration", bank_revision=bank.revision, window_id=window.id
        ),
    )
    assert report.samples == 30 and report.known == 30 and report.families == 1
    assert not report.passed and "insufficient_independent_families" in report.reasons


async def test_assessment_waiter_cancellation_does_not_discard_judge_result(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.assess.contracts import JudgeObservation
    from auton.assess.store import key

    done = await file_run(agent, monkeypatch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def judge(
        principal: Principal,
        identity: str,
        prompt: str,
        answer: str,
        public: bool,
        evidence: tuple[str, ...],
        actor_models: tuple[str, ...],
        actor_fingerprints: tuple[str, ...],
        evidence_text: dict[str, str] | None = None,
    ) -> JudgeObservation:
        entered.set()
        await release.wait()
        return JudgeObservation(
            request_id=identity,
            rubric_revision=assessment.config.rubric_revision,
            configuration_digest=assessment.config.digest,
            verdict="unknown",
            reason="Fixture.",
            source="test",
        )

    monkeypatch.setattr(assessment.judge, "evaluate", judge)
    body = EvaluateCommand(
        request_id="cancel-http",
        project_id="project",
        run_id=done.id,
        expected_version=done.version,
        semantic=True,
    )
    task = asyncio.create_task(assessment.evaluate(USER, body))
    await asyncio.wait_for(entered.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    await asyncio.wait_for(asyncio.gather(*list(assessment.active.values())), 5)
    job = await assessment.job(USER, key(USER.owner, "run:" + body.request_id))
    assert job.status == "complete" and job.report


async def test_store_restart_schema_guard_and_report_integrity(assessment: Assessment) -> None:
    import stat

    from auton.assess.contracts import SeedCommand

    bank = await assessment.bank(USER)
    command_body = SeedCommand(request_id="seeds", expected_revision=bank.revision)
    seeded = await assessment.seed(USER, command_body)
    assert seeded.counts["train"] == 2 and seeded.counts["test"] == 0 and seeded.counts["meta"] == 0
    assert await assessment.seed(USER, command_body) == seeded
    await assessment.close()
    assert (
        stat.S_IMODE((assessment.config.directory / "evaluation.sqlite3").stat().st_mode) == 0o600
    )
    replacement = AssessFactory().create(assessment.config, assessment.deps)
    await replacement.start()
    try:
        assert await replacement.bank(USER) == seeded
        assert len(await replacement.train_cases(USER.model_copy(update={"role": "training"}))) == 2
    finally:
        await replacement.close()


async def test_full_blind_batch_is_frozen_and_cannot_cherry_pick(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.assess.contracts import BatchEvaluation, CaseRunBinding
    from auton.assess.service import candidate_revision

    bank = await assessment.bank(USER)
    alpha = "Write hello followed by a newline to notes.md. Alpha experiment."
    beta = "Write hello followed by a newline to notes.md. Beta experiment."
    cases = tuple(
        EvalCase(
            id=identity,
            family=identity,
            origin_group=identity,
            split="test",
            prompt=goal,
            kind="file",
            target_path="notes.md",
            expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
            source="test_fixture",
        )
        for identity, goal in (("alpha", alpha), ("beta", beta))
    )
    bank = await assessment.import_cases(
        USER, ImportCases(request_id="batch-pack", expected_revision=bank.revision, cases=cases)
    )
    first = await file_run(agent, monkeypatch, "alpha-run", alpha)
    second = await file_run(agent, monkeypatch, "beta-run", beta)
    assert candidate_revision(first) == candidate_revision(second)
    window = await assessment.open_window(
        USER,
        BlindWindowCommand(
            request_id="batch-window",
            bank_revision=bank.revision,
            split="test",
            purpose="release",
            candidate_revision=candidate_revision(first),
        ),
    )
    bindings = (
        CaseRunBinding(case_id="alpha", run_id=first.id, expected_version=first.version),
        CaseRunBinding(case_id="beta", run_id=second.id, expected_version=second.version),
    )
    body = BatchEvaluation(
        request_id="full-batch",
        project_id="project",
        bank_revision=bank.revision,
        window_id=window.id,
        runs=bindings,
    )
    with pytest.raises(ApplicationError):
        await assessment.batch(
            USER, body.model_copy(update={"request_id": "cherry-pick", "runs": bindings[:1]})
        )
    assert await assessment.store.window_usage(USER.owner, window.id) == 0
    result = await assessment.batch(USER, body)
    assert result.complete and result.expected_cases == 2 and result.aggregate.passed == 2
    assert all(not report.quality_release_eligible for report in result.reports)
    assert await assessment.batch(USER, body) == result
    assert await assessment.store.window_usage(USER.owner, window.id) == 1
    with pytest.raises(ApplicationError):
        await assessment.batch(USER, body.model_copy(update={"request_id": "adaptive-retest"}))
    windows = await assessment.windows(USER)
    assert windows[0].used == 1 and windows[0].current


async def test_case_digest_corruption_and_unknown_schema_fail_closed(
    assessment: Assessment,
) -> None:
    import apsw

    from auton.assess.contracts import SeedCommand

    bank = await assessment.bank(USER)
    await assessment.seed(
        USER, SeedCommand(request_id="persist-seed", expected_revision=bank.revision)
    )
    await assessment.close()
    path = assessment.config.directory / "evaluation.sqlite3"
    db = apsw.Connection(str(path))
    db.execute("UPDATE documents SET document='{}' WHERE kind='case'")
    db.close()
    corrupt = AssessFactory().create(assessment.config, assessment.deps)
    await corrupt.start()
    try:
        with pytest.raises(ApplicationError) as error:
            await corrupt.bank(USER)
        assert error.value.code == "evaluation_document_corrupt"
    finally:
        await corrupt.close()
    db = apsw.Connection(str(path))
    db.pragma("user_version", 999)
    db.close()
    incompatible = AssessFactory().create(assessment.config, assessment.deps)
    try:
        with pytest.raises(ApplicationError) as error:
            await incompatible.start()
        assert error.value.code == "eval_schema_incompatible"
    finally:
        await incompatible.close()


async def test_human_preference_retains_provenance_without_overruling_checker(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.server.feedback import FeedbackCommand, FeedbackFactory

    done = await file_run(agent, monkeypatch)
    feedback = FeedbackFactory().create(agent, agent.deps.events, agent.deps.runtime)
    receipt = await feedback.submit(
        USER,
        done.id,
        FeedbackCommand(
            request_id="human-dislikes-output",
            expected_goal_revision=done.goal_revision,
            checkpoint_version=done.version,
            rating="unhelpful",
        ),
    )
    job = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="with-human-preference",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert job.report and job.report.outcome == "pass"
    labels = [signal for signal in job.report.signals if signal.source == "human"]
    assert len(labels) == 1 and labels[0].verdict == "unknown"
    assert labels[0].evidence == (receipt.event_id,)
    assert "unhelpful" in labels[0].reason and not job.report.quality_release_eligible


async def test_http_protected_gold_and_judge_prompts_only_reach_private_journal(
    tmp_path: Path,
) -> None:
    import stat
    from datetime import UTC, datetime
    from uuid import uuid4

    from fastapi.testclient import TestClient

    from auton.agent.contracts import AgentConfig
    from auton.assess.rubric import RUBRIC
    from auton.bootstrap.app import ApplicationFactory
    from auton.bootstrap.config import ApplicationConfig
    from auton.delegation.contracts import DelegationConfig
    from auton.experience.contracts import ExperienceConfig
    from auton.genome.contracts import GenomeConfig
    from auton.judgment.config import JudgmentConfig
    from auton.kernel.ports import RuntimeDependencies
    from auton.server.identity import ServerSettings
    from auton.tools.config import ToolConfig

    config = ApplicationConfig(
        profile="test",
        kernel=KernelConfig(data_directory=tmp_path / "events"),
        server=ServerSettings(directory=tmp_path / "server"),
        genome=GenomeConfig(directory=tmp_path / "assets"),
        agent=AgentConfig(directory=str(tmp_path / "agent")),
        tools=ToolConfig(directory=tmp_path / "tools"),
        experience=ExperienceConfig(directory=tmp_path / "experience"),
        models=ModelConfig(backend="mock", fixture_scenario="agent_acceptance"),
        judgment=JudgmentConfig(backend="mock"),
        datasets=DatasetConfig(directory=tmp_path / "datasets"),
        decision_review=DecisionReviewConfig(directory=tmp_path / "decision-review"),
        evolve=EvolutionConfig(directory=tmp_path / "evolve"),
        delegation=DelegationConfig(directory=tmp_path / "delegation"),
        assess=AssessConfig(directory=tmp_path / "assess", judge_model="fixture-model"),
        allowed_origins=("http://testserver",),
    )
    deps = RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))
    private_prompt = "UNPUBLISHED_META_PROMPT_strictly_private"
    private_answer = "UNPUBLISHED_GOLD_ANSWER_strictly_private"
    headers = {"Origin": "http://testserver", "X-Auton-Client": "web"}
    with TestClient(ApplicationFactory().create(config, deps), headers=headers) as client:
        client.get("/api/v1/bootstrap")
        state = client.get("/api/v1/assessment/status").json()
        bank = client.get("/api/v1/assessment/bank").json()
        body = {
            "request_id": "http-meta-import",
            "expected_revision": bank["revision"],
            "cases": [
                {
                    "id": "private-gold",
                    "family": "private-family",
                    "origin_group": "private-origin",
                    "split": "meta",
                    "kind": "research",
                    "prompt": private_prompt,
                    "human_answer": private_answer,
                    "human_verdict": "pass",
                    "source": "test_fixture",
                    "data_domain": "public",
                }
            ],
        }
        assert (
            client.post("/api/v1/assessment/bank", json={**body, "role": "training"}).status_code
            == 422
        )
        imported = client.post("/api/v1/assessment/bank", json=body)
        assert imported.status_code == 200, imported.text
        assert private_prompt not in imported.text and private_answer not in imported.text
        revision = imported.json()["revision"]
        assert client.get("/api/v1/assessment/train-cases").json() == []
        window = client.post(
            "/api/v1/assessment/windows",
            json={
                "request_id": "http-meta-window",
                "bank_revision": revision,
                "split": "meta",
                "purpose": "calibration",
                "candidate_revision": state["config_digest"],
            },
        )
        assert window.status_code == 200, window.text
        command = {
            "request_id": "http-calibration",
            "bank_revision": revision,
            "window_id": window.json()["id"],
            "confirm_public": True,
            "repeats": 2,
        }
        calibration = client.post("/api/v1/assessment/calibrations", json=command)
        assert calibration.status_code == 200, calibration.text
        assert not calibration.json()["passed"] and calibration.json()["judge_calls"] == 2
        assert (
            client.post("/api/v1/assessment/calibrations", json=command).json()
            == calibration.json()
        )
        assert client.get("/api/v1/assessment/windows").json()[0]["used"] == 1
        client.cookies.clear()
        client.get("/api/v1/bootstrap")
        assert not client.get("/api/v1/assessment/bank").json()["cases"]
        assert client.get("/api/v1/assessment/calibrations").json() == []
        assert client.get("/api/v1/assessment/jobs/" + calibration.json()["id"]).status_code == 404

    for directory, expect_private in [
        (tmp_path / "events", False),
        (tmp_path / "assess" / "judge-journal", True),
    ]:
        events = EventLogFactory().create(KernelConfig(data_directory=directory))
        await events.start()
        try:
            rows = await events.read(limit=1000)
            text = "\n".join(row.event.model_dump_json() for row in rows)
            assert (private_prompt in text) is expect_private
            assert (private_answer in text) is expect_private
            assert (RUBRIC.splitlines()[0] in text) is expect_private
        finally:
            await events.close()
        for path in directory.glob("*.sqlite3"):
            assert stat.S_IMODE(path.stat().st_mode) == 0o600


async def test_changed_asset_configuration_cannot_reuse_one_blind_candidate(
    assessment: Assessment, agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import cast

    from auton.assess.service import candidate_revision
    from auton.genome.contracts import Asset
    from auton.genome.ports import GenomePort

    bank = await assessment.bank(USER)
    goal = "Write hello followed by a newline to notes.md. Fixed blind input."
    bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="asset-scope-case",
            expected_revision=bank.revision,
            cases=(
                EvalCase(
                    id="fixed",
                    family="fixed-family",
                    origin_group="fixed-origin",
                    split="test",
                    prompt=goal,
                    kind="file",
                    target_path="notes.md",
                    expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
                    source="test_fixture",
                ),
            ),
        ),
    )
    first = await file_run(agent, monkeypatch, "configuration-one", goal)
    assert first.input_asset_snapshot_id
    assets = cast(GenomePort, agent.deps.assets)
    view = await assets.view(USER, "project")
    proposed = await assets.propose(
        USER,
        "project",
        Asset(
            id="changed-input",
            name="Changed input",
            kind="document",
            content="A new input configuration for the same model.",
            origin="user_explicit",
            source="assessment fixture",
        ),
        view.candidates_revision,
    )
    assert proposed.revision and proposed.candidates_revision
    await assets.promote(
        USER, "project", "changed-input", proposed.revision, proposed.candidates_revision
    )
    second = await file_run(agent, monkeypatch, "configuration-two", goal)
    assert first.input_asset_snapshot_id != second.input_asset_snapshot_id
    assert candidate_revision(first) != candidate_revision(second)
    window = await assessment.open_window(
        USER,
        BlindWindowCommand(
            request_id="configuration-window",
            bank_revision=bank.revision,
            split="test",
            purpose="release",
            candidate_revision=candidate_revision(first),
        ),
    )
    with pytest.raises(ApplicationError) as mismatch:
        await assessment.evaluate(
            USER,
            EvaluateCommand(
                request_id="wrong-input-candidate",
                project_id="project",
                run_id=second.id,
                expected_version=second.version,
                bank_revision=bank.revision,
                case_id="fixed",
                window_id=window.id,
            ),
        )
    assert mismatch.value.code == "assessment_candidate_changed"
    assert (await assessment.windows(USER))[0].used == 0


async def test_optimizer_task_capability_cannot_export_development_to_generation_or_meta(
    assessment: Assessment,
) -> None:
    from typing import cast

    from auton.assess.contracts import Split

    bank = await assessment.bank(USER)
    cases = []
    for split, text in (
        ("train", "Training example"),
        ("development", "Development example"),
        ("meta", "Protected judge gold"),
    ):
        cases.append(
            EvalCase(
                id=split,
                family=split,
                origin_group=split,
                split=cast(Split, split),
                prompt=text,
                kind="file",
                target_path="notes.md",
                expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
                source="test_fixture",
                human_answer="PRIVATE_META_ANSWER" if split == "meta" else None,
                human_verdict="pass" if split == "meta" else "unknown",
            )
        )
    bank = await assessment.import_cases(
        USER,
        ImportCases(
            request_id="optimizer-capabilities", expected_revision=bank.revision, cases=tuple(cases)
        ),
    )
    generation = USER.model_copy(update={"role": "evolution"})
    train = await assessment.optimization_task(generation, "train", bank.revision, "train")
    assert train.split == "train" and "human_answer" not in train.model_dump_json()
    assert (
        await assessment.optimization_task(USER, "development", bank.revision, "development")
    ).split == "development"
    for principal, identity, purpose in (
        (generation, "development", "development"),
        (generation, "meta", "train"),
        (USER, "meta", "development"),
    ):
        with pytest.raises(ApplicationError) as denied:
            await assessment.optimization_task(principal, identity, bank.revision, purpose)  # type: ignore[arg-type]
        assert denied.value.status == 403
