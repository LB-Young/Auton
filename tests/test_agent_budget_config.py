"""Configurable project budgets stay aligned across validation and context envelopes."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from auton.agent.contracts import AgentConfig, RunLimits
from auton.bootstrap.config import ApplicationConfig
from auton.constitution.config import Principal
from auton.context.contracts import ContextRequest, PendingOperation, TaskState
from auton.model.contracts import ModelMessage

LIMITS = dict(
    max_steps=100,
    max_tool_calls=200,
    max_tokens=100000,
    max_cost_microusd=1000000,
    max_output_tokens=2048,
)


def test_requested_budgets_load_and_server_policy_does_not_clamp_tools() -> None:
    import tomllib

    root = Path(__file__).parents[1]
    configured = ApplicationConfig.model_validate(
        tomllib.loads((root / "config/server.toml").read_text())
    )
    assert configured.agent.max_steps == 100
    assert configured.agent.max_tool_calls == configured.constitution.budget.tool_calls == 200
    assert AgentConfig.model_validate(LIMITS).max_cost_microusd == 1000000
    assert RunLimits(**LIMITS).max_steps == 100


@pytest.mark.parametrize("field,value", [("max_steps", 101), ("max_tool_calls", 201)])
def test_limits_remain_bounded(field: str, value: int) -> None:
    for schema in (AgentConfig, RunLimits):
        with pytest.raises(ValidationError):
            schema.model_validate({**LIMITS, field: value})


def test_context_envelope_can_hold_two_hundred_tool_receipts_and_long_history() -> None:
    pending = tuple(
        PendingOperation(operation_id=f"operation-{n}", status="completed") for n in range(200)
    )
    history = tuple(ModelMessage(role="user", content=f"turn-{n}") for n in range(379))
    context = ContextRequest(
        request_id="limits",
        principal=Principal(owner="test", role="runtime"),
        project_id="project",
        goal_id="goal",
        model_id="fixture-model",
        state=TaskState(goal="test", pending=pending),
        history=history,
    )
    assert len(context.state.pending) == 200 and len(context.history) == 379
    with pytest.raises(ValidationError):
        TaskState(
            goal="test",
            pending=(*pending, PendingOperation(operation_id="extra", status="completed")),
        )
