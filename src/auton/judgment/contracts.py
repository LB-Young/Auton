import hashlib
from typing import Literal

from pydantic import Field, model_validator

from auton.constitution.config import Principal
from auton.model.contracts import Contract


class Option(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    description: str = Field(min_length=1, max_length=300)


class Question(Contract):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    point: Literal["information_sufficiency", "executor_tier", "tool_domain", "skill_match"]
    type: Literal["choice", "boolean", "score"] = "choice"
    revision: str = "auton-question-v1"
    instructions: str = Field(min_length=1, max_length=600)
    options: tuple[Option, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def valid_options(self) -> "Question":
        if self.type == "boolean" and self.options:
            raise ValueError("Boolean options are fixed to no/yes")
        if self.type != "boolean" and len(self.options) < 2:
            raise ValueError("Choice/score requires at least two stable options")
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("Duplicate option id")
        if self.point == "executor_tier" and (
            self.type != "choice"
            or {item.id for item in self.options} != {"small_2b", "small_7b", "strong"}
        ):
            raise ValueError("Executor tier options must use the registered ids")
        return self

    def wire(self) -> dict[str, object]:
        return {
            "type": "noul" if self.type == "boolean" else self.type,
            "instructions": self.instructions,
            **(
                {}
                if self.type == "boolean"
                else {
                    "criteria": {option.id: option.description for option in self.options}
                    if self.type == "choice"
                    else [option.description for option in self.options]
                }
            ),
        }


class JudgmentRequest(Contract):
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    principal: Principal
    goal_id: str = Field(min_length=1, max_length=200)
    goal_revision: int = Field(default=1, ge=1)
    state_cutoff: int = Field(default=0, ge=0)
    state: str = Field(min_length=1, max_length=12000)
    questions: tuple[Question, ...] = Field(min_length=1, max_length=8)
    required_capabilities: tuple[Literal["text", "tools", "json"], ...] = ("text",)
    required_context_tokens: int = Field(default=0, ge=0, le=1048576)
    data_domain: Literal["public", "local-only", "secret"] = "local-only"

    @model_validator(mode="after")
    def unique_questions(self) -> "JudgmentRequest":
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("Duplicate question id")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Answer(Contract):
    question_id: str
    type: Literal["choice", "boolean", "score"]
    status: Literal["answered", "abstained", "failed"]
    selected_id: str | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    expected_score: float | None = None
    reason: str | None = None


class DecisionSource(Contract):
    provider: Literal["laya", "mock"]
    repository: str
    revision: str
    subfolder: str
    runtime_version: str
    device: str
    max_tokens: int
    source: Literal["local", "test"]


class RouteDecision(Contract):
    status: Literal["proposed", "blocked", "not_requested", "stale"]
    model_id: str | None = None
    requested_tier: str | None = None
    reason_codes: tuple[str, ...] = ()
    excluded: dict[str, str] = Field(default_factory=dict)
    policy_version: str


class JudgmentResult(Contract):
    request_id: str
    request_digest: str
    goal_id: str
    goal_revision: int
    state_cutoff: int
    source: DecisionSource
    answers: tuple[Answer, ...]
    raw_event_id: str
    route: RouteDecision
    adopted: bool = False
    latency_ms: int


class JudgmentInfo(Contract):
    backend: str
    checkpoint: str
    revision: str
    health: Literal["not_loaded", "available", "weights_missing", "unavailable", "test_fixture"]
    decision_points: tuple[str, ...]
    application_enabled: bool = False
    primary_only: Literal[True] = True
