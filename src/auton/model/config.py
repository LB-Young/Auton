from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    backend: Literal["deepseek", "mock"] = "deepseek"
    fixture_scenario: Literal["baseline", "agent_acceptance"] = "baseline"

    @model_validator(mode="after")
    def fixture_only(self) -> "ModelConfig":
        if self.backend != "mock" and self.fixture_scenario != "baseline":
            raise ValueError("Synthetic scenarios require explicit mock backend")
        return self

    secret_reference: str = Field(default="DEEPSEEK_API_KEY", pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    timeout_seconds: float = Field(default=45, gt=0, le=120)
    max_parallel: int = Field(default=4, ge=1, le=16)


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    provider: Literal["deepseek", "mock"]
    location: Literal["local", "remote"]
    declared_revision: str
    executor_tier: Literal["small_2b", "small_7b", "strong", "test_fixture"] = "strong"
    base_revision: str | None = None
    adapter_revision: str | None = None
    template_revision: str | None = None
    runtime_revision: str = "deepseek-http-sse-v1"
    quantization: str | None = None
    # Operational cap is deliberately smaller than the provider's declared context.
    context_tokens: int = 8192
    declared_context_tokens: int = 1048576
    max_output_tokens: int = 2048
    capabilities: tuple[Literal["text", "tools", "json"], ...] = ("text", "tools", "json")
    input_microusd_per_million: int = 0
    output_microusd_per_million: int = 0
    price_revision: str = "2026-11-17-peak"
    revision_is_pinned: bool = False

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> int:
        total = (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
        )
        return (total + 999999) // 1000000
