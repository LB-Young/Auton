import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from test_agent import agent as agent
from test_assessment import assessment as assessment
from test_assessment import file_run
from test_context import USER
from test_context import context as context
from test_delegation import supervisor as supervisor

from auton.agent.service import AgentRuntime
from auton.assess.contracts import EvaluateCommand
from auton.assess.service import Assessment
from auton.decision_review.contracts import (
    DecisionReviewConfig,
    HumanRevision,
    ReviewCommand,
    ReviewRecord,
)
from auton.decision_review.dependencies import ReviewDependencies
from auton.decision_review.factory import DecisionReviewFactory
from auton.decision_review.reviewer import stage_input
from auton.decision_review.service import DecisionReview
from auton.delegation.service import Delegation
from auton.genome.ports import GenomePort
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult, ModelUsage


@pytest.fixture
async def reviewer(
    assessment: Assessment, agent: AgentRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[DecisionReview]:
    # Assessment already owns a separate private gateway/journal in this fixture.
    models = assessment.deps.models

    async def model(request: ModelRequest) -> ModelResult:
        value = json.loads(request.messages[-1].content or "")
        refs = [f["id"] for f in value["evidence"]]
        if "later_evidence" not in value:
            parsed = {
                "verdict": "supported",
                "knowledge_at_time": "sufficient",
                "evidence_refs": refs,
                "explanation": "Original constraints support this choice.",
            }
        else:
            parsed = {
                "verdict": "beneficial",
                "causal_support": "controlled",
                "efficiency": "beneficial",
                "evidence_refs": refs,
                "explanation": "Optimistic reviewer claims cannot bypass independent attribution.",
            }
        return ModelResult(
            request_id=request.request_id,
            model_id=request.model_id,
            reported_model="reviewer-fixture",
            system_fingerprint="reviewer-fp",
            content=json.dumps(parsed),
            finish_reason="stop",
            usage=ModelUsage(input_tokens=10, output_tokens=10),
            source="test",
            latency_ms=0,
        )

    monkeypatch.setattr(models, "generate", model)
    # Use the same public trajectory module as production, with isolated projection.
    from auton.experience.contracts import ExperienceConfig
    from auton.experience.factory import ExperienceFactory
    from auton.experience.service import ExperienceDependencies

    experience = ExperienceFactory().create(
        ExperienceConfig(directory=tmp_path / "experience"),
        ExperienceDependencies(
            agent.deps.events, agent, agent.deps.assets, agent.deps.context, agent.deps.runtime
        ),
    )
    await experience.start()
    deps = ReviewDependencies(
        agent,
        assessment,
        experience,
        cast(GenomePort, agent.deps.assets),
        models,
        agent.deps.events,
        agent.deps.runtime,
        True,
    )
    service = DecisionReviewFactory().create(
        DecisionReviewConfig(directory=tmp_path / "review", reviewer_model="fixture-model"), deps
    )
    assert isinstance(service, DecisionReview)
    await service.start()
    yield service
    await service.close()
    await experience.close()


async def test_actual_shadow_answer_two_stage_temporal_isolation_and_human_exclusion(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    done = await file_run(agent, monkeypatch)
    report = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="decision-evidence",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert report.report
    decision = done.judgments[0]
    command = ReviewCommand(
        request_id="two-stage",
        project_id="project",
        run_id=done.id,
        expected_run_version=done.version,
        judgment_id=decision.request_id,
        question_id=decision.answers[0].question_id,
        assessment_report_id=report.report.id,
    )
    result = await reviewer.review(USER, command)
    assert result.status == "complete" and result.stage_a and result.stage_b, (
        result.status,
        result.stage_a.reason if result.stage_a else None,
        result.stage_b.reason if result.stage_b else None,
    )
    assert result.stage_a.verdict
    assert result.verdict == "HOLD" and not result.positive_training_eligible
    assert "shadow_answer_not_eligible" in result.reason_codes
    a = stage_input(result.subject, "before", None)
    b = stage_input(result.subject, "after", result.stage_a)
    assert (
        "later_evidence" not in a
        and "adopted" not in a
        and "independent_assessment_passed" not in a
    )
    assert b["frozen_stage_a"] == result.stage_a.verdict.model_dump(mode="json")
    assert "later_evidence" in b
    assert await reviewer.review(USER, command) == result
    assert await reviewer.eligible(USER, "project") == ()
    assert not (await reviewer.calibrations(USER))[0].eligible
    from auton.decision_review.contracts import MetaCaseCommand

    meta = MetaCaseCommand(
        request_id="human-meta",
        review_id=result.id,
        expected_review_version=result.version,
        family="fixture-family",
        origin_group="fixture-origin",
        gold="HOLD",
        explanation="The original answer was not adopted and cannot receive success credit.",
        evidence_refs=(result.subject.before_evidence[0].id,),
        confirm_independent_human_annotation=True,
    )
    calibration = await reviewer.annotate_meta(USER, meta)
    assert not calibration.eligible and calibration.independent_families == 0
    assert (await reviewer.protected_inputs(USER))[0].run_id == done.id
    correction = HumanRevision(
        request_id="wrong",
        expected_version=result.version,
        proposed_verdict="DROP",
        reason="User observed an unsuitable selection despite later success.",
        evidence_refs=("invented",),
    )
    with pytest.raises(ApplicationError) as forged:
        await reviewer.revise(USER, result.id, correction)
    assert forged.value.code == "decision_review_forged_reference"
    correction = correction.model_copy(
        update={"evidence_refs": (result.subject.before_evidence[0].id,)}
    )
    fixed = await reviewer.revise(USER, result.id, correction)
    assert fixed.verdict == "DROP" and not fixed.positive_training_eligible
    assert await reviewer.revise(USER, result.id, correction) == fixed
    revised_meta = meta.model_copy(
        update={
            "request_id": "corrected-human-meta",
            "expected_review_version": fixed.version,
            "gold": "DROP",
        }
    )
    with pytest.raises(ApplicationError) as moved:
        await reviewer.annotate_meta(
            USER, revised_meta.model_copy(update={"family": "another-family"})
        )
    assert moved.value.code == "decision_meta_family_locked"
    assert not (await reviewer.annotate_meta(USER, revised_meta)).eligible
    with pytest.raises(ApplicationError):
        await reviewer.get(USER.model_copy(update={"owner": "other"}), result.id)


async def base_record(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> ReviewRecord:
    done = await file_run(agent, monkeypatch)
    report = await assessment.evaluate(
        USER,
        EvaluateCommand(
            request_id="base-review-evidence",
            project_id="project",
            run_id=done.id,
            expected_version=done.version,
        ),
    )
    assert report.report
    decision = done.judgments[0]
    return await reviewer.review(
        USER,
        ReviewCommand(
            request_id="base-review",
            project_id="project",
            run_id=done.id,
            expected_run_version=done.version,
            judgment_id=decision.request_id,
            question_id=decision.answers[0].question_id,
            assessment_report_id=report.report.id,
        ),
    )


async def test_policy_does_not_launder_salvaged_error_or_blame_environment(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auton.decision_review.contracts import Contribution, Reasonableness
    from auton.decision_review.policy import AttributionPolicyFactory

    original = await base_record(reviewer, assessment, agent, monkeypatch)
    assert original.stage_a and original.stage_b
    # Pure policy fixtures: these flags never come from client-supplied source DTOs.
    candidate = original.model_copy(
        update={
            "subject": original.subject.model_copy(
                update={
                    "source": "runtime",
                    "blockers": (),
                    "decision": original.subject.decision.model_copy(update={"adopted": True}),
                    "assessment_passed": True,
                    "assessment_current": True,
                    "causal_link_verified": True,
                    "efficiency_comparison_verified": True,
                }
            ),
            "stage_a": original.stage_a.model_copy(
                update={
                    "source": "runtime",
                    "fingerprint": "fixture-proof",
                    "verdict": Reasonableness(
                        verdict="supported",
                        knowledge_at_time="sufficient",
                        evidence_refs=("before",),
                        explanation="Pure fixture original evidence.",
                    ),
                }
            ),
            "stage_b": original.stage_b.model_copy(
                update={
                    "source": "runtime",
                    "fingerprint": "fixture-proof",
                    "verdict": Contribution(
                        verdict="beneficial",
                        causal_support="controlled",
                        efficiency="beneficial",
                        evidence_refs=("after",),
                        explanation="Pure fixture controlled effect.",
                    ),
                }
            ),
        }
    )
    policy = AttributionPolicyFactory().create()
    assert policy.assess(candidate, True)[0] == "KEEP"
    assert policy.assess(candidate, False)[0] == "HOLD"
    assert candidate.stage_a and isinstance(candidate.stage_a.verdict, Reasonableness)
    assert candidate.stage_b and isinstance(candidate.stage_b.verdict, Contribution)
    salvaged = candidate.model_copy(
        update={
            "stage_a": candidate.stage_a.model_copy(
                update={
                    "verdict": candidate.stage_a.verdict.model_copy(
                        update={"verdict": "unreasonable"}
                    )
                }
            ),
            "stage_b": candidate.stage_b.model_copy(
                update={
                    "verdict": candidate.stage_b.verdict.model_copy(
                        update={
                            "verdict": "harmful",
                            "causal_support": "corrective_chain",
                            "efficiency": "avoidable_detour",
                        }
                    )
                }
            ),
        }
    )
    assert salvaged.subject.assessment_passed and policy.assess(salvaged, True)[0] == "DROP"
    environmental = candidate.model_copy(
        update={
            "subject": candidate.subject.model_copy(
                update={"environment_failure": True, "assessment_passed": False}
            )
        }
    )
    assert policy.assess(environmental, True)[0] == "HOLD"
    changed = candidate.model_copy(
        update={"subject": candidate.subject.model_copy(update={"goal_changed": True})}
    )
    assert policy.assess(changed, True)[0] == "HOLD"
    interaction = candidate.model_copy(
        update={"subject": candidate.subject.model_copy(update={"interaction_group": "pair"})}
    )
    assert policy.assess(interaction, True)[0] == "HOLD"
    assert policy.assess(candidate, True, True)[0] == "HOLD"


async def test_independent_human_meta_requires_class_coverage_and_low_contamination_upper(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from auton.decision_review.calibration import calibrate
    from auton.decision_review.contracts import MetaCase, MetaCaseCommand, ReviewRecord, Verdict
    from auton.decision_review.policy import reviewer_signature

    base = await base_record(reviewer, assessment, agent, monkeypatch)
    assert base.stage_a and base.stage_b
    base = base.model_copy(
        update={
            "stage_a": base.stage_a.model_copy(
                update={"source": "runtime", "fingerprint": "fixture-meta"}
            ),
            "stage_b": base.stage_b.model_copy(
                update={"source": "runtime", "fingerprint": "fixture-meta"}
            ),
        }
    )
    signature = reviewer_signature(base)
    assert signature
    cases = []
    records: dict[str, ReviewRecord] = {}
    # This is an algorithmic synthetic test, not production calibration evidence.
    for i in range(441):
        token = "".join(chr(97 + (i // (26**p)) % 26) for p in range(3))
        identity = hashlib.sha256(token.encode()).hexdigest()
        label: Verdict = "KEEP" if i < 381 else "DROP" if i < 411 else "HOLD"
        subject = base.subject.model_copy(
            update={
                "source": "runtime",
                "source_digest": identity,
                "request": base.subject.request.model_copy(
                    update={"state": "Independent fixture " + token}
                ),
            }
        )
        record = base.model_copy(
            update={"id": identity, "subject": subject, "proposed_verdict": label}
        )
        records[identity] = record
        cases.append(
            MetaCase(
                id=identity,
                command=MetaCaseCommand(
                    request_id="meta-" + token,
                    review_id=identity,
                    expected_review_version=record.version,
                    family=token,
                    origin_group=token,
                    gold=label,
                    explanation="Synthetic algorithmic label, not human production evidence.",
                    evidence_refs=("fixture",),
                    confirm_independent_human_annotation=True,
                ),
                reviewer_signature=signature,
                subject_digest=identity,
                source="runtime",
                recommended=label,
                observed_at_version=record.version,
            )
        )
    small = calibrate(reviewer.config, signature, tuple(cases[:100]), records)
    assert not small.eligible and "human_meta_class_coverage_missing" in small.reasons
    enough = calibrate(reviewer.config, signature, tuple(cases), records)
    assert (
        enough.eligible
        and enough.keep_contamination_upper
        and enough.keep_contamination_upper < 0.01
    )
    poisoned = list(cases)
    poisoned[0] = cases[0].model_copy(
        update={"command": cases[0].command.model_copy(update={"gold": "DROP"})}
    )
    assert not calibrate(reviewer.config, signature, tuple(poisoned), records).eligible
    correlated = tuple(
        c.model_copy(
            update={"command": c.command.model_copy(update={"origin_group": "one-source"})}
        )
        for c in cases
    )
    assert not calibrate(reviewer.config, signature, correlated, records).eligible


async def test_late_feedback_invalidates_old_review_without_rewriting_original_state(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auton.server.feedback import FeedbackCommand, FeedbackFactory

    original = await base_record(reviewer, assessment, agent, monkeypatch)
    feedback = FeedbackFactory().create(agent, agent.deps.events, agent.deps.runtime)
    receipt = await feedback.submit(
        USER,
        original.command.run_id,
        FeedbackCommand(
            request_id="late-review-correction",
            expected_goal_revision=1,
            checkpoint_version=original.command.expected_run_version,
            rating="unhelpful",
            note="The decision needed another constraint; do not treat final success as proof.",
        ),
    )
    stale = await reviewer.get(USER, original.id)
    assert not stale.evidence_current and not stale.positive_training_eligible
    assert original.subject.request == stale.subject.request
    newer = await reviewer.review(
        USER, original.command.model_copy(update={"request_id": "corrected-source"})
    )
    assert newer.id != original.id and newer.subject.request == original.subject.request
    before = stage_input(newer.subject, "before", None)
    after = stage_input(newer.subject, "after", newer.stage_a)
    assert receipt.event_id not in json.dumps(before)
    assert receipt.event_id in json.dumps(after)
    assert newer.verdict == "HOLD" and not newer.positive_training_eligible


async def test_unknown_review_charge_is_preserved_and_not_retried(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from auton.model.ports import ModelError

    original = await base_record(reviewer, assessment, agent, monkeypatch)
    calls = 0

    async def uncertain(request: ModelRequest) -> ModelResult:
        nonlocal calls
        calls += 1
        raise ModelError("provider_timeout", "Result unknown after dispatch", dispatched=True)

    monkeypatch.setattr(reviewer.deps.models, "generate", uncertain)
    command = original.command.model_copy(update={"request_id": "unknown-charge"})
    blocked = await reviewer.review(USER, command)
    assert blocked.status == "blocked" and blocked.stage_a and not blocked.stage_b
    assert blocked.stage_a.cost_microusd is None and blocked.stage_a.tokens is None
    assert blocked.stage_a.dispatch == "unknown"
    assert await reviewer.review(USER, command) == blocked
    assert calls == 1


async def test_stage_a_commit_ack_loss_resumes_only_stage_b(
    reviewer: DecisionReview,
    assessment: Assessment,
    agent: AgentRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import Any

    from auton.decision_review.contracts import StageReceipt

    original = await base_record(reviewer, assessment, agent, monkeypatch)
    calls: list[str] = []
    review = reviewer.reviewer.review

    async def counted(*args: Any, **kwargs: Any) -> StageReceipt:
        calls.append(args[3])
        return await review(*args, **kwargs)

    put = reviewer.store.put
    lost = False

    async def put_then_lose(*args: Any, **kwargs: Any) -> None:
        nonlocal lost
        await put(*args, **kwargs)
        value = args[3]
        if not lost and args[0] == "review" and value.get("stage_a") and not value.get("stage_b"):
            lost = True
            raise ApplicationError(503, "fixture_review_ack_lost", "Stage A was committed")

    monkeypatch.setattr(reviewer.reviewer, "review", counted)
    monkeypatch.setattr(reviewer.store, "put", put_then_lose)
    command = original.command.model_copy(update={"request_id": "lost-stage-a"})
    with pytest.raises(ApplicationError) as failed:
        await reviewer.review(USER, command)
    assert failed.value.code == "fixture_review_ack_lost"
    completed = await reviewer.review(USER, command)
    assert completed.status == "complete" and calls == ["before", "after"]


@pytest.mark.usefixtures("supervisor")
async def test_real_supervisor_dag_marks_child_as_interaction_not_independent_success(
    reviewer: DecisionReview, supervisor: Delegation, agent: AgentRuntime
) -> None:
    from dataclasses import replace

    from test_delegation import control, plan

    deps = replace(reviewer.deps, delegation=supervisor)
    reviewer.deps = deps
    reviewer.reader.deps = deps
    parent = await supervisor.create(USER, plan())
    await control(supervisor, parent, "start")
    import asyncio

    async with asyncio.timeout(10):
        while True:
            parent = await supervisor.get(USER, parent.id)
            if any(c.status == "waiting_approval" for c in parent.children):
                break
            assert parent.status != "blocked", parent.reason
            await asyncio.sleep(0.02)
    run_id = next(c.run_id for c in parent.children if c.run_id)
    assert run_id
    run = await agent.get(USER, run_id)
    decision = run.judgments[0]
    record = await reviewer.review(
        USER,
        ReviewCommand(
            request_id="dag-review",
            project_id="project",
            run_id=run.id,
            expected_run_version=run.version,
            judgment_id=decision.request_id,
            question_id=decision.answers[0].question_id,
        ),
    )
    assert record.subject.interaction_group == parent.id
    assert any(f.kind == "delegation_dag" for f in record.subject.after_evidence)
    assert record.verdict == "HOLD" and not record.positive_training_eligible
