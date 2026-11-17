import asyncio
import io
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from auton.constitution.config import ActionRequest, ConstitutionConfig, Principal, Usage
from auton.constitution.control import ConstitutionService
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.policy import PolicyEvaluatorFactory
from auton.constitution.secrets import LoggerFactory, Redactor, SecretStoreFactory
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError, RuntimeDependencies

RUNTIME = Principal(owner="owner", role="runtime")
USER = Principal(owner="owner", role="user")


def action(operation: str, **changes: object) -> ActionRequest:
    return ActionRequest.model_validate(
        {
            "principal": RUNTIME,
            "goal_id": "goal",
            "goal_revision": 1,
            "operation_id": operation,
            "action": "model.generate",
            **changes,
        }
    )


@pytest.fixture
async def control(tmp_path: Path, deps: RuntimeDependencies) -> AsyncIterator[ConstitutionService]:
    events = EventLogFactory().create(KernelConfig(data_directory=tmp_path))
    await events.start()
    service = ConstitutionFactory().create(
        ConstitutionConfig(budget=Usage(tokens=10, cost_microusd=100, tool_calls=2)),
        ConstitutionDependencies(events, deps),
    )
    await service.start()
    await service.register_goal(RUNTIME, "goal")
    yield service
    await service.close()
    await events.close()


@pytest.mark.parametrize("role", ["runtime", "training", "evolution"])
def test_learned_actors_cannot_change_fixed_boundaries(role: str) -> None:
    evaluator = PolicyEvaluatorFactory().create(ConstitutionConfig())
    for name in ("constitution.modify", "checker.modify", "holdout.read", "secret.read"):
        request = action("op", action=name, principal={"owner": "owner", "role": role})
        assert evaluator.evaluate(request).outcome == "deny"


def test_egress_provider_autonomy_and_approval_are_deterministic() -> None:
    evaluator = PolicyEvaluatorFactory().create(ConstitutionConfig(remote_providers=("deepseek",)))
    assert (
        evaluator.evaluate(action("a", destination="remote", provider="deepseek")).outcome == "deny"
    )
    assert (
        evaluator.evaluate(
            action("a", destination="remote", provider="deepseek", data_domain="public")
        ).outcome
        == "allow"
    )
    assert (
        evaluator.evaluate(
            action("a", destination="remote", provider="unregistered", data_domain="public")
        ).outcome
        == "deny"
    )
    assert evaluator.evaluate(action("a", autonomy=3)).outcome == "deny"
    assert evaluator.evaluate(action("a", action="tool.write")).outcome == "approval_required"
    assert evaluator.evaluate(action("a", action="unknown.action")).outcome == "deny"


async def test_atomic_concurrent_reservations_and_idempotency(control: ConstitutionService) -> None:
    results = await asyncio.gather(
        *[control.reserve(action(f"op{i}"), Usage(tokens=7), f"op{i}") for i in range(2)],
        return_exceptions=True,
    )
    assert sum(isinstance(item, ApplicationError) for item in results) == 1
    accepted = next(item for item in results if not isinstance(item, BaseException))
    again = await control.reserve(accepted.request, Usage(tokens=7), accepted.request_id)
    assert again.id == accepted.id
    with pytest.raises(ApplicationError, match="request_conflict"):
        await control.reserve(accepted.request, Usage(tokens=6), accepted.request_id)
    await control.release(RUNTIME, accepted.id)
    await control.reserve(action("next"), Usage(tokens=10), "next")


async def test_started_usage_cannot_be_refunded_on_cancel(control: ConstitutionService) -> None:
    reservation = await control.reserve(action("a"), Usage(tokens=8), "a")
    await control.begin(RUNTIME, reservation.id)
    await control.cancel(USER, "goal", 1)
    with pytest.raises(ApplicationError, match="reconciliation_required"):
        await control.release(USER, reservation.id)
    await control.settle(RUNTIME, reservation.id, Usage(tokens=8))
    await control.revise_goal(USER, "goal", 1)
    with pytest.raises(ApplicationError, match="budget_exceeded"):
        await control.reserve(action("b", goal_revision=2), Usage(tokens=3), "b")


async def test_revision_revocation_and_expiry(control: ConstitutionService) -> None:
    reservation = await control.reserve(action("a"), Usage(tokens=1), "a")
    await control.revise_goal(USER, "goal", 1)
    with pytest.raises(ApplicationError, match="stale_revision"):
        await control.begin(RUNTIME, reservation.id)
    reservation = await control.reserve(action("b", goal_revision=2), Usage(tokens=1), "b")
    old = control.deps
    future = old.now() + timedelta(hours=2)
    control.deps = RuntimeDependencies(now=lambda: future, new_id=old.new_id)
    with pytest.raises(ApplicationError, match="authorization_not_dispatchable"):
        await control.begin(RUNTIME, reservation.id)


async def test_approval_is_bound_to_payload_version_owner_and_expiry(
    control: ConstitutionService,
) -> None:
    request = action("write", action="tool.write", input_digest="a" * 64)
    with pytest.raises(ApplicationError, match="approval_required"):
        await control.reserve(request, Usage(tool_calls=1), "write")
    approval = await control.approve(USER, request)
    with pytest.raises(ApplicationError, match="approval_required"):
        await control.reserve(
            request.model_copy(update={"input_digest": "b" * 64}), Usage(), "write", approval.id
        )
    with pytest.raises(ApplicationError, match="human_required"):
        await control.approve(RUNTIME, request)
    with pytest.raises(ApplicationError, match="human_required"):
        await control.reconfigure(RUNTIME, control.initial, control.public().version)
    await control.reconfigure(USER, ConstitutionConfig(autonomy_max=0), control.public().version)
    with pytest.raises(ApplicationError, match="approval_required"):
        await control.reserve(request, Usage(), "write", approval.id)


async def test_approval_expiring_after_reserve_still_blocks_dispatch(
    control: ConstitutionService,
) -> None:
    request = action("write", action="tool.write")
    approval = await control.approve(USER, request)
    original = control.deps
    reserved_at = original.now() + timedelta(seconds=100)
    control.deps = RuntimeDependencies(now=lambda: reserved_at, new_id=original.new_id)
    item = await control.reserve(request, Usage(tool_calls=1), "write", approval.id)
    expired = original.now() + timedelta(seconds=301)
    assert approval.expires_at < expired.timestamp() < item.expires_at
    control.deps = RuntimeDependencies(now=lambda: expired, new_id=original.new_id)
    with pytest.raises(ApplicationError, match="approval_required"):
        await control.begin(RUNTIME, item.id)


async def test_recovery_holds_uncertain_dispatch_and_persists_user_policy(
    control: ConstitutionService,
) -> None:
    item = await control.reserve(action("a"), Usage(tokens=8), "a")
    await control.begin(RUNTIME, item.id)
    version = await control.reconfigure(
        USER, ConstitutionConfig(budget=Usage(tokens=9)), control.public().version
    )
    await control.close()
    reopened = ConstitutionFactory().create(
        control.initial, ConstitutionDependencies(control.events, control.deps)
    )
    await reopened.start()
    assert reopened.public().version == version
    with pytest.raises(ApplicationError, match="reconciliation_required"):
        await reopened.release(USER, item.id)
    await reopened.settle(RUNTIME, item.id, Usage(tokens=8))
    with pytest.raises(ApplicationError, match="budget_exceeded"):
        await reopened.reserve(action("b"), Usage(tokens=2), "b")
    await reopened.close()


async def test_cross_instance_writers_cannot_double_reserve(control: ConstitutionService) -> None:
    other = ConstitutionFactory().create(
        control.initial, ConstitutionDependencies(control.events, control.deps)
    )
    await other.start()
    try:
        results = await asyncio.gather(
            control.reserve(action("a"), Usage(tokens=8), "a"),
            other.reserve(action("b"), Usage(tokens=8), "b"),
            return_exceptions=True,
        )
        assert sum(isinstance(item, ApplicationError) for item in results) == 1
    finally:
        await other.close()


async def test_usage_overrun_is_accounted_and_wrong_owner_or_role_is_rejected(
    control: ConstitutionService,
) -> None:
    item = await control.reserve(action("a"), Usage(tokens=1), "a")
    with pytest.raises(ApplicationError, match="reservation_not_authorized"):
        await control.begin(Principal(owner="owner", role="training"), item.id)
    await control.begin(RUNTIME, item.id)
    await control.settle(RUNTIME, item.id, Usage(tokens=12))
    with pytest.raises(ApplicationError, match="budget_exceeded"):
        await control.reserve(action("b"), Usage(tokens=1), "b")


def test_secrets_are_references_and_actual_log_output_is_redacted(tmp_path: Path) -> None:
    value = "sk-fixture-never-an-actual-key-12345"
    path = tmp_path / ".env"
    path.write_text(f"AUTON_FIXTURE_KEY={value}\n")
    store = SecretStoreFactory().create(path)
    secret = store.get("AUTON_FIXTURE_KEY")
    assert secret.get_secret_value() == value
    assert value not in repr(store) + repr(secret)
    redactor = Redactor((secret, SecretStr("nonstandard-credential")))
    logger = LoggerFactory().create(redactor)
    stream = io.StringIO()
    logger.handlers[0].setStream(stream)  # type: ignore[attr-defined]
    logger.error("error key=%s other=%s", value, "nonstandard-credential")
    assert value not in stream.getvalue() and "nonstandard-credential" not in stream.getvalue()
    assert "REDACTED" in stream.getvalue()
    assert redactor.redact({"authorization": "bearer any", "nested": [value]}) == {
        "authorization": "[REDACTED]",
        "nested": ["[REDACTED]"],
    }
    with pytest.raises(ApplicationError) as missing:
        store.get("AUTON_NO_SUCH_CREDENTIAL")
    assert missing.value.code == "credential_missing"
    with pytest.raises(ValidationError):
        ConstitutionConfig.model_validate({"api_key": value})


def test_http_control_requires_current_revision_and_does_not_echo_secret_input(
    client: TestClient,
) -> None:
    policy = client.get("/api/v1/policy").json()
    invalid = client.post(
        "/api/v1/policy/revisions",
        json={
            "expected_version": policy["version"],
            "config": {"api_key": "sk-fixture-1234567890123456"},
        },
    )
    assert invalid.status_code == 422 and "sk-fixture" not in invalid.text
    result = client.post(
        "/api/v1/policy/revisions",
        json={
            "expected_version": policy["version"],
            "config": {"allowed_actions": []},
        },
    )
    assert result.status_code == 200 and result.json()["version"] != policy["version"]
    assert (
        client.post(
            "/api/v1/policy/revisions",
            json={
                "expected_version": policy["version"],
                "config": {},
            },
        ).status_code
        == 409
    )
    session = client.post("/api/v1/sessions", json={"request_id": "new"}).json()
    result = client.post(
        f"/api/v1/sessions/{session['id']}/messages", json={"request_id": "send", "content": "test"}
    )
    assert result.status_code == 403
