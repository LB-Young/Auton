"""Auton local-runtime-v1 adapter; no inherited cloud Authorization header or redirects."""

import json
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from auton.constitution.secrets import SecretStorePort
from auton.model.config import ModelSpec
from auton.model.contracts import ModelChunk, ModelRequest, ModelUsage
from auton.model.ports import ModelError, ProviderPort
from auton.model.provider import StreamState, finalize


class LocalRuntimeProvider:
    def __init__(self, fallback: ProviderPort, secrets: SecretStorePort) -> None:
        self.secrets = secrets
        self.fallback = fallback
        self.client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        await self.fallback.start()
        self.client = httpx.AsyncClient(timeout=45, follow_redirects=False, trust_env=False)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()
        await self.fallback.close()

    async def post(self, spec: ModelSpec, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.client is None or spec.endpoint is None:
            raise ModelError("local_runtime_unavailable", "Local runtime is not configured")
        if spec.local_secret_reference is None:
            raise ModelError(
                "local_runtime_credential_missing", "Dedicated local runtime credential required"
            )
        secret = self.secrets.get(spec.local_secret_reference)
        try:
            response = await self.client.post(
                spec.endpoint + path,
                json=body,
                headers={"Authorization": "Bearer " + secret.get_secret_value()},
            )
        except httpx.HTTPError as error:
            raise ModelError(
                "local_runtime_unavailable",
                "Local runtime is unavailable",
                dispatched=path == "/auton/generate"
                and not isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout)),
            ) from error
        if response.status_code != 200 or len(response.content) > 256000:
            raise ModelError(
                "local_runtime_rejected",
                "Local runtime rejected the request",
                dispatched=path == "/auton/generate",
            )
        try:
            value: dict[str, Any] = response.json()
            if not isinstance(value, dict):
                raise ValueError()
        except ValueError as error:
            raise ModelError(
                "local_runtime_protocol",
                "Local runtime returned invalid JSON",
                dispatched=path == "/auton/generate",
            ) from error
        if value.get("fingerprint") != spec.expected_fingerprint:
            raise ModelError(
                "local_runtime_changed",
                "Loaded deployment fingerprint changed",
                dispatched=path == "/auton/generate",
            )
        return value

    async def count(self, request: ModelRequest, spec: ModelSpec) -> tuple[int, str]:
        value = await self.post(
            spec,
            "/auton/token-count",
            {"request": request.model_dump(mode="json"), "request_digest": request.digest},
        )
        count = value.get("tokens")
        if type(count) is not int or count < 1 or value.get("request_digest") != request.digest:
            raise ModelError("local_tokenizer_protocol", "Exact tokenization response is invalid")
        return count, "local-runtime:" + str(spec.expected_fingerprint)

    async def stream(
        self, request: ModelRequest, spec: ModelSpec
    ) -> AsyncGenerator[ModelChunk, None]:
        if spec.provider != "local":
            async for chunk in self.fallback.stream(request, spec):
                yield chunk
            return
        started = time.monotonic()
        try:
            value = await self.post(
                spec,
                "/auton/generate",
                {"request": request.model_dump(mode="json"), "request_digest": request.digest},
            )
            if value.get("request_digest") != request.digest or value.get("model_id") != spec.id:
                raise ModelError(
                    "local_runtime_response_scope",
                    "Local response belongs to another request",
                    dispatched=True,
                )
            if (
                type(value.get("input_tokens")) is not int
                or type(value.get("output_tokens")) is not int
                or value["input_tokens"] < 1
                or not 0 < value["output_tokens"] <= request.max_output_tokens
                or value["input_tokens"] + value["output_tokens"] > spec.context_tokens
            ):
                raise ValueError("local_usage_outside_budget")
            state = StreamState(
                content=value["content"],
                reported_model=spec.id,
                fingerprint=value["fingerprint"],
                finish=value["finish_reason"],
                usage=ModelUsage(
                    input_tokens=value["input_tokens"],
                    output_tokens=value["output_tokens"],
                    estimated_cost_microusd=spec.estimated_cost(
                        value["input_tokens"], value["output_tokens"]
                    ),
                ),
            )
            state.tools = {
                i: {"id": t["id"], "name": t["name"], "arguments": json.dumps(t["arguments"])}
                for i, t in enumerate(value.get("tool_calls", []))
            }
            result = finalize(state, request, spec, started)
            if result.content:
                yield ModelChunk(kind="delta", content=result.content)
            yield ModelChunk(kind="completed", result=result)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ModelError(
                "local_runtime_protocol",
                "Local runtime did not return a verified result",
                dispatched=True,
            ) from error
