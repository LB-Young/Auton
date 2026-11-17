from auton.model.config import ModelConfig, ModelSpec
from auton.model.contracts import ModelInfo, ModelRequest
from auton.model.ports import ModelError


class ModelRegistry:
    def __init__(self, models: tuple[ModelSpec, ...]) -> None:
        self.models = {model.id: model for model in models}
        self.health: dict[str, str] = {}

    def select(self, request: ModelRequest) -> tuple[ModelSpec, int]:
        spec = self.models.get(request.model_id)
        if spec is None:
            raise ModelError("model_not_found", "The selected model is not registered")
        required = {"text"}
        if request.tools:
            required.add("tools")
        if request.output_format == "json":
            required.add("json")
        if not required.issubset(spec.capabilities):
            raise ModelError(
                "unsupported_capability", "Model capability does not match this request"
            )
        # Conservative byte-based reservation, not an assertion of exact tokenizer counts.
        input_estimate = len(request.model_dump_json().encode()) + 512
        if (
            input_estimate + request.max_output_tokens > spec.context_tokens
            or request.max_output_tokens > spec.max_output_tokens
        ):
            raise ModelError(
                "context_limit", "Request exceeds the operational context/output limit"
            )
        return spec, input_estimate

    def catalog(self, credentials: bool) -> list[ModelInfo]:
        return [
            ModelInfo.model_validate(
                {
                    **spec.model_dump(include=set(ModelInfo.model_fields)),
                    "health": "test_fixture"
                    if spec.provider == "mock"
                    else (
                        self.health.get(spec.id, "not_checked")
                        if credentials
                        else "credential_missing"
                    ),
                    "capability_source": "test-fixture"
                    if spec.provider == "mock"
                    else "provider-declared",
                }
            )
            for spec in self.models.values()
        ]


class ModelRegistryFactory:
    def create(self, config: ModelConfig) -> ModelRegistry:
        if config.backend == "mock":
            return ModelRegistry(
                (
                    ModelSpec(
                        id="fixture-model",
                        provider="mock",
                        location="local",
                        declared_revision="fixture-v1",
                        base_revision="fixture-v1",
                        runtime_revision="synthetic-v1",
                        revision_is_pinned=True,
                        declared_context_tokens=8192,
                    ),
                )
            )
        return ModelRegistry(
            (
                ModelSpec(
                    id="deepseek-flash",
                    provider="deepseek",
                    location="remote",
                    declared_revision="DeepSeek-V4.1-Flash-1017",
                    input_microusd_per_million=300000,
                    output_microusd_per_million=1200000,
                ),
                ModelSpec(
                    id="deepseek-v4-pro",
                    provider="deepseek",
                    location="remote",
                    declared_revision="DeepSeek-V4-Pro-0813",
                    input_microusd_per_million=1320000,
                    output_microusd_per_million=3960000,
                ),
            )
        )
