import asyncio
import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Literal, cast

import httpx
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError

from auton.constitution.secrets import SecretStorePort
from auton.model.config import ModelConfig, ModelSpec
from auton.model.contracts import ModelChunk, ModelRequest, ModelResult, ModelUsage, ToolCall
from auton.model.ports import ModelError


@dataclass
class StreamState:
    content: str = ""
    reported_model: str = ""
    fingerprint: str | None = None
    finish: str | None = None
    usage: ModelUsage | None = None
    tools: dict[int, dict[str, str]] = field(default_factory=dict)


def parse_frame(raw: str, state: StreamState, spec: ModelSpec) -> str:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or "error" in value:
            raise ValueError("Invalid stream frame")
        if isinstance(value.get("model"), str):
            reported = value["model"]
            if state.reported_model and reported != state.reported_model:
                raise ValueError("Model changed during stream")
            state.reported_model = reported
        if isinstance(value.get("system_fingerprint"), str):
            state.fingerprint = value["system_fingerprint"]
        if value.get("usage") is not None:
            usage = value["usage"]
            state.usage = ModelUsage(
                input_tokens=usage["prompt_tokens"],
                output_tokens=usage["completion_tokens"],
                estimated_cost_microusd=spec.estimated_cost(
                    usage["prompt_tokens"], usage["completion_tokens"]
                ),
            )
        delta_text = ""
        for choice in value.get("choices", []):
            if choice.get("index", 0) != 0:
                raise ValueError("Multiple candidates are unsupported")
            delta = choice.get("delta", {})
            text = delta.get("content") or ""
            if not isinstance(text, str):
                raise ValueError("Invalid text delta")
            delta_text += text
            state.content += text
            if len(state.content) > 128000:
                raise ValueError("Output size limit exceeded")
            for tool in delta.get("tool_calls") or []:
                index = tool["index"]
                if not isinstance(index, int) or not 0 <= index < 16:
                    raise ValueError("Invalid tool index")
                existing = state.tools.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if tool.get("id"):
                    if existing["id"] and existing["id"] != tool["id"]:
                        raise ValueError("Tool identity changed")
                    existing["id"] = tool["id"]
                function = tool.get("function") or {}
                existing["name"] += function.get("name") or ""
                existing["arguments"] += function.get("arguments") or ""
                if len(existing["arguments"]) > 32000 or len(existing["name"]) > 64:
                    raise ValueError("Tool output size limit exceeded")
            if choice.get("finish_reason") is not None:
                if not isinstance(choice["finish_reason"], str):
                    raise ValueError("Invalid completion marker")
                state.finish = choice["finish_reason"]
        return delta_text
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError) as error:
        raise ModelError(
            "invalid_stream", "Provider returned an invalid stream", dispatched=True
        ) from error


def finalize(
    state: StreamState, request: ModelRequest, spec: ModelSpec, started: float
) -> ModelResult:
    if state.usage is None or state.finish not in {"stop", "tool_calls", "length"}:
        raise ModelError(
            "incomplete_stream", "Missing final usage or completion marker", dispatched=True
        )
    calls = []
    registered = {tool.name: tool for tool in request.tools}
    try:
        for value in state.tools.values():
            name = value["name"]
            if not value["id"] or name not in registered:
                raise ValueError("Unregistered tool call")
            arguments = json.loads(value["arguments"])
            Draft202012Validator(registered[name].parameters).validate(arguments)
            calls.append(ToolCall(id=value["id"], name=name, arguments=arguments))
        if bool(calls) != (state.finish == "tool_calls"):
            raise ValueError("Tool finish reason mismatch")
        if request.tool_choice == "required" and not calls:
            raise ValueError("Required tool call was not returned")
        if (
            request.output_format == "json"
            and not calls
            and not isinstance(json.loads(state.content), dict)
        ):
            raise ValueError("Expected a JSON object")
    except (ValueError, TypeError, SchemaValidationError, ValidationError) as error:
        raise ModelError(
            "invalid_model_output",
            "Output failed the requested protocol",
            dispatched=True,
            usage=state.usage,
        ) from error
    return ModelResult(
        request_id=request.request_id,
        model_id=spec.id,
        reported_model=state.reported_model or spec.id,
        system_fingerprint=state.fingerprint,
        content=state.content,
        tool_calls=tuple(calls),
        finish_reason=cast(Literal["stop", "tool_calls", "length"], state.finish),
        usage=state.usage,
        source="remote",
        latency_ms=int((time.monotonic() - started) * 1000),
    )


class DeepSeekProvider:
    def __init__(
        self,
        config: ModelConfig,
        secrets: SecretStorePort,
        client_factory: Callable[[], httpx.AsyncClient],
    ) -> None:
        self.config, self.secrets, self.client_factory = config, secrets, client_factory
        self.client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self.client is None:
            self.client = self.client_factory()

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()
            self.client = None

    async def stream(
        self, request: ModelRequest, spec: ModelSpec
    ) -> AsyncGenerator[ModelChunk, None]:
        if self.client is None:
            raise ModelError("model_not_ready", "Provider has not started")
        secret = self.secrets.get(self.config.secret_reference)
        payload: dict[str, object] = {
            "model": spec.id,
            "messages": [message.wire() for message in request.messages],
            "max_tokens": request.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "thinking": {"type": "disabled"},
        }
        if request.output_format == "json":
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = [
                {"type": "function", "function": tool.model_dump()} for tool in request.tools
            ]
            payload["tool_choice"] = request.tool_choice
        state = StreamState()
        started = time.monotonic()
        done = False
        try:
            async with self.client.stream(
                "POST",
                "https://api.deepseek.com/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer " + secret.get_secret_value()},
            ) as response:
                if response.status_code != 200:
                    code = {
                        401: "credential_rejected",
                        402: "balance_insufficient",
                        404: "model_not_found",
                        429: "rate_limited",
                        400: "provider_rejected",
                    }.get(response.status_code, "provider_unavailable")
                    raise ModelError(
                        code,
                        f"Provider rejected request (HTTP {response.status_code})",
                        retryable=response.status_code in {429, 500, 502, 503},
                        dispatched=response.status_code >= 500,
                    )
                if "text/event-stream" not in response.headers.get("content-type", ""):
                    raise ModelError(
                        "invalid_stream", "Provider did not return SSE", dispatched=True
                    )
                data: list[str] = []
                async for line in response.aiter_lines():
                    if len(line) > 256000:
                        raise ModelError(
                            "invalid_stream", "Provider frame exceeds size limit", dispatched=True
                        )
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        raw, data = "\n".join(data), []
                        if raw == "[DONE]":
                            done = True
                            break
                        text = parse_frame(raw, state, spec)
                        if text:
                            yield ModelChunk(kind="delta", content=text)
                if data:
                    raw = "\n".join(data)
                    if raw == "[DONE]":
                        done = True
                    else:
                        text = parse_frame(raw, state, spec)
                        if text:
                            yield ModelChunk(kind="delta", content=text)
            if not done:
                raise ModelError(
                    "stream_interrupted",
                    "Stream ended without DONE",
                    dispatched=True,
                    usage=state.usage,
                )
            result = finalize(state, request, spec, started)
            yield ModelChunk(kind="completed", result=result)
        except (httpx.ConnectError, httpx.ConnectTimeout) as error:
            raise ModelError(
                "provider_unreachable", "Cannot connect to provider", retryable=True
            ) from error
        except httpx.TimeoutException as error:
            raise ModelError(
                "provider_timeout",
                "Provider timed out; result is uncertain",
                dispatched=True,
                usage=state.usage,
            ) from error
        except httpx.HTTPError as error:
            raise ModelError(
                "stream_interrupted",
                "Provider transport failed",
                dispatched=True,
                usage=state.usage,
            ) from error


class MockProvider:
    def __init__(self, scenario: str = "baseline") -> None:
        self.scenario = scenario

    def agent_fixture(self, request: ModelRequest) -> tuple[str, tuple[ToolCall, ...]]:
        state: dict[str, object] = {}
        sources: list[str] = []
        for message in request.messages:
            if message.role != "user" or not message.content:
                continue
            try:
                value = json.loads(message.content)
            except ValueError:
                continue
            if not isinstance(value, dict):
                continue
            if value.get("source") == "host-task-state" and not state:
                state = value.get("state", {})
            if value.get("source") == "retrieved-evidence":
                sources.extend(value.get("asset_ids", []))
        delivery = state.get("delivery", {})
        if isinstance(delivery, dict) and delivery.get("kind") == "file":
            if any(m.role == "tool" for m in request.messages):
                return "[TEST FIXTURE] The host must verify the file digest.", ()
            return "", (
                ToolCall(
                    id="fixture-write",
                    name="file_write",
                    arguments={"path": str(delivery.get("path", "notes.md")), "content": "hello\n"},
                ),
            )
        text = (
            "[TEST FIXTURE] Context retrieval preserves project boundaries and source provenance. "
            * 3
        )
        return text + " ".join("[asset:" + source + "]" for source in sorted(set(sources))), ()

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def stream(
        self, request: ModelRequest, spec: ModelSpec
    ) -> AsyncGenerator[ModelChunk, None]:
        content = (
            '{"ok":true}'
            if request.output_format == "json"
            else "[测试模型] " + str(request.messages[-1].content)[:80]
        )
        calls: tuple[ToolCall, ...] = ()
        if request.tools and request.tool_choice == "required":
            content = ""
            calls = (
                ToolCall(
                    id="fixture-tool", name=request.tools[0].name, arguments={"value": "fixture"}
                ),
            )
        if self.scenario == "agent_acceptance" and request.goal_id.startswith("agent-goal-"):
            content, calls = self.agent_fixture(request)
        for offset in range(0, len(content), 5):
            await asyncio.sleep(0)
            yield ModelChunk(kind="delta", content=content[offset : offset + 5])
        yield ModelChunk(
            kind="completed",
            result=ModelResult(
                request_id=request.request_id,
                model_id=spec.id,
                reported_model="fixture-v1",
                content=content,
                tool_calls=calls,
                finish_reason="tool_calls" if calls else "stop",
                usage=ModelUsage(input_tokens=10, output_tokens=5),
                source="test",
                latency_ms=0,
            ),
        )
