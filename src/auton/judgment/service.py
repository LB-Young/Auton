import asyncio
import hashlib
import time
from dataclasses import dataclass

from anyio import CancelScope
from pydantic import JsonValue

from auton.constitution.config import ActionRequest, Usage
from auton.constitution.ports import ExecutionControlPort, PolicyControlPort
from auton.constitution.secrets import Redactor
from auton.judgment.contracts import JudgmentInfo, JudgmentRequest, JudgmentResult, RouteDecision
from auton.judgment.policy import RoutePolicy, decode
from auton.judgment.ports import JudgmentAdapterPort
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.ports import ModelGatewayPort


@dataclass(frozen=True)
class JudgmentDependencies:
    control: ExecutionControlPort
    policy: PolicyControlPort
    events: EventLogPort
    runtime: RuntimeDependencies
    models: ModelGatewayPort


class JudgmentService:
    def __init__(
        self,
        adapter: JudgmentAdapterPort,
        route: RoutePolicy,
        deps: JudgmentDependencies,
        application_enabled: bool = False,
    ) -> None:
        self.adapter, self.route, self.deps = adapter, route, deps
        self.application_enabled = application_enabled
        self._lock = asyncio.Lock()
        self.ready = False

    async def start(self) -> None:
        await self.adapter.start()
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        await self.adapter.close()

    def info(self) -> JudgmentInfo:
        return self.adapter.info().model_copy(
            update={"application_enabled": self.application_enabled}
        )

    @staticmethod
    def key(request: JudgmentRequest) -> str:
        return hashlib.sha256(
            (request.principal.owner + "\0" + request.request_id).encode()
        ).hexdigest()

    async def record(
        self, key: str, stage: str, request: JudgmentRequest, payload: dict[str, JsonValue]
    ) -> None:
        event_id = f"judgment:{key}:{stage}"
        payload = {"request_digest": request.digest, **payload}
        existing = await self.deps.events.lookup(event_id)
        if existing:
            if existing.event.payload != payload:
                raise ApplicationError(409, "judgment_conflict", "Stored decision differs")
            return
        await self.deps.events.append(
            [
                Event(
                    event_id=event_id,
                    kind=f"judgment.{stage}",
                    timestamp=self.deps.runtime.now(),
                    source="test" if self.info().backend == "mock" else "runtime",
                    scope=EventScope.model_validate(
                        {
                            "goal_id": request.goal_id,
                            "goal_revision": request.goal_revision,
                            "operation_id": request.request_id,
                        }
                    ),
                    payload=payload,
                )
            ]
        )

    async def decide(self, request: JudgmentRequest) -> JudgmentResult:
        if not self.ready:
            raise ApplicationError(503, "judgment_not_ready", "Decision service is not ready")
        if request.data_domain == "secret" or Redactor().text(request.state) != request.state:
            raise ApplicationError(
                403, "credential_in_input", "Do not place credentials in decision context"
            )
        # One local worker, bounded queue. Native timeout/cancel kills only our worker.
        if self._lock.locked():
            raise ApplicationError(429, "judgment_busy", "Local judgment worker is busy")
        async with self._lock:
            key = self.key(request)
            action = ActionRequest(
                principal=request.principal,
                goal_id=request.goal_id,
                goal_revision=request.goal_revision,
                operation_id=request.request_id,
                action="judgment.evaluate",
                data_domain=request.data_domain,
                input_digest=request.digest,
            )
            await self.deps.control.register_goal(
                request.principal, request.goal_id, request.goal_revision
            )
            await self.deps.control.validate_action(action)
            for stage in ("completed", "started"):
                stored = await self.deps.events.lookup(f"judgment:{key}:{stage}")
                if stored:
                    if stored.event.payload.get("request_digest") != request.digest:
                        raise ApplicationError(
                            409, "judgment_conflict", "Request id belongs to another decision"
                        )
                    if stage == "completed":
                        return JudgmentResult.model_validate(stored.event.payload["result"])
                    raise ApplicationError(
                        409,
                        "judgment_interrupted",
                        "Previous local decision is incomplete; use a new request id",
                    )
            # Native inference tokens are not generative billable tokens. Reserve zero cash,
            # enforce policy and shared concurrency through the same durable control plane.
            reservation = await self.deps.control.reserve(action, Usage(), request.request_id)
            if reservation.status != "reserved":
                raise ApplicationError(
                    409, "judgment_interrupted", "Previous authorization cannot dispatch"
                )
            begun = False
            received = False
            started = time.monotonic()
            policy_version = self.deps.policy.public().version
            try:
                await self.deps.control.begin(request.principal, reservation.id)
                begun = True
                await self.record(
                    key,
                    "started",
                    request,
                    {
                        "request": request.model_dump(mode="json"),
                        "policy_version": policy_version,
                        "reservation_id": reservation.id,
                        "configured_checkpoint": self.info().checkpoint,
                        "configured_revision": self.info().revision,
                    },
                )
                source, raw = await self.adapter.predict(request)
                received = True
                await self.record(
                    key, "raw", request, {"response": raw, "source": source.model_dump(mode="json")}
                )
                answers_raw = raw.get("answers")
                answers = tuple(
                    decode(q, answers_raw.get(q.id) if isinstance(answers_raw, dict) else None)
                    for q in request.questions
                )
                route = self.route.select(
                    request, answers, self.deps.models.catalog(), self.deps.policy.public()
                )
                try:
                    await self.deps.control.validate_action(action)
                    if policy_version != self.deps.policy.public().version:
                        raise ApplicationError(
                            409, "policy_changed", "Policy changed during judgment"
                        )
                except ApplicationError as error:
                    route = RouteDecision(
                        status="stale",
                        reason_codes=(error.code,),
                        policy_version=self.deps.policy.public().version,
                    )
                result = JudgmentResult(
                    request_id=request.request_id,
                    request_digest=request.digest,
                    goal_id=request.goal_id,
                    goal_revision=request.goal_revision,
                    state_cutoff=request.state_cutoff,
                    source=source,
                    answers=answers,
                    raw_event_id=f"judgment:{key}:raw",
                    route=route,
                    latency_ms=int((time.monotonic() - started) * 1000),
                )
                await self.deps.control.settle(request.principal, reservation.id, Usage())
                await self.record(
                    key, "completed", request, {"result": result.model_dump(mode="json")}
                )
                return result
            except BaseException as error:
                with CancelScope(shield=True):
                    # Local worker has no external side effects; completed or killed native work
                    # has no cash charge. The failed judgment is retained, never adopted.
                    if begun:
                        await self.deps.control.settle(request.principal, reservation.id, Usage())
                    else:
                        await self.deps.control.release(request.principal, reservation.id)
                    await self.record(
                        key,
                        "failed",
                        request,
                        {
                            "code": error.code
                            if isinstance(error, ApplicationError)
                            else "judgment_interrupted",
                            "raw_received": received,
                            "adopted": False,
                        },
                    )
                raise

    async def apply(self, request: JudgmentRequest, current_state_cutoff: int) -> JudgmentResult:
        """Trusted runtime adoption of a selection only; never dispatches the model/tool."""
        if not self.application_enabled:
            raise ApplicationError(
                403,
                "judgment_advisory_only",
                "Local judgment application needs a validated domain baseline",
            )
        async with self._lock:
            key = self.key(request)
            stored = await self.deps.events.lookup(f"judgment:{key}:completed")
            if stored is None or stored.event.payload.get("request_digest") != request.digest:
                raise ApplicationError(409, "judgment_not_found", "No matching completed judgment")
            result = JudgmentResult.model_validate(stored.event.payload["result"])
            action = ActionRequest(
                principal=request.principal,
                goal_id=request.goal_id,
                goal_revision=request.goal_revision,
                operation_id=request.request_id,
                action="judgment.evaluate",
                data_domain=request.data_domain,
                input_digest=request.digest,
            )
            try:
                await self.deps.control.validate_action(action)
                if current_state_cutoff != request.state_cutoff:
                    raise ApplicationError(
                        409, "stale_state", "Decision input is no longer current"
                    )
                current = self.route.select(
                    request, result.answers, self.deps.models.catalog(), self.deps.policy.public()
                )
                if (
                    result.route.status != "proposed"
                    or current.status != "proposed"
                    or current.model_id != result.route.model_id
                    or current.policy_version != result.route.policy_version
                ):
                    raise ApplicationError(
                        409, "route_not_applicable", "Decision is blocked or policy/model changed"
                    )
            except ApplicationError as error:
                # Rejections are observations, not permission to alter the immutable answer.
                await self.record(
                    key,
                    "application_rejected_"
                    + hashlib.sha256(
                        f"{current_state_cutoff}:{error.code}:{self.deps.policy.public().version}".encode()
                    ).hexdigest()[:24],
                    request,
                    {"code": error.code, "adopted": False},
                )
                raise
            adopted = result.model_copy(update={"adopted": True})
            await self.record(
                key,
                "adopted",
                request,
                {
                    "result": adopted.model_dump(mode="json"),
                    "policy_action": "select_executor",
                    "model_id": result.route.model_id,
                },
            )
            return adopted
