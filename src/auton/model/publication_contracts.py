from typing import Literal

from pydantic import Field

from auton.model.config import ModelSpec
from auton.model.contracts import Contract


class ModelActivation(Contract):
    release_id: str
    project_id: str
    target: ModelSpec
    baseline_model_id: str
    percentage: int = Field(ge=1, le=100)
    status: Literal["active", "paused", "revoked", "evaluation"] = "active"
    approval_event_id: str
    languages: tuple[str, ...] = ("zh", "en", "mixed", "other")
    data_domains: tuple[str, ...] = ("public", "local-only")


class ModelProfile(Contract):
    id: str
    version: int = 0
    project_id: str
    current: str | None = None
    releases: dict[str, ModelActivation] = Field(default_factory=dict)


class ModelAssignment(Contract):
    id: str
    version: int = 0
    project_id: str
    goal_id: str
    model_id: str
    release_id: str | None = None
    creation_digest: str
    purpose: Literal["operational", "evaluation"] = "operational"


def input_language(text: str) -> str:
    import re

    chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
    latin = bool(re.search(r"[a-zA-Z]", text))
    return "mixed" if chinese and latin else "zh" if chinese else "en" if latin else "other"
