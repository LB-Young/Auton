import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from auton.bootstrap.config import ApplicationConfig
from auton.constitution.config import ConstitutionConfig, Principal
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.model.config import ModelConfig
from auton.model.contracts import ModelMessage, ModelRequest, ToolSpec
from auton.model.factory import ProviderFactory
from auton.model.gateway import GatewayDependencies, ModelGateway
from auton.model.ports import ModelError
from auton.model.registry import ModelRegistryFactory


class Secrets:
    def get(self, name: str) -> SecretStr:
        assert name == "DEEPSEEK_API_KEY"
        return SecretStr("synthetic-fixture-credential")


def request(**changes: object) -> ModelRequest:
    return ModelRequest.model_validate(
        {
            "model_id": "deepseek-flash",
            "request_id": "request-1",
            "goal_id": "goal-1",
            "principal": Principal(owner="owner", role="runtime"),
            "messages": [{"role": "user", "content": "Reply OK"}],
            "max_output_tokens": 32,
            "data_domain": "public",
            **changes,
        }
    )


def sse(*frames: object, done: bool = True) -> httpx.Response:
    body = "".join("data: " + json.dumps(frame) + "\n\n" for frame in frames)
    if done:
        body += "data: [DONE]\n\n"
    return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})


def frame(text: str = "", finish: str | None = None, usage: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "model": "deepseek-flash",
        "system_fingerprint": "fixture",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}],
    }
    if usage:
        value["usage"] = {"prompt_tokens": 10, "completion_tokens": 2}
    return value


@pytest.fixture
async def gateway(tmp_path: Path, deps: RuntimeDependencies) -> AsyncIterator[ModelGateway]:
    events = EventLogFactory().create(KernelConfig(data_directory=tmp_path))
    await events.start()
    control = ConstitutionFactory().create(
        ConstitutionConfig(remote_providers=("deepseek",)), ConstitutionDependencies(events, deps)
    )
    await control.start()
    config = ModelConfig()
    provider = ProviderFactory().create(
        config,
        Secrets(),
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: sse(frame("OK", "stop", True)))
        ),
    )
    value = ModelGateway(
        config,
        ModelRegistryFactory().create(config),
        provider,
        GatewayDependencies(control, events, deps, Secrets()),
    )
    await value.start()
    yield value
    await value.close()
    await control.close()
    await events.close()


async def test_stream_usage_replay_conflict_and_durable_settlement(gateway: ModelGateway) -> None:
    chunks = [chunk async for chunk in gateway.stream(request())]
    assert chunks[0].content == "OK"
    result = chunks[-1].result
    assert result and result.source == "remote" and result.usage.input_tokens == 10
    assert result.system_fingerprint == "fixture"
    assert await gateway.generate(request()) == result
    stored = await gateway.deps.events.lookup(f"model:{gateway._key(request())}:completed")
    assert stored is not None
    with pytest.raises(ModelError, match="different input"):
        await gateway.generate(request(messages=[{"role": "user", "content": "different"}]))
    assert gateway.catalog()[0].health == "available"


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"data_domain": "local-only"}, "data_egress_denied"),
        ({"data_domain": "secret"}, "data_egress_denied"),
        ({"model_id": "missing"}, "model_not_found"),
        ({"messages": [{"role": "user", "content": "x" * 15000}] * 5}, "context_limit"),
        ({"messages": [{"role": "user", "content": "sk-" + "a" * 32}]}, "credential_in_input"),
    ],
)
async def test_preflight_never_dispatches(
    gateway: ModelGateway, changes: dict[str, object], code: str
) -> None:
    with pytest.raises(ApplicationError) as error:
        await gateway.generate(request(**changes))
    assert error.value.code == code
    assert await gateway.deps.events.lookup(f"model:{gateway._key(request())}:started") is None


@pytest.mark.parametrize(
    "status,code,uncertain",
    [
        (401, "credential_rejected", False),
        (402, "balance_insufficient", False),
        (404, "model_not_found", False),
        (429, "rate_limited", False),
        (500, "provider_unavailable", True),
    ],
)
async def test_provider_errors_never_fall_back(
    gateway: ModelGateway, status: int, code: str, uncertain: bool
) -> None:
    provider = ProviderFactory().create(
        ModelConfig(),
        Secrets(),
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, text="do not expose body")
            )
        ),
    )
    await gateway.provider.close()
    gateway.provider = provider
    await provider.start()
    with pytest.raises(ModelError) as error:
        await gateway.generate(request())
    assert error.value.code == code and error.value.dispatched == uncertain
    assert "do not expose" not in str(error.value)
    with pytest.raises(ModelError, match="silently re-execute"):
        await gateway.generate(request())
    assert gateway.catalog()[0].health == "unavailable"


@pytest.mark.parametrize("case", ["missing_done", "missing_usage", "bad_json", "bad_tool"])
async def test_protocol_failure_is_not_success(gateway: ModelGateway, case: str) -> None:
    req = request(output_format="json" if case in {"bad_json", "bad_tool"} else "text")
    response = sse(
        frame("not json" if case == "bad_json" else "{}", "stop", case != "missing_usage"),
        done=case != "missing_done",
    )
    if case == "bad_tool":
        req = request(
            tools=[{"name": "echo", "parameters": {"type": "object"}}], tool_choice="required"
        )
    provider = ProviderFactory().create(
        ModelConfig(),
        Secrets(),
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)),
    )
    await gateway.provider.close()
    gateway.provider = provider
    await provider.start()
    with pytest.raises(ModelError) as error:
        await gateway.generate(req)
    assert error.value.dispatched
    assert error.value.code in {"stream_interrupted", "incomplete_stream", "invalid_model_output"}


async def test_fragmented_tool_arguments_and_usage_only_frame(gateway: ModelGateway) -> None:
    spec = ToolSpec(
        name="echo",
        parameters={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    frames = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {"name": "echo", "arguments": '{"value":'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"ok"}'}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        },
        {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 5}},
    ]
    provider = ProviderFactory().create(
        ModelConfig(),
        Secrets(),
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(lambda _: sse(*frames))),
    )
    await gateway.provider.close()
    gateway.provider = provider
    await provider.start()
    result = await gateway.generate(request(tools=(spec,), tool_choice="required"))
    assert result.tool_calls[0].arguments == {"value": "ok"}
    assert result.usage.input_tokens == 11


async def test_concurrent_idempotency_and_recovery_after_received(gateway: ModelGateway) -> None:
    results = await asyncio.gather(*(gateway.generate(request()) for _ in range(5)))
    assert len({result.model_dump_json() for result in results}) == 1
    # Replay after constructing another gateway over the same durable journal.
    restarted = ModelGateway(gateway.config, gateway.registry, gateway.provider, gateway.deps)
    await restarted.start()
    assert await restarted.generate(request()) == results[0]
    await restarted.close()


async def test_cancel_after_dispatch_keeps_unknown_outcome(gateway: ModelGateway) -> None:
    class Interrupted(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
            await asyncio.Event().wait()

    provider = ProviderFactory().create(
        ModelConfig(),
        Secrets(),
        lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, stream=Interrupted(), headers={"content-type": "text/event-stream"}
                )
            )
        ),
    )
    await gateway.provider.close()
    gateway.provider = provider
    await provider.start()
    async with aclosing(gateway.stream(request())) as stream:
        assert (await anext(stream)).content == "partial"
    with pytest.raises(ModelError, match="silently re-execute"):
        await gateway.generate(request())


def test_contracts_reject_invalid_tools_and_test_cloud() -> None:
    with pytest.raises(ValidationError):
        ApplicationConfig(profile="test")
    with pytest.raises(ValidationError):
        ApplicationConfig(models=ModelConfig(backend="mock"))
    with pytest.raises(ValidationError):
        ToolSpec(name="echo", parameters={"type": "object", "$ref": "https://example.test/schema"})
    with pytest.raises(ValidationError):
        request(messages=(ModelMessage(role="tool", content="orphan", tool_call_id="missing"),))


def test_catalog_and_probe_are_owner_scoped_and_test_labelled(client: TestClient) -> None:
    catalog = client.get("/api/v1/models").json()
    assert catalog[0]["health"] == "test_fixture"
    assert "secret" not in json.dumps(catalog).lower()
    path = "/api/v1/models/fixture-model/probe"
    result = client.post(path, json={"request_id": "probe-test"})
    assert result.status_code == 200
    assert result.json()["source"] == "test"
    assert client.post(path, json={"request_id": "probe-test"}).json() == result.json()
    assert (
        client.post(path, json={"request_id": "other", "principal": {"role": "user"}}).status_code
        == 422
    )


async def test_durable_received_recovers_settlement_without_provider_call(
    gateway: ModelGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = gateway.deps.control.settle
    attempts = 0

    async def fail_once(principal: Principal, identifier: str, actual: object) -> object:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("simulated storage outage after provider completion")

    monkeypatch.setattr(gateway.deps.control, "settle", fail_once)
    with pytest.raises(RuntimeError, match="simulated storage outage"):
        await gateway.generate(request())
    assert attempts == 1
    monkeypatch.setattr(gateway.deps.control, "settle", original)
    # A provider closed before replay proves no second external request is made.
    await gateway.provider.close()
    result = await gateway.generate(request())
    assert result.content == "OK"
    assert await gateway.generate(request()) == result


async def test_missing_credentials_are_reported_before_dispatch(gateway: ModelGateway) -> None:
    class Missing:
        def get(self, name: str) -> SecretStr:
            raise ApplicationError(503, "credential_missing", "not configured")

    gateway.deps = GatewayDependencies(
        gateway.deps.control, gateway.deps.events, gateway.deps.runtime, Missing()
    )
    assert gateway.catalog()[0].health == "credential_missing"
    with pytest.raises(ModelError) as error:
        await gateway.generate(request())
    assert error.value.code == "credential_missing"
    assert await gateway.deps.events.lookup(f"model:{gateway._key(request())}:started") is None


@pytest.mark.parametrize("dispatched,known_usage", [(True, False), (True, True), (False, False)])
async def test_failure_replay_preserves_dispatch_uncertainty_and_known_usage_without_new_call(
    gateway: ModelGateway, monkeypatch: pytest.MonkeyPatch, dispatched: bool, known_usage: bool
) -> None:
    from collections.abc import AsyncGenerator

    from auton.model.config import ModelSpec
    from auton.model.contracts import ModelChunk, ModelUsage

    calls = 0
    usage = (
        ModelUsage(input_tokens=12, output_tokens=3, estimated_cost_microusd=137)
        if known_usage
        else None
    )

    async def failing(req: ModelRequest, spec: ModelSpec) -> AsyncGenerator[ModelChunk, None]:
        nonlocal calls
        calls += 1
        raise ModelError(
            "synthetic_provider_failure",
            "Synthetic response failure",
            dispatched=dispatched,
            usage=usage,
        )
        yield ModelChunk(kind="delta", content="unreachable")

    monkeypatch.setattr(gateway.provider, "stream", failing)
    with pytest.raises(ModelError):
        await gateway.generate(request())
    with pytest.raises(ModelError) as replayed:
        await gateway.generate(request())
    assert calls == 1 and replayed.value.code == "request_result_unknown"
    assert replayed.value.dispatched is dispatched
    assert replayed.value.usage == usage


def test_hosted_project_context_accepts_more_than_legacy_eight_kib_but_keeps_a_cap() -> None:
    project = request(messages=[{"role": "user", "content": "project source\n" * 1000}])
    current = ModelRegistryFactory().create(ModelConfig())
    spec, reserved = current.select(project)
    assert 8192 < reserved < spec.context_tokens == 65536
    constrained = ModelRegistryFactory().create(ModelConfig(hosted_context_tokens=8192))
    with pytest.raises(ModelError) as rejected:
        constrained.select(project)
    assert rejected.value.code == "context_limit"
