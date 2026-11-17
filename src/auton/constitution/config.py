import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Usage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tokens: int = Field(default=0, ge=0)
    cost_microusd: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)

    def plus(self, other: "Usage") -> "Usage":
        return Usage(
            **{key: value + getattr(other, key) for key, value in self.model_dump().items()}
        )

    def exceeds(self, other: "Usage") -> bool:
        return any(value > getattr(other, key) for key, value in self.model_dump().items())


ActionName = Literal[
    "demo.start",
    "demo.stop",
    "model.generate",
    "judgment.evaluate",
    "tool.read",
    "tool.write",
    "dataset.read",
    "model.train",
    "asset.read",
    "asset.publish",
    "asset.propose",
    "release.activate",
]


class ConstitutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    allowed_actions: tuple[ActionName, ...] = (
        "demo.start",
        "demo.stop",
        "model.generate",
        "judgment.evaluate",
        "tool.read",
        "tool.write",
        "dataset.read",
        "model.train",
        "asset.read",
        "asset.publish",
        "asset.propose",
        "release.activate",
    )
    remote_providers: tuple[Literal["deepseek", "typesafe"], ...] = ()
    approval_actions: tuple[ActionName, ...] = ("tool.write", "release.activate")
    autonomy_max: int = Field(default=1, ge=0, le=3)
    budget: Usage = Field(
        default_factory=lambda: Usage(
            tokens=100000,
            cost_microusd=5000000,
            tool_calls=100,
        )
    )
    max_concurrent: int = Field(default=4, ge=1, le=32)
    authorization_ttl_seconds: int = Field(default=300, ge=1, le=3600)

    @property
    def version(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()[:24]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: str = Field(min_length=1, max_length=200)
    role: Literal["user", "runtime", "training", "evolution"] = "runtime"


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    principal: Principal
    goal_id: str = Field(min_length=1, max_length=200)
    goal_revision: int = Field(ge=1)
    operation_id: str = Field(default="preview", min_length=1, max_length=200)
    action: str = Field(min_length=1, max_length=100)
    data_domain: Literal["public", "local-only", "secret"] = "local-only"
    destination: Literal["local", "remote"] = "local"
    provider: str | None = None
    input_digest: str = Field(default="0" * 64, pattern=r"^[a-f0-9]{64}$")
    autonomy: int = Field(default=0, ge=0, le=3)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class PolicyDecision(BaseModel):
    outcome: Literal["allow", "deny", "approval_required"]
    reason_codes: tuple[str, ...]
    policy_version: str


class PublicPolicy(BaseModel):
    version: str
    allowed_actions: tuple[str, ...]
    remote_providers: tuple[str, ...]
    remote_data_domains: tuple[Literal["public"], ...] = ("public",)
    approval_actions: tuple[str, ...]
    autonomy_max: int
    budget_per_goal: Usage
    max_concurrent: int
