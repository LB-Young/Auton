from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from auton.constitution.config import ActionRequest, Usage


class Goal(BaseModel):
    model_config = ConfigDict(frozen=True)
    owner: str
    revision: int = 1
    cancelled: bool = False


class Reservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    request_id: str
    request: ActionRequest
    estimate: Usage
    policy_version: str
    expires_at: float
    approval_id: str | None = None
    status: Literal["reserved", "started", "unknown", "settled", "released"] = "reserved"
    actual: Usage = Field(default_factory=Usage)


class Approval(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    request: ActionRequest
    policy_version: str
    expires_at: float
