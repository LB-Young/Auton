import math
from typing import Literal

from pydantic import Field, model_validator

from auton.datasets.contracts import Digest, Id
from auton.model.contracts import Contract


class AgentDecisionPair(Contract):
    reference_report_id: Digest
    candidate_report_id: Digest


class DecisionEvaluationCommand(Contract):
    request_id: Id
    project_id: Id
    bundle_id: Digest
    champion_bundle_id: Digest | None = None
    agent_pairs: tuple[AgentDecisionPair, ...] = Field(default=(), max_length=30)


class DecisionEvaluation(Contract):
    id: Digest
    version: int = 0
    command: DecisionEvaluationCommand
    bundle_digest: Digest
    evidence_digest: Digest
    layers: dict[str, Literal["observed", "missing", "stale", "descriptive_only"]]
    blockers: tuple[str, ...]
    current_evidence_valid: bool = True
    actual_agent_pairs: int = 0
    independent_agent_families: int = 0
    status: Literal["HOLD"] = "HOLD"
    release_eligible: Literal[False] = False
    activation: Literal["teacher_only_no_student_route"] = "teacher_only_no_student_route"


class ShadowPrediction(Contract):
    sample_id: Digest
    point: str
    option_ids: tuple[str, ...]
    probabilities: dict[str, float]
    selected_id: str | None
    teacher_selected_id: str | None
    observed_state_digest: Digest
    adopted: Literal[False] = False

    @model_validator(mode="after")
    def valid_prediction(self) -> "ShadowPrediction":
        if not 2 <= len(self.option_ids) <= 6 or len(set(self.option_ids)) != len(self.option_ids):
            raise ValueError("Invalid shadow option set")
        if (
            set(self.probabilities) != set(self.option_ids)
            or any(not math.isfinite(v) or v < 0 or v > 1 for v in self.probabilities.values())
            or abs(sum(self.probabilities.values()) - 1) > 1e-5
        ):
            raise ValueError("Shadow probabilities must match stable option ids")
        if self.selected_id is not None and self.selected_id not in self.option_ids:
            raise ValueError("Unknown shadow selection")
        if self.teacher_selected_id is not None and self.teacher_selected_id not in self.option_ids:
            raise ValueError("Unknown teacher selection")
        return self


class ShadowEvaluation(Contract):
    protocol: Literal["decision-shadow-replay-v1"] = "decision-shadow-replay-v1"
    source: Literal["historical_validation_not_live_shadow"] = (
        "historical_validation_not_live_shadow"
    )
    predictions: tuple[ShadowPrediction, ...]
    live_distribution_verified: Literal[False] = False
    agent_benefit_verified: Literal[False] = False
