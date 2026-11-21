"""Decision workflow engineering tests. Fixture training bytes never certify real quality."""

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from test_context import USER
from test_training import FixtureBackend, plan_job, wait_job
from test_training import agent as agent
from test_training import assessment as assessment
from test_training import context as context
from test_training import datasets as datasets
from test_training import evolution as evolution
from test_training import reviewer as reviewer
from test_training import supervisor as supervisor
from test_training import training as training

from auton.datasets.service import Datasets
from auton.kernel.ports import ApplicationError
from auton.training.contracts import ENCODER_CHOICE_TEMPLATE, DecisionTrainingConfig
from auton.training.decision import DecisionTraining
from auton.training.decision_contracts import DecisionEvaluationCommand, ShadowPrediction
from auton.training.decision_data import decision_record
from auton.training.decision_evaluation import (
    DecisionEvaluationDependencies,
    ShadowEvaluatorFactory,
)
from auton.training.decision_factory import DecisionTrainingFactory
from auton.training.decision_metrics import summarize
from auton.training.decision_worker import encode_choice
from auton.training.service import ExecutorTraining


def record() -> dict[str, Any]:
    return {
        "id": "e" * 64,
        "kind": "decision",
        "input": {
            "state": "用户要求只读检索，不允许写入文件。",
            "question": {
                "id": "tools",
                "point": "tool_domain",
                "type": "choice",
                "revision": "v1",
                "instructions": "Select the permitted tool domain.",
                "options": [
                    {"id": "read", "description": "Read only"},
                    {"id": "write", "description": "Write files"},
                ],
            },
        },
        "target": {"question_id": "tools", "type": "choice", "selected_id": "read"},
    }


def test_typed_encoder_labels_survive_option_reordering_and_reject_future_fields() -> None:
    value = record()
    canonical = decision_record(value)
    reordered = encode_choice(value, [1, 0])
    assert canonical["selected_id"] == reordered["gold"] == "read"
    assert reordered["label"] == 1 and reordered["options"][1] == "read"
    assert all('"selected_id"' not in text for text in reordered["texts"])
    assert "Write files" in reordered["texts"][0]
    with pytest.raises(ValueError, match="decision_input_schema"):
        decision_record({**value, "input": {**value["input"], "future_success": True}})
    with pytest.raises(ValueError, match="decision_unknown_option"):
        decision_record({**value, "target": {**value["target"], "selected_id": "unknown"}})
    with pytest.raises(ValueError, match="invalid_option_permutation"):
        encode_choice(value, [0, 0])


def test_metrics_cannot_pass_by_abstaining_or_hiding_rare_class_errors() -> None:
    rows = [
        {
            "options": ["read", "write"],
            "probabilities": {"read": 0.6, "write": 0.4},
            "gold": "read",
            "selected_id": None,
            "point": "tool_domain",
            "group_id": "one",
        }
    ]
    result = summarize(rows)
    assert (
        result["coverage"] == 0 and result["accuracy"] == 0 and result["selective_accuracy"] is None
    )
    assert result["critical_labeled_count"] == 0 and result["severe_errors"] is None
    assert result["label_basis"] == "qualified_KEEP_teacher_targets_not_independent_gold"
    with pytest.raises(ValueError, match="evaluation_probability_schema"):
        summarize([{**rows[0], "probabilities": {"read": float("nan"), "write": 0.4}}])
    repeated = summarize([rows[0], rows[0]])
    assert repeated["count"] == 2 and repeated["independent_groups"] == 1


def test_shadow_probabilities_are_validated_and_never_adopted() -> None:
    value: dict[str, Any] = {
        "sample_id": "a" * 64,
        "point": "tool_domain",
        "option_ids": ["read", "write"],
        "probabilities": {"read": 0.8, "write": 0.2},
        "selected_id": "read",
        "teacher_selected_id": "read",
        "observed_state_digest": "b" * 64,
    }
    replay = ShadowEvaluatorFactory().create().evaluate([value])
    assert not replay.predictions[0].adopted and not replay.agent_benefit_verified
    assert replay.source == "historical_validation_not_live_shadow"
    with pytest.raises(ValidationError):
        ShadowPrediction.model_validate({**value, "adopted": True})
    with pytest.raises(ValidationError):
        ShadowPrediction.model_validate({**value, "probabilities": {"write": 1.0}})


@pytest.fixture
async def decision_training(
    training: tuple[ExecutorTraining, FixtureBackend],
    datasets: Datasets,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[DecisionTraining, FixtureBackend]]:
    original, _ = training
    base = original.config.base_models[0].model_copy(
        update={
            "architecture": "encoder_choice",
            "template_sha256": hashlib.sha256(ENCODER_CHOICE_TEMPLATE.encode()).hexdigest(),
        }
    )
    config = DecisionTrainingConfig.model_validate(
        {
            **original.config.model_dump(),
            "directory": tmp_path / "decision-training",
            "workload": "decision",
            "base_models": (base,),
        }
    )
    service = DecisionTrainingFactory().create(
        config,
        original.deps,
        DecisionEvaluationDependencies(datasets.deps.agent, datasets.deps.assess),
    )
    assert isinstance(service, DecisionTraining)
    backend = FixtureBackend()
    monkeypatch.setattr(service, "backend", backend)
    # Explicit control-protocol test double; no synthetic data is promoted to runtime.
    monkeypatch.setattr(service.data, "read", original.data.read)
    await service.start()
    yield service, backend
    await service.close()


async def test_candidate_four_layers_hold_and_static_replay_not_live_shadow(
    decision_training: tuple[DecisionTraining, FixtureBackend],
) -> None:
    service, backend = decision_training
    created = await plan_job(service, "decision-control")
    running = await wait_job(service, created.id, "running")
    assert backend.directory
    prediction = {
        "sample_id": "a" * 64,
        "point": "tool_domain",
        "option_ids": ["read", "write"],
        "probabilities": {"read": 0.8, "write": 0.2},
        "selected_id": "read",
        "teacher_selected_id": "read",
        "observed_state_digest": "b" * 64,
        "adopted": False,
    }
    (backend.directory / "output/predictions-validation.json").write_text(json.dumps([prediction]))
    backend.checkpoint(running, 2, True)
    done = await wait_job(service, created.id, "succeeded")
    assert done.bundle_id
    candidate = (await service.bundles(USER, "project"))[0]
    assert (
        candidate.kind == "decision"
        and candidate.source == "test"
        and not candidate.quality_release_eligible
    )
    command = DecisionEvaluationCommand(
        request_id="four-layers", project_id="project", bundle_id=candidate.id
    )
    evaluation = await service.evaluate(USER, command)
    assert evaluation.status == "HOLD" and not evaluation.release_eligible
    assert "independent_decision_gold_required" in evaluation.blockers
    assert "fresh_live_shadow_required" in evaluation.blockers
    assert "complete_isolated_agent_comparison_missing" in evaluation.blockers
    assert await service.evaluate(USER, command) == evaluation
    replay = await service.shadow_replay(USER, "project", candidate.id)
    assert not replay.agent_benefit_verified and not replay.predictions[0].adopted
    (backend.directory / "output/predictions-validation.json").write_text("[]")
    with pytest.raises(ApplicationError) as changed:
        await service.shadow_replay(USER, "project", candidate.id)
    assert changed.value.code == "decision_shadow_evidence_missing"


def test_encoder_and_llm_exports_are_separate_and_neither_contains_future_evidence() -> None:
    from auton.training.decision_data import DecisionDataAdapterFactory

    source = record()
    encoder = DecisionDataAdapterFactory().create("encoder_choice").render(source)
    llm = DecisionDataAdapterFactory().create("llm_json").render(source)
    assert encoder["format"] == "encoder-choice-v1" and "messages" not in encoder
    assert llm["format"] == "decision-json-readout-v1" and llm["loss_message_indices"] == [1]
    assert "proofs" not in llm and "assessment" not in json.dumps(llm)
    assert llm["requires_actual_template_token_mask"]
