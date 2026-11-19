import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, ValidationError

from auton.constitution.config import ConstitutionConfig, Principal
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.judgment.adapter import LayaAdapter, MockJudgmentAdapter
from auton.judgment.config import JudgmentConfig
from auton.judgment.contracts import DecisionSource, JudgmentRequest, Option, Question
from auton.judgment.policy import RoutePolicyFactory, decode
from auton.judgment.questions import JudgmentQuestionsFactory
from auton.judgment.service import JudgmentDependencies, JudgmentService
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.model.config import ModelConfig
from auton.model.registry import ModelRegistryFactory

PRINCIPAL = Principal(owner="owner", role="runtime")


def request(**changes: object) -> JudgmentRequest:
    return JudgmentRequest.model_validate(
        {
            "request_id": "decision-1",
            "principal": PRINCIPAL,
            "goal_id": "goal-1",
            "state": "请计算 1 加 1，只返回结果。",
            "state_cutoff": 12,
            "questions": JudgmentQuestionsFactory().create(),
            **changes,
        }
    )


@pytest.fixture
async def service(tmp_path: Path, deps: RuntimeDependencies) -> AsyncIterator[JudgmentService]:
    events = EventLogFactory().create(KernelConfig(data_directory=tmp_path))
    await events.start()
    control = ConstitutionFactory().create(
        ConstitutionConfig(), ConstitutionDependencies(events, deps)
    )
    await control.start()

    # The dependency only uses the catalog Port; retain a concrete full mock gateway for typing.
    from auton.constitution.secrets import SecretStoreFactory
    from auton.model.factory import ModelGatewayFactory
    from auton.model.gateway import GatewayDependencies

    models = ModelGatewayFactory().create(
        ModelConfig(backend="mock"),
        GatewayDependencies(
            control, events, deps, SecretStoreFactory().create(tmp_path / "missing.env")
        ),
    )
    await models.start()
    value = JudgmentService(
        MockJudgmentAdapter(JudgmentConfig(backend="mock")),
        RoutePolicyFactory().create(),
        JudgmentDependencies(control, control, events, deps, models),
        application_enabled=True,
    )
    await value.start()
    yield value
    await value.close()
    await models.close()
    await control.close()
    await events.close()


async def test_decision_preserves_cutoff_raw_source_and_separate_adoption(
    service: JudgmentService,
) -> None:
    result = await service.decide(request())
    assert not result.adopted and result.source.source == "test"
    assert result.state_cutoff == 12 and result.route.status == "proposed"
    assert result.route.model_id == "fixture-model"
    assert len(result.answers) == 4
    raw = await service.deps.events.lookup(result.raw_event_id)
    assert raw and raw.event.payload["source"]
    assert await service.decide(request()) == result
    adopted = await service.apply(request(), current_state_cutoff=12)
    assert adopted.adopted
    assert await service.apply(request(), current_state_cutoff=12) == adopted
    assert not (await service.decide(request())).adopted  # Immutable inference record.
    with pytest.raises(ApplicationError) as error:
        await service.decide(request(state="different"))
    assert error.value.code == "judgment_conflict"


async def test_stale_state_and_revised_goal_cannot_apply(service: JudgmentService) -> None:
    await service.decide(request())
    with pytest.raises(ApplicationError) as error:
        await service.apply(request(), 13)
    assert error.value.code == "stale_state"
    # Drive the human control surface; no runtime ability to revise its own goal.
    control = service.deps.control
    from auton.constitution.control import ConstitutionService

    assert isinstance(control, ConstitutionService)
    await control.revise_goal(Principal(owner="owner", role="user"), "goal-1", 1)
    with pytest.raises(ApplicationError) as error:
        await service.apply(request(), 12)
    assert error.value.code == "stale_revision"


async def test_late_result_is_saved_but_stale(service: JudgmentService) -> None:
    original = service.adapter.predict
    from auton.constitution.control import ConstitutionService

    control = service.deps.control
    assert isinstance(control, ConstitutionService)

    async def late(req: JudgmentRequest) -> tuple[DecisionSource, dict[str, JsonValue]]:
        response = await original(req)
        await control.revise_goal(Principal(owner="owner", role="user"), "goal-1", 1)
        return response

    service.adapter.predict = late  # type: ignore[method-assign, assignment]
    result = await service.decide(request())
    assert result.route.status == "stale" and not result.adopted
    assert result.route.reason_codes == ("stale_revision",)
    assert await service.deps.events.lookup(result.raw_event_id)


async def test_unavailable_never_falls_back_and_retry_needs_new_id(
    service: JudgmentService,
) -> None:
    async def fail(req: JudgmentRequest) -> tuple[DecisionSource, dict[str, JsonValue]]:
        raise ApplicationError(503, "local_inference_failed", "offline worker failed")

    service.adapter.predict = fail  # type: ignore[method-assign, assignment]
    with pytest.raises(ApplicationError) as error:
        await service.decide(request())
    assert error.value.code == "local_inference_failed"
    with pytest.raises(ApplicationError) as error:
        await service.decide(request())
    assert error.value.code == "judgment_interrupted"
    failed = await service.deps.events.lookup(f"judgment:{service.key(request())}:failed")
    assert failed and failed.event.payload["adopted"] is False


async def test_private_decision_can_run_locally_but_remote_route_is_filtered(
    service: JudgmentService,
) -> None:
    original = service.deps.models.catalog
    registry = ModelRegistryFactory().create(ModelConfig())
    service.deps.models.catalog = lambda principal=None: registry.catalog(True)  # type: ignore[method-assign]
    result = await service.decide(request())
    assert result.route.status == "blocked"
    assert set(result.route.excluded.values()) == {"data_egress_denied"}
    with pytest.raises(ApplicationError):
        await service.apply(request(), 12)
    service.deps.models.catalog = original  # type: ignore[method-assign]


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"type": "choice", "choice": "other", "probabilities": {"other": 1}},
        {
            "type": "choice",
            "choice": "small_2b",
            "probabilities": {"small_2b": float("nan"), "small_7b": 0, "strong": 0},
        },
        {
            "type": "choice",
            "choice": "small_2b",
            "probabilities": {"small_2b": 0.1, "small_7b": 0.2, "strong": 0.7},
        },
    ],
)
def test_malformed_answer_fails_per_question(bad: JsonValue) -> None:
    question = JudgmentQuestionsFactory().create()[1]
    assert decode(question, bad).status == "failed"


def test_option_order_preserves_stable_identity_and_high_confidence_is_not_success() -> None:
    original = JudgmentQuestionsFactory().create()[1]
    reversed_question = original.model_copy(update={"options": tuple(reversed(original.options))})
    raw: dict[str, JsonValue] = {
        "type": "choice",
        "choice": "strong",
        "probabilities": {"small_2b": 0.01, "small_7b": 0.01, "strong": 0.98},
        "answer_confidence": 0.98,
    }
    assert (
        decode(original, raw).selected_id == decode(reversed_question, raw).selected_id == "strong"
    )
    assert decode(original, raw).confidence == 0.98
    # High-confidence semantic mistakes are retained; no success label is synthesized.
    assert "success" not in decode(original, raw).model_dump()


async def test_partial_batch_failure_does_not_erase_valid_answers(service: JudgmentService) -> None:
    original = service.adapter.predict

    async def partial(req: JudgmentRequest) -> tuple[DecisionSource, dict[str, JsonValue]]:
        source, raw = await original(req)
        assert isinstance(raw["answers"], dict)
        raw["answers"]["executor"] = {"error": "state_truncated"}
        return source, raw

    service.adapter.predict = partial  # type: ignore[method-assign, assignment]
    result = await service.decide(request())
    assert result.answers[1].status == "abstained"
    assert result.answers[2].status == "answered"
    assert result.route.status == "blocked"


async def test_missing_weights_and_advisory_gate(service: JudgmentService, tmp_path: Path) -> None:
    adapter = LayaAdapter(JudgmentConfig(directory=tmp_path / "missing"))
    await adapter.start()
    assert adapter.info().health == "weights_missing"
    with pytest.raises(ApplicationError) as error:
        await adapter.predict(request())
    assert error.value.code == "weights_missing"
    await adapter.close()
    await service.decide(request())
    service.application_enabled = False
    with pytest.raises(ApplicationError) as error:
        await service.apply(request(), 12)
    assert error.value.code == "judgment_advisory_only"


async def test_busy_is_bounded_and_cancellation_is_recorded(service: JudgmentService) -> None:
    started = asyncio.Event()

    async def pending(req: JudgmentRequest) -> tuple[DecisionSource, dict[str, JsonValue]]:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    service.adapter.predict = pending  # type: ignore[method-assign, assignment]
    task = asyncio.create_task(service.decide(request()))
    await started.wait()
    with pytest.raises(ApplicationError) as error:
        await service.decide(request(request_id="other"))
    assert error.value.code == "judgment_busy"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await service.deps.events.lookup(f"judgment:{service.key(request())}:failed")


def test_public_api_uses_trusted_questions_and_cannot_impersonate(client: TestClient) -> None:
    assert client.get("/api/v1/judgment").json()["health"] == "test_fixture"
    assert client.get("/api/v1/judgment").json()["application_enabled"] is False
    body = {"request_id": "preview-1", "state": "简单任务"}
    response = client.post("/api/v1/judgment/preview", json=body)
    assert response.status_code == 200
    assert response.json()["source"]["provider"] == "mock"
    assert response.json()["adopted"] is False
    assert (
        client.post(
            "/api/v1/judgment/preview", json={**body, "principal": {"role": "user"}}
        ).status_code
        == 422
    )


def test_question_schema_and_score_identity() -> None:
    with pytest.raises(ValidationError):
        Question(
            id="tier",
            point="executor_tier",
            instructions="Choose",
            options=(Option(id="x", description="x"), Option(id="y", description="y")),
        )
    question = Question(
        id="fit",
        point="skill_match",
        type="score",
        instructions="Score fit",
        options=(Option(id="low", description="low"), Option(id="high", description="high")),
    )
    answer = decode(
        question, {"type": "score", "score": 0.8, "probabilities": {"0": 0.2, "1": 0.8}}
    )
    assert answer.expected_score == 0.8 and answer.selected_id == "high"


async def test_worker_deadline_kills_owned_process_and_drops_inherited_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typing import cast

    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-only-test-credential")
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"ready":true,"runtime":"laya-0.3.20"}\n')
    killed = []

    class Writer:
        def write(self, data: bytes) -> None:
            assert b"questions" in data

        async def drain(self) -> None:
            pass

    class Process:
        stdout = reader
        stdin = Writer()
        returncode = None

        def kill(self) -> None:
            killed.append(True)

        async def wait(self) -> int:
            return 0

    async def spawn(*args: object, **kwargs: object) -> asyncio.subprocess.Process:
        env = kwargs["env"]
        assert isinstance(env, dict) and "DEEPSEEK_API_KEY" not in env
        assert env["HF_HUB_OFFLINE"] == env["TRANSFORMERS_OFFLINE"] == "1"
        return cast(asyncio.subprocess.Process, Process())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    adapter = LayaAdapter(JudgmentConfig(directory=tmp_path, timeout_seconds=0.01))
    with pytest.raises(ApplicationError) as error:
        await adapter.predict(request())
    assert error.value.code == "judgment_timeout"
    assert killed == [True] and adapter.process is None


def test_fixed_candidate_filters_and_capability_tiers_precede_selection() -> None:
    req = request(
        data_domain="public", required_capabilities=("tools",), required_context_tokens=4096
    )
    q = JudgmentQuestionsFactory().create()[1]
    req = req.model_copy(update={"questions": (q,)})
    answer = decode(
        q,
        {
            "type": "choice",
            "choice": "strong",
            "probabilities": {"small_2b": 0.0, "small_7b": 0.0, "strong": 1.0},
            "answer_confidence": 1.0,
        },
    )
    spec = ModelRegistryFactory().create(ModelConfig()).catalog(True)[0]
    candidates = [
        spec.model_copy(
            update={"id": "local-2b", "location": "local", "executor_tier": "small_2b"}
        ),
        spec.model_copy(
            update={"id": "weak-protocol", "location": "local", "capabilities": ("text",)}
        ),
        spec.model_copy(
            update={"id": "short-context", "location": "local", "context_tokens": 1000}
        ),
        spec,
    ]
    # Public policy shape comes from the control service in production.
    from auton.constitution.config import PublicPolicy

    public = PublicPolicy(
        version="fixed",
        allowed_actions=(),
        remote_providers=("deepseek",),
        approval_actions=(),
        autonomy_max=1,
        budget_per_goal=ConstitutionConfig().budget,
        max_concurrent=4,
    )
    route = RoutePolicyFactory().create().select(req, (answer,), candidates, public)
    assert route.model_id == spec.id and route.status == "proposed"
    assert route.excluded == {
        "local-2b": "insufficient_tier",
        "weak-protocol": "capability_missing",
        "short-context": "context_limit",
    }
