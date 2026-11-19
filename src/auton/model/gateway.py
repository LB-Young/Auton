import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass

from anyio import CancelScope
from pydantic import JsonValue

from auton.constitution.config import ActionRequest, Principal, Usage
from auton.constitution.ports import ExecutionControlPort
from auton.constitution.secrets import Redactor, SecretStorePort, StreamingRedactor
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.config import ModelConfig
from auton.model.contracts import ModelChunk, ModelInfo, ModelRequest, ModelResult, ModelUsage
from auton.model.local_provider import LocalRuntimeProvider
from auton.model.ports import ModelError, ProviderPort
from auton.model.publication_contracts import ModelAssignment
from auton.model.registry import ModelRegistry


@dataclass(frozen=True)
class GatewayDependencies:
    control: ExecutionControlPort
    events: EventLogPort
    runtime: RuntimeDependencies
    secrets: SecretStorePort


class ModelGateway:
    def __init__(
        self,
        config: ModelConfig,
        registry: ModelRegistry,
        provider: ProviderPort,
        deps: GatewayDependencies,
    ) -> None:
        self.config, self.registry, self.provider, self.deps = config, registry, provider, deps
        self._semaphore = asyncio.Semaphore(config.max_parallel)
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._active: set[asyncio.Task[object]] = set()
        self.ready = False

    async def start(self) -> None:
        await self.provider.start()
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        tasks = [task for task in self._active if task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.provider.close()

    def catalog(self, principal: Principal | None = None) -> list[ModelInfo]:
        credentials = True
        if self.config.backend != "mock":
            try:
                self.deps.secrets.get(self.config.secret_reference)
            except ApplicationError:
                credentials = False
        return self.registry.catalog(credentials, principal)

    def runtime_assignment(self, principal: Principal, goal_id: str) -> ModelAssignment | None:
        publications = self.registry.publications
        return publications.assignments.get((principal.owner, goal_id)) if publications else None

    async def resolve_model(
        self,
        principal: Principal,
        project: str,
        goal: str,
        requested: str,
        creation_digest: str = "",
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> str:
        if self.registry.publications is None:
            return requested
        result = await self.registry.publications.resolve(
            principal, project, goal, requested, creation_digest, goal_text, data_domain
        )
        spec = self.registry.models.get(result)
        if (
            requested == "project_default"
            and spec is not None
            and spec.location == "remote"
            and data_domain != "public"
        ):
            raise ApplicationError(
                403,
                "release_fallback_privacy_denied",
                "Fallback cannot send this goal to a remote model",
            )
        return result

    @staticmethod
    def request_goal(request: ModelRequest) -> str:
        if len(request.messages) < 2 or request.messages[1].content is None:
            raise ApplicationError(
                409, "local_host_state_missing", "Local runtime requires the pinned host task state"
            )
        try:
            value = json.loads(request.messages[1].content)
            if value["source"] != "host-task-state" or not isinstance(value["state"]["goal"], str):
                raise ValueError()
            return str(value["state"]["goal"])
        except (ValueError, TypeError, KeyError) as error:
            raise ApplicationError(
                409, "local_host_state_missing", "Local runtime requires the pinned host task state"
            ) from error

    async def validate_runtime(
        self,
        principal: Principal,
        model_id: str,
        goal_id: str,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> None:
        spec = self.registry.models.get(model_id)
        if spec is not None and spec.provider == "local":
            if self.registry.publications is None:
                raise ApplicationError(
                    409, "model_release_unavailable", "No approved model runtime binding"
                )
            await self.registry.publications.validate(
                principal, model_id, goal_id, spec, goal_text, data_domain
            )

    async def count_local_tokens(self, request: ModelRequest) -> tuple[int, str]:
        spec = self.registry.models.get(request.model_id)
        if spec is None:
            raise ModelError("model_not_found", "No registered local model")
        if self.registry.publications is None:
            raise ModelError("model_release_unavailable", "No approved runtime profile")
        await self.validate_runtime(
            request.principal,
            spec.id,
            request.goal_id,
            self.request_goal(request),
            request.data_domain,
        )
        if spec.provider != "local" or not isinstance(self.provider, LocalRuntimeProvider):
            raise ModelError("local_tokenizer_unavailable", "No local runtime tokenization binding")
        if (
            Redactor(
                (self.deps.secrets.get(spec.local_secret_reference or "MISSING_LOCAL_SECRET"),)
            ).text(request.model_dump_json())
            != request.model_dump_json()
        ):
            raise ApplicationError(
                403, "credential_in_input", "Credentials cannot enter tokenization"
            )
        return await self.provider.count(request, spec)

    @staticmethod
    def _key(request: ModelRequest) -> str:
        return hashlib.sha256(
            (request.principal.owner + "\0" + request.request_id).encode()
        ).hexdigest()

    async def _record(
        self, key: str, stage: str, request: ModelRequest, payload: dict[str, JsonValue]
    ) -> None:
        existing = await self.deps.events.lookup(f"model:{key}:{stage}")
        if existing is not None:
            if existing.event.payload != {"request_digest": request.digest, **payload}:
                raise ModelError("request_conflict", "Stored model event differs")
            return
        await self.deps.events.append(
            [
                Event(
                    event_id=f"model:{key}:{stage}",
                    kind=f"model.{stage}",
                    timestamp=self.deps.runtime.now(),
                    source="test" if self.config.backend == "mock" else "runtime",
                    scope=EventScope.model_validate(
                        {
                            "goal_id": request.goal_id,
                            "goal_revision": request.goal_revision,
                            "operation_id": request.request_id,
                        }
                    ),
                    payload={"request_digest": request.digest, **payload},
                )
            ]
        )

    async def _replay(self, key: str, request: ModelRequest) -> ModelResult | None:
        for stage in ("completed", "received", "failed", "started"):
            previous = await self.deps.events.lookup(f"model:{key}:{stage}")
            if previous is None:
                continue
            payload = previous.event.payload
            if payload.get("request_digest") != request.digest:
                raise ModelError(
                    "request_conflict", "Request id already belongs to different input"
                )
            if stage in {"completed", "received"}:
                result = ModelResult.model_validate(payload["result"])
                if stage == "received":
                    await self.deps.control.settle(
                        request.principal,
                        str(payload["reservation_id"]),
                        Usage(
                            tokens=result.usage.input_tokens + result.usage.output_tokens,
                            cost_microusd=result.usage.estimated_cost_microusd,
                        ),
                    )
                    await self._record(
                        key, "completed", request, {"result": result.model_dump(mode="json")}
                    )
                return result
            raise ModelError(
                "request_result_unknown",
                "Previous request was dispatched or failed; do not silently re-execute",
                dispatched=stage == "started" or payload.get("outcome") != "not_executed",
                usage=ModelUsage.model_validate(payload["usage"])
                if payload.get("usage") is not None
                else None,
            )
        return None

    async def stream(self, request: ModelRequest) -> AsyncGenerator[ModelChunk, None]:
        if not self.ready:
            raise ModelError("model_not_ready", "Model gateway is not ready")
        key = self._key(request)
        lock, users = self._locks.get(key, (asyncio.Lock(), 0))
        if key not in self._locks and len(self._locks) >= 64:
            raise ModelError("model_busy", "Too many pending model requests", retryable=True)
        self._locks[key] = (lock, users + 1)
        task = asyncio.current_task()
        if task:
            self._active.add(task)
        try:
            async with lock, self._semaphore:
                async with aclosing(self._execute(key, request)) as execution:
                    async for chunk in execution:
                        yield chunk
        finally:
            if task:
                self._active.discard(task)
            current_lock, remaining = self._locks[key]
            if remaining == 1:
                del self._locks[key]
            else:
                self._locks[key] = (current_lock, remaining - 1)

    async def _execute(self, key: str, request: ModelRequest) -> AsyncGenerator[ModelChunk, None]:
        cached = await self._replay(key, request)
        if cached is not None:
            yield ModelChunk(kind="completed", result=cached)
            return
        spec, input_estimate = self.registry.select(request)
        if spec.provider == "local":
            await self.validate_runtime(
                request.principal,
                spec.id,
                request.goal_id,
                self.request_goal(request),
                request.data_domain,
            )
        if spec.location == "remote" and request.data_domain != "public":
            raise ApplicationError(
                403, "data_egress_denied", "Private data cannot leave the machine"
            )
        try:
            known_secrets = (
                (self.deps.secrets.get(self.config.secret_reference),)
                if spec.provider == "deepseek"
                else (self.deps.secrets.get(spec.local_secret_reference or "MISSING_LOCAL_SECRET"),)
                if spec.provider == "local"
                else ()
            )
        except ApplicationError as error:
            raise ModelError(error.code, str(error), dispatched=False) from error
        redactor = Redactor(known_secrets)
        streaming_redactor = StreamingRedactor(redactor, known_secrets)
        if redactor.text(request.model_dump_json()) != request.model_dump_json():
            raise ApplicationError(
                403, "credential_in_input", "Credential-like content cannot be sent to a model"
            )
        if spec.location == "remote":
            try:
                self.deps.secrets.get(self.config.secret_reference)
            except ApplicationError as error:
                raise ModelError(
                    "credential_missing", "Provider credential is not configured"
                ) from error
        action = ActionRequest(
            principal=request.principal,
            goal_id=request.goal_id,
            goal_revision=request.goal_revision,
            operation_id=request.request_id,
            action="model.generate",
            data_domain=request.data_domain,
            destination=spec.location,
            provider=spec.provider,
            input_digest=request.digest,
        )
        await self.deps.control.register_goal(
            request.principal, request.goal_id, request.goal_revision
        )
        reservation = await self.deps.control.reserve(
            action,
            Usage(
                tokens=input_estimate + request.max_output_tokens,
                cost_microusd=spec.estimated_cost(input_estimate, request.max_output_tokens),
            ),
            request.request_id,
        )
        if reservation.status != "reserved":
            raise ModelError(
                "request_result_unknown",
                "Previous authorization is not dispatchable",
                dispatched=True,
            )
        begun = False
        result: ModelResult | None = None
        try:
            await self.deps.control.begin(request.principal, reservation.id)
            begun = True
            await self._record(
                key,
                "started",
                request,
                {
                    "request": request.model_dump(mode="json"),
                    "reservation_id": reservation.id,
                    "model_spec": spec.model_dump(mode="json"),
                    "declared_revision": spec.declared_revision,
                    "price_revision": spec.price_revision,
                },
            )
            async with asyncio.timeout(self.config.timeout_seconds):
                async with aclosing(self.provider.stream(request, spec)) as stream:
                    async for chunk in stream:
                        if chunk.kind == "completed":
                            if result is not None or chunk.result is None:
                                raise ModelError(
                                    "invalid_stream",
                                    "Invalid terminal model event",
                                    dispatched=True,
                                )
                            result = chunk.result
                        elif result is not None:
                            raise ModelError(
                                "invalid_stream", "Data arrived after completion", dispatched=True
                            )
                        else:
                            safe_delta = streaming_redactor.feed(chunk.content)
                            if safe_delta:
                                yield ModelChunk(kind="delta", content=safe_delta)
            if result is None:
                raise ModelError(
                    "incomplete_stream", "No model completion received", dispatched=True
                )
            remainder = streaming_redactor.finish()
            if remainder:
                yield ModelChunk(kind="delta", content=remainder)
            safe = redactor.redact(result.model_dump(mode="json"))
            redacted = safe != result.model_dump(mode="json")
            result = ModelResult.model_validate(safe).model_copy(update={"redacted": redacted})
            await self._record(
                key,
                "received",
                request,
                {
                    "result": result.model_dump(mode="json"),
                    "reservation_id": reservation.id,
                },
            )
            await self.deps.control.settle(
                request.principal,
                reservation.id,
                Usage(
                    tokens=result.usage.input_tokens + result.usage.output_tokens,
                    cost_microusd=result.usage.estimated_cost_microusd,
                ),
            )
            await self._record(
                key, "completed", request, {"result": result.model_dump(mode="json")}
            )
            self.registry.health[spec.id] = "available"
            yield ModelChunk(kind="completed", result=result)
        except BaseException as error:
            with CancelScope(shield=True):
                if result is None:
                    known = isinstance(error, ModelError) and not error.dispatched
                    usage = error.usage if isinstance(error, ModelError) else None
                    if not begun:
                        await self.deps.control.release(request.principal, reservation.id)
                    elif known or usage is not None:
                        await self.deps.control.settle(
                            request.principal,
                            reservation.id,
                            Usage(
                                tokens=usage.input_tokens + usage.output_tokens if usage else 0,
                                cost_microusd=usage.estimated_cost_microusd if usage else 0,
                            ),
                        )
                    await self._record(
                        key,
                        "failed",
                        request,
                        {
                            "code": error.code
                            if isinstance(error, ApplicationError)
                            else "request_interrupted",
                            "outcome": "not_executed" if known or not begun else "unknown",
                            "usage": usage.model_dump(mode="json") if usage is not None else None,
                        },
                    )
            self.registry.health[spec.id] = "unavailable"
            if isinstance(error, TimeoutError):
                raise ModelError(
                    "provider_timeout",
                    "Model deadline exceeded; request result uncertain",
                    dispatched=True,
                ) from error
            raise

    async def generate(self, request: ModelRequest) -> ModelResult:
        result = None
        async with aclosing(self.stream(request)) as stream:
            async for chunk in stream:
                if chunk.result:
                    result = chunk.result
        if result is None:
            raise ModelError("incomplete_stream", "No terminal result received", dispatched=True)
        return result
