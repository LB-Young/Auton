from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    backend: Literal["deepseek", "mock"] = "deepseek"
    hosted_context_tokens: int = Field(default=65536, ge=8192, le=131072)
    local_targets: tuple["ModelSpec", ...] = ()
    fixture_scenario: Literal["baseline", "agent_acceptance"] = "baseline"

    @model_validator(mode="after")
    def fixture_only(self) -> "ModelConfig":
        if (
            any(t.provider != "local" for t in self.local_targets)
            or len({t.id for t in self.local_targets}) != len(self.local_targets)
            or any(
                t.id in {"deepseek-flash", "deepseek-v4-pro", "fixture-model", "project_default"}
                for t in self.local_targets
            )
        ):
            raise ValueError("Local targets require unique reserved-safe local model ids")
        if self.backend != "mock" and self.fixture_scenario != "baseline":
            raise ValueError("Synthetic scenarios require explicit mock backend")
        return self

    secret_reference: str = Field(default="DEEPSEEK_API_KEY", pattern=r"^[A-Z][A-Z0-9_]{2,99}$")
    timeout_seconds: float = Field(default=45, gt=0, le=120)
    max_parallel: int = Field(default=4, ge=1, le=16)


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    provider: Literal["deepseek", "mock", "local"]
    location: Literal["local", "remote"]
    declared_revision: str
    executor_tier: Literal["small_2b", "small_7b", "strong", "test_fixture"] = "strong"
    base_revision: str | None = None
    adapter_revision: str | None = None
    template_revision: str | None = None
    runtime_revision: str = "deepseek-http-sse-v2"
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
    endpoint: str | None = None
    expected_fingerprint: str | None = None
    local_secret_reference: str | None = Field(
        default=None, pattern=r"^AUTON_LOCAL_MODEL_[A-Z0-9_]{1,80}$"
    )
    base_manifest_digest: str | None = None
    local_tool_parser: Literal["tagged_json", "json"] = "tagged_json"
    local_lora_rank: int = Field(default=8, ge=1, le=128)

    @model_validator(mode="after")
    def local_binding(self) -> "ModelSpec":
        if self.provider == "local":
            import re
            from urllib.parse import urlsplit

            parsed = urlsplit(self.endpoint or "")
            if (
                self.location != "local"
                or parsed.scheme != "http"
                or parsed.hostname != "127.0.0.1"
                or not parsed.port
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("Local deployment endpoint must be an explicit loopback origin")
            if self.local_secret_reference is None:
                raise ValueError("Local runtime requires a dedicated local credential reference")
            if (
                not self.expected_fingerprint
                or not re.fullmatch(r"[a-f0-9]{64}", self.expected_fingerprint)
                or not self.revision_is_pinned
            ):
                raise ValueError("Local runtime requires a pinned deployment fingerprint")
        elif self.endpoint is not None:
            raise ValueError("Hosted endpoints cannot be overridden")
        return self

    def estimated_cost(self, input_tokens: int, output_tokens: int) -> int:
        total = (
            input_tokens * self.input_microusd_per_million
            + output_tokens * self.output_microusd_per_million
        )
        return (total + 999999) // 1000000
