import asyncio
import copy
from dataclasses import dataclass, field

from pydantic import JsonValue

from auton.constitution.config import (
    ActionRequest,
    ConstitutionConfig,
    PolicyDecision,
    Principal,
    PublicPolicy,
    Usage,
)
from auton.constitution.contracts import Approval, Goal, Reservation
from auton.constitution.policy import PolicyEvaluatorFactory
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError


@dataclass
class ControlState:
    config: ConstitutionConfig
    sequence: int = 0
    seed_version: str = ""
    goals: dict[str, Goal] = field(default_factory=dict)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    approvals: dict[str, Approval] = field(default_factory=dict)


def control_error(code: str) -> ApplicationError:
    return ApplicationError(
        409 if code in {"stale_revision", "control_conflict"} else 403, code, code
    )


def apply(state: ControlState, operation: str, value: dict[str, JsonValue]) -> None:
    if operation == "load":
        state.config = ConstitutionConfig.model_validate(value["config"])
        state.seed_version = str(value["seed"])
    elif operation == "configure":
        state.config = ConstitutionConfig.model_validate(value)
    elif operation in {"goal", "cancel", "revise"}:
        state.goals[str(value["id"])] = Goal.model_validate(value["goal"])
    elif operation in {"reserve", "begin", "settle", "release", "recover"}:
        item = Reservation.model_validate(value)
        state.reservations[item.id] = item
    elif operation == "approve":
        approval = Approval.model_validate(value)
        state.approvals[approval.id] = approval
    else:
        raise ValueError("Unknown control operation")


class ConstitutionService:
    def __init__(
        self,
        config: ConstitutionConfig,
        events: EventLogPort,
        deps: RuntimeDependencies,
    ) -> None:
        self.initial = config
        self.events, self.deps = events, deps
        self.state = ControlState(config)
        self._lock = asyncio.Lock()
        self.ready = False

    async def _replay(self) -> None:
        state = ControlState(self.initial)
        after = 0
        while rows := await self.events.read(after=after, limit=1000):
            for row in rows:
                if row.event.kind.startswith("control."):
                    expected = state.sequence + 1
                    if row.event.event_id != f"control:{expected}":
                        raise control_error("control_journal_invalid")
                    apply(state, row.event.kind.removeprefix("control."), row.event.payload)
                    state.sequence = expected
            after = rows[-1].cursor
        self.state = state

    async def start(self) -> None:
        async with self._lock:
            await self._replay()
            if self.state.sequence == 0 or self.state.seed_version != self.initial.version:
                await self._write(
                    "load",
                    {"seed": self.initial.version, "config": self.initial.model_dump(mode="json")},
                )
            # An interrupted dispatch is not refunded; actual consumption needs reconciliation.
            for item in list(self.state.reservations.values()):
                if item.status == "started":
                    await self._write(
                        "recover",
                        item.model_copy(update={"status": "unknown"}).model_dump(mode="json"),
                    )
            self.ready = True

    async def close(self) -> None:
        self.ready = False

    async def _write(self, operation: str, value: dict[str, JsonValue]) -> None:
        candidate = copy.deepcopy(self.state)
        apply(candidate, operation, value)
        sequence = self.state.sequence + 1
        request = value.get("request")
        goal = value.get("goal")
        scope = EventScope()
        if isinstance(request, dict):
            scope = EventScope.model_validate(
                {
                    "goal_id": request["goal_id"],
                    "goal_revision": request["goal_revision"],
                    "operation_id": request["operation_id"],
                }
            )
        elif isinstance(goal, dict):
            scope = EventScope.model_validate(
                {"goal_id": value["id"], "goal_revision": goal["revision"]}
            )
        event = Event(
            event_id=f"control:{sequence}",
            kind=f"control.{operation}",
            source="system",
            timestamp=self.deps.now(),
            payload=value,
            scope=scope,
        )
        try:
            await self.events.append([event])
        except StorageError as error:
            stored = await self.events.lookup(event.event_id)
            if error.outcome == "unknown" and stored and stored.event.digest() == event.digest():
                pass  # Commit proved by stable event identity, not guessed.
            else:
                await self._replay()
                raise control_error("control_conflict") from error
        candidate.sequence = sequence
        self.state = candidate

    def _check(self) -> None:
        if not self.ready:
            raise ApplicationError(503, "control_not_ready", "Control service is not ready")

    def public(self) -> PublicPolicy:
        self._check()
        config = self.state.config
        return PublicPolicy(
            version=config.version,
            allowed_actions=config.allowed_actions,
            remote_providers=config.remote_providers,
            approval_actions=config.approval_actions,
            autonomy_max=config.autonomy_max,
            budget_per_goal=config.budget,
            max_concurrent=config.max_concurrent,
        )

    def preview(self, request: ActionRequest) -> PolicyDecision:
        self._check()
        return PolicyEvaluatorFactory().create(self.state.config).evaluate(request)

    def _goal(self, principal: Principal, goal_id: str, revision: int | None = None) -> Goal:
        self._check()
        goal = self.state.goals.get(goal_id)
        if goal is None or goal.owner != principal.owner:
            raise control_error("goal_not_authorized")
        if revision is not None and goal.revision != revision:
            raise control_error("stale_revision")
        return goal

    async def register_goal(self, principal: Principal, goal_id: str, revision: int = 1) -> None:
        async with self._lock:
            self._check()
            if goal_id in self.state.goals:
                self._goal(principal, goal_id, revision)
                return
            if revision < 1 or not goal_id or len(goal_id) > 200:
                raise ValueError("Invalid goal identity")
            await self._write(
                "goal",
                {
                    "id": goal_id,
                    "goal": Goal(owner=principal.owner, revision=revision).model_dump(mode="json"),
                },
            )

    async def revise_goal(self, principal: Principal, goal_id: str, expected_revision: int) -> int:
        async with self._lock:
            if principal.role != "user":
                raise control_error("human_required")
            goal = self._goal(principal, goal_id, expected_revision)
            revised = goal.model_copy(update={"revision": goal.revision + 1, "cancelled": False})
            await self._write("revise", {"id": goal_id, "goal": revised.model_dump(mode="json")})
            return revised.revision

    async def cancel(self, principal: Principal, goal_id: str, revision: int) -> None:
        async with self._lock:
            goal = self._goal(principal, goal_id, revision)
            await self._write(
                "cancel",
                {
                    "id": goal_id,
                    "goal": goal.model_copy(update={"cancelled": True}).model_dump(mode="json"),
                },
            )

    async def reconfigure(
        self,
        principal: Principal,
        config: ConstitutionConfig,
        expected_version: str,
    ) -> str:
        async with self._lock:
            self._check()
            if principal.role != "user":
                raise control_error("human_required")
            if expected_version != self.state.config.version:
                raise control_error("stale_revision")
            await self._write("configure", config.model_dump(mode="json"))
            return config.version

    async def approve(self, principal: Principal, request: ActionRequest) -> Approval:
        async with self._lock:
            if principal.role != "user" or principal.owner != request.principal.owner:
                raise control_error("human_required")
            goal = self._goal(principal, request.goal_id, request.goal_revision)
            if goal.cancelled:
                raise control_error("goal_cancelled")
            decision = PolicyEvaluatorFactory().create(self.state.config).evaluate(request)
            if decision.outcome == "deny":
                raise control_error(decision.reason_codes[0])
            approval = Approval(
                id=self.deps.new_id(),
                request=request,
                policy_version=self.state.config.version,
                expires_at=self.deps.now().timestamp()
                + self.state.config.authorization_ttl_seconds,
            )
            await self._write("approve", approval.model_dump(mode="json"))
            return approval

    def _authorize(self, request: ActionRequest, approval_id: str | None = None) -> None:
        goal = self._goal(request.principal, request.goal_id, request.goal_revision)
        if goal.cancelled:
            raise control_error("goal_cancelled")
        decision = PolicyEvaluatorFactory().create(self.state.config).evaluate(request)
        if decision.outcome == "deny":
            raise control_error(decision.reason_codes[0])
        if decision.outcome == "approval_required":
            approval = self.state.approvals.get(approval_id or "")
            if (
                approval is None
                or approval.request.fingerprint != request.fingerprint
                or approval.policy_version != self.state.config.version
                or approval.expires_at <= self.deps.now().timestamp()
            ):
                raise control_error("approval_required")

    async def reserve(
        self,
        request: ActionRequest,
        estimate: Usage,
        request_id: str,
        approval_id: str | None = None,
    ) -> Reservation:
        async with self._lock:
            self._authorize(request, approval_id)
            if not request_id or len(request_id) > 200 or request.operation_id != request_id:
                raise ValueError("Invalid request id")
            held, spent, active = Usage(), Usage(), 0
            for item in self.state.reservations.values():
                if item.request.goal_id != request.goal_id:
                    continue
                if item.request_id == request_id:
                    if item.request != request or item.estimate != estimate:
                        raise control_error("request_conflict")
                    return item
                if item.status == "settled":
                    spent = spent.plus(item.actual)
                if item.status in {"reserved", "started", "unknown"}:
                    held, active = held.plus(item.estimate), active + 1
            if held.plus(spent).plus(estimate).exceeds(self.state.config.budget):
                raise control_error("budget_exceeded")
            if active >= self.state.config.max_concurrent:
                raise control_error("concurrency_exceeded")
            reservation = Reservation(
                id=self.deps.new_id(),
                request_id=request_id,
                request=request,
                approval_id=approval_id,
                estimate=estimate,
                policy_version=self.state.config.version,
                expires_at=self.deps.now().timestamp()
                + self.state.config.authorization_ttl_seconds,
            )
            await self._write("reserve", reservation.model_dump(mode="json"))
            return reservation

    def _reservation(self, principal: Principal, identifier: str) -> Reservation:
        self._check()
        item = self.state.reservations.get(identifier)
        if (
            item is None
            or item.request.principal.owner != principal.owner
            or (principal.role != "user" and item.request.principal != principal)
        ):
            raise control_error("reservation_not_authorized")
        return item

    async def begin(self, principal: Principal, identifier: str) -> Reservation:
        async with self._lock:
            item = self._reservation(principal, identifier)
            goal = self._goal(principal, item.request.goal_id, item.request.goal_revision)
            if goal.cancelled or item.policy_version != self.state.config.version:
                raise control_error("authorization_revoked")
            if item.status != "reserved" or item.expires_at <= self.deps.now().timestamp():
                raise control_error("authorization_not_dispatchable")
            self._authorize(item.request, item.approval_id)
            begun = item.model_copy(update={"status": "started"})
            await self._write("begin", begun.model_dump(mode="json"))
            return begun

    async def settle(self, principal: Principal, identifier: str, actual: Usage) -> Reservation:
        async with self._lock:
            item = self._reservation(principal, identifier)
            if item.status == "settled" and item.actual == actual:
                return item
            if item.status not in {"started", "unknown"}:
                raise control_error("settlement_conflict")
            settled = item.model_copy(update={"status": "settled", "actual": actual})
            # Actual overrun is charged, not erased; subsequent reservations fail the budget gate.
            await self._write("settle", settled.model_dump(mode="json"))
            return settled

    async def release(self, principal: Principal, identifier: str) -> Reservation:
        async with self._lock:
            item = self._reservation(principal, identifier)
            if item.status == "released":
                return item
            if item.status != "reserved":
                raise control_error("reconciliation_required")
            released = item.model_copy(update={"status": "released"})
            await self._write("release", released.model_dump(mode="json"))
            return released
