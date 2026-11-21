from pathlib import Path

import pytest
from pydantic import ValidationError
from test_agent import result
from test_context import context as context

from auton.context.service import ContextEngine
from auton.evolve.contracts import EvolutionConfig
from auton.evolve.mutation import MutationStrategyFactory, TrainSummary
from auton.model.contracts import ModelRequest, ModelResult, ModelUsage, ToolCall
from auton.model.ports import ModelError


async def test_reflection_only_emits_bounded_text_not_gate_or_tool_authority(
    context: ContextEngine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    models = context.deps.models
    requests: list[ModelRequest] = []

    async def generate(request: ModelRequest) -> ModelResult:
        requests.append(request)
        return result(
            request,
            '{"new_body":"Write once and verify.\\n","rationale":"Keep the original grant."}',
        )

    monkeypatch.setattr(models, "generate", generate)
    strategy = MutationStrategyFactory().create(
        EvolutionConfig(directory=tmp_path / "evolve", reflection_model="fixture-model"), models
    )
    evidence = (TrainSummary(report_id="1" * 64, reasons=("independent_file_digest_mismatch",)),)
    from test_context import USER

    outcome = await strategy.generate(
        USER,
        "reflection-once",
        "Write once.\n",
        "## Steps",
        "Verify existing delivery",
        evidence,
        (),
        True,
    )
    assert outcome.patch and outcome.patch.new_body == "Write once and verify.\n"
    assert outcome.receipt.source == "test" and outcome.receipt.dispatch == "confirmed"
    assert len(requests) == 1 and requests[0].principal.role == "evolution"
    assert requests[0].data_domain == "local-only" and not requests[0].tools
    with pytest.raises(ValidationError):
        TrainSummary.model_validate({"report_id": "1" * 64, "split": "meta"})

    async def tool_or_self_score(request: ModelRequest) -> ModelResult:
        return result(
            request,
            '{"new_body":"skip checks","rationale":"trust me","passed":true}',
            calls=(ToolCall(id="self-approve", name="approve", arguments={}),),
        )

    monkeypatch.setattr(models, "generate", tool_or_self_score)
    rejected = await strategy.generate(
        USER,
        "reflection-no-authority",
        "Write once.\n",
        "## Steps",
        "Verify existing delivery",
        evidence,
        (),
        False,
    )
    assert rejected.patch is None and rejected.receipt.reason == "reflection_protocol_invalid"


async def test_reflection_unknown_usage_is_null_and_known_error_cost_is_preserved(
    context: ContextEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_context import USER

    strategy = MutationStrategyFactory().create(
        EvolutionConfig(reflection_model="fixture-model"), context.deps.models
    )
    evidence = (TrainSummary(report_id="1" * 64),)

    async def unknown(request: ModelRequest) -> ModelResult:
        raise ModelError("provider_timeout", "Synthetic unknown result", dispatched=True)

    monkeypatch.setattr(context.deps.models, "generate", unknown)
    missing = await strategy.generate(
        USER, "unknown-generation", "Old body", "## Steps", "Verify", evidence, (), False
    )
    assert missing.patch is None and missing.receipt.dispatch == "unknown"
    assert missing.receipt.tokens is None and missing.receipt.cost_microusd is None

    async def accounted(request: ModelRequest) -> ModelResult:
        raise ModelError(
            "invalid_stream",
            "Synthetic malformed paid result",
            dispatched=True,
            usage=ModelUsage(input_tokens=12, output_tokens=3, estimated_cost_microusd=137),
        )

    monkeypatch.setattr(context.deps.models, "generate", accounted)
    known = await strategy.generate(
        USER, "known-generation-cost", "Old body", "## Steps", "Verify", evidence, (), False
    )
    assert known.patch is None and known.receipt.dispatch == "confirmed"
    assert known.receipt.cost_microusd == 137 and known.receipt.tokens == 15
