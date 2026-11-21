import asyncio
import hashlib
from dataclasses import dataclass
from typing import Literal

from pydantic import JsonValue, ValidationError

from auton.agent.contracts import AgentRun, RunCommand, checkpoint_event_id
from auton.agent.ports import AgentRuntimePort
from auton.constitution.config import Principal
from auton.context.ports import ContextEnginePort
from auton.experience.contracts import (
    EpisodeSummary,
    ExperienceConfig,
    RecoveryCommand,
    TraceEdge,
    TraceNode,
    Trajectory,
)
from auton.experience.ports import ProjectionPort
from auton.experience.repository import CheckpointRepositoryPort
from auton.genome.ports import AssetReadPort
from auton.kernel.events import Event, EventScope, StoredEvent
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class ExperienceDependencies:
    events: EventLogPort
    agent: AgentRuntimePort
    assets: AssetReadPort
    context: ContextEnginePort
    runtime: RuntimeDependencies


class ExperienceService:
    def __init__(
        self,
        config: ExperienceConfig,
        deps: ExperienceDependencies,
        projection: ProjectionPort,
        checkpoints: CheckpointRepositoryPort,
    ) -> None:
        self.config, self.deps, self.projection, self.checkpoints = (
            config,
            deps,
            projection,
            checkpoints,
        )
        self.lock = asyncio.Lock()
        self.ready = False

    async def start(self) -> None:
        await self.projection.start()
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        await self.projection.close()

    @staticmethod
    def actor(principal: Principal) -> Principal:
        if principal.role != "user":
            raise ApplicationError(
                403,
                "trajectory_purpose_denied",
                (
                    "Only user inspection/recovery is available; "
                    "training export requires separate gates"
                ),
            )
        return principal.model_copy(update={"role": "runtime"})

    async def catch_up(self) -> bool:
        if not self.ready:
            raise ApplicationError(503, "experience_not_ready", "Trajectory service is unavailable")
        async with self.lock:
            remaining = self.config.max_catchup_events
            while remaining > 0:
                rows = await self.deps.events.read(
                    after=await self.projection.position(),
                    limit=min(self.config.batch_size, remaining),
                )
                if not rows:
                    return True
                await self.projection.apply(rows, self.deps.runtime.now().isoformat())
                remaining -= len(rows)
            return not await self.deps.events.read(after=await self.projection.position(), limit=1)

    async def rebuild(self, principal: Principal) -> None:
        self.actor(principal)
        if not self.ready:
            raise ApplicationError(503, "experience_not_ready", "Trajectory service is unavailable")
        async with self.lock:
            await self.projection.rebuild()
        await self.catch_up()

    @staticmethod
    def details(event: Event) -> dict[str, JsonValue]:
        payload = event.payload
        if event.kind == "agent.checkpoint":
            raw = payload.get("run", {})
            if isinstance(raw, dict):
                return {
                    key: raw[key]
                    for key in (
                        "status",
                        "phase",
                        "version",
                        "goal_revision",
                        "runtime_revision",
                        "reason",
                        "tokens_used",
                        "cost_microusd",
                        "check",
                        "input_cutoff_unit",
                        "executor_selection",
                    )
                    if key in raw
                }
        if event.kind == "context.snapshot":
            raw = payload.get("snapshot", {})
            if isinstance(raw, dict):
                return {
                    key: raw[key]
                    for key in (
                        "id",
                        "status",
                        "reasons",
                        "model_id",
                        "declared_model_revision",
                        "policy_version",
                        "asset_snapshot_id",
                        "input_tokens",
                        "admission_tokens",
                        "tokenizer_revision",
                        "state_cutoff",
                    )
                    if key in raw
                }
        if event.kind.startswith("judgment."):
            return {
                key: payload[key]
                for key in (
                    "request_digest",
                    "source",
                    "answers",
                    "route",
                    "adopted",
                    "reason",
                    "code",
                )
                if key in payload
            }
        if event.kind.startswith("model."):
            raw = payload.get("result", {})
            result = {
                key: raw[key]
                for key in (
                    "request_id",
                    "reported_model",
                    "system_fingerprint",
                    "usage",
                    "source",
                    "finish_reason",
                )
                if isinstance(raw, dict) and key in raw
            }
            result.update(
                {
                    key: payload[key]
                    for key in (
                        "request_digest",
                        "model_spec",
                        "declared_revision",
                        "reservation_id",
                        "code",
                    )
                    if key in payload
                }
            )
            return result
        if event.kind.startswith("tool."):
            raw = payload.get("receipt", {})
            result = {
                key: raw[key]
                for key in (
                    "operation_id",
                    "outcome",
                    "code",
                    "attempt",
                    "reconciled",
                    "evidence",
                    "artifact",
                )
                if isinstance(raw, dict) and key in raw
            }
            result.update(
                {
                    key: payload[key]
                    for key in ("request_digest", "reservation_id", "code")
                    if key in payload
                }
            )
            return result
        if event.kind.startswith("control."):
            return {
                key: payload[key]
                for key in ("id", "status", "estimate", "actual", "policy_version", "expires_at")
                if key in payload
            }
        return {}

    async def trajectory(
        self, principal: Principal, project: str, run_id: str, purpose: str = "inspect"
    ) -> Trajectory:
        runtime = self.actor(principal)
        if purpose not in {"inspect", "recovery"}:
            raise ApplicationError(
                403, "trajectory_purpose_denied", "Training/export is not an inspection purpose"
            )
        await self.checkpoints.owned_seed(principal, project, run_id)
        await self.deps.assets.view(runtime, project)
        incompatible = False
        try:
            run = await self.deps.agent.get(principal, run_id)
        except ValidationError:
            run = None
            incompatible = True
        except ApplicationError as error:
            if error.code != "agent_checkpoint_schema_incompatible":
                raise
            run = None
            incompatible = True
        caught_up = await self.catch_up()
        reference = await self.projection.checkpoint(run_id)
        missing: list[str] = []
        reasons: list[str] = []
        if reference is None:
            reasons.append("checkpoint_projection_missing")
        elif not await self.checkpoints.valid(principal, project, reference):
            reasons.append("checkpoint_reference_invalid")
        if incompatible or (
            reference
            and reference.runtime_revision
            not in {"single-agent-v1", "single-agent-v2", "single-agent-v3"}
        ):
            reasons.append("checkpoint_schema_incompatible")
        if not caught_up or (reference and run and reference.version != run.version):
            reasons.append("projection_behind")
        operation_ids: set[str] = set()
        base = await self.projection.select(
            run_id, "agent-goal-" + run_id, (), self.config.max_trace_events + 1
        )
        for entry in base:
            if entry.kind != "agent.checkpoint":
                continue
            original = await self.deps.events.lookup(entry.event_id)
            if (
                original is None
                or original.event.digest() != entry.digest
                or original.event.scope.run_id != run_id
            ):
                continue
            try:
                historical = AgentRun.model_validate(original.event.payload["run"])
            except ValidationError:
                continue
            if (
                original.event.event_id
                != checkpoint_event_id(principal.owner, run_id, historical.version)
                or historical.command.project_id != project
            ):
                continue
            operation_ids.update(p.operation_id for p in historical.plans)
            operation_ids.update(r.operation_id for r in historical.receipts)
        operations = tuple(sorted(value for op in operation_ids for value in (op, "tool-" + op)))
        indexed = await self.projection.select(
            run_id, "agent-goal-" + run_id, operations, self.config.max_trace_events + 1
        )
        if len(indexed) > self.config.max_trace_events:
            reasons.append("trace_limit")
            indexed = indexed[: self.config.max_trace_events]
        facts: list[tuple[StoredEvent, str]] = []
        for entry in indexed:
            stored = await self.deps.events.lookup(entry.event_id)
            if (
                stored is None
                or stored.event.digest() != entry.digest
                or stored.cursor != entry.cursor
            ):
                missing.append(entry.event_id)
            elif not (
                stored.event.scope.run_id == run_id
                or stored.event.scope.goal_id == "agent-goal-" + run_id
                or str(stored.event.scope.operation_id) in operations
            ):
                missing.append("projection_scope_mismatch:" + entry.event_id)
            else:
                facts.append((stored, entry.processed_at))
        nodes: list[TraceNode] = []
        edges: list[TraceEdge] = []
        contexts: dict[str, str] = {}
        reservations: dict[str, str] = {}
        models: dict[str, list[str]] = {}
        tools: dict[str, list[str]] = {}
        checkpoints: list[StoredEvent] = []
        revision_start = 0
        if run:
            for fact, _ in facts:
                if (
                    fact.event.kind == "agent.checkpoint"
                    and fact.event.scope.goal_revision == run.goal_revision
                ):
                    revision_start = fact.cursor
                    break
        for fact, processed_at in facts:
            event = fact.event
            # Context journal has a request index and a canonical snapshot; show both as
            # real facts but link input references to the canonical snapshot only.
            if event.kind == "context.snapshot" and event.event_id.startswith("context:"):
                raw = event.payload.get("snapshot", {})
                if isinstance(raw, dict):
                    contexts[str(raw.get("id"))] = event.event_id
            if event.kind == "control.reserve":
                reservations[str(event.payload.get("id"))] = event.event_id
            if event.kind.startswith("model.") and event.scope.operation_id:
                models.setdefault(str(event.scope.operation_id), []).append(event.event_id)
            if (
                event.kind in {"tool.received", "tool.completed", "tool.unknown"}
                and event.scope.operation_id
            ):
                tools.setdefault(str(event.scope.operation_id), []).append(event.event_id)
            if event.kind == "agent.checkpoint":
                checkpoints.append(fact)
            late = bool(
                run
                and revision_start
                and fact.cursor > revision_start
                and event.scope.goal_id == "agent-goal-" + run_id
                and event.scope.goal_revision < run.goal_revision
                and event.kind.startswith(("model.", "judgment."))
            )
            nodes.append(
                TraceNode(
                    id=event.event_id,
                    cursor=fact.cursor,
                    kind=event.kind,
                    event_time=event.timestamp.isoformat(),
                    processed_at=processed_at,
                    source=event.source,
                    goal_revision=event.scope.goal_revision,
                    late_revision_result=late,
                    details=self.details(event),
                )
            )
        for previous, current in zip(checkpoints, checkpoints[1:], strict=False):
            edges.append(
                TraceEdge(
                    source=previous.event.event_id,
                    target=current.event.event_id,
                    relation="checkpoint",
                )
            )
        ids = {n.id for n in nodes}
        node_cursors = {n.id: n.cursor for n in nodes}
        node_kinds = {n.id: n.kind for n in nodes}
        if reference and reference.event_id not in ids:
            missing.append("checkpoint-index:" + reference.event_id)
        for fact, _ in facts:
            event = fact.event
            reservation = event.payload.get("reservation_id")
            if reservation and str(reservation) in reservations:
                edges.append(
                    TraceEdge(
                        source=reservations[str(reservation)],
                        target=event.event_id,
                        relation="authorization",
                    )
                )
            if event.kind == "agent.checkpoint":
                try:
                    state = AgentRun.model_validate(event.payload["run"])
                except ValidationError:
                    continue
                for context_id in state.context_ids:
                    if context_id in contexts:
                        edges.append(
                            TraceEdge(
                                source=contexts[context_id], target=event.event_id, relation="input"
                            )
                        )
                for judgment in state.judgments:
                    if judgment.raw_event_id in ids:
                        edges.append(
                            TraceEdge(
                                source=judgment.raw_event_id,
                                target=event.event_id,
                                relation="decision",
                            )
                        )
                for receipt in state.receipts:
                    for source in tools.get(receipt.operation_id, []):
                        if node_cursors[source] > fact.cursor:
                            continue
                        relation: Literal["verification", "receipt"] = (
                            "verification"
                            if state.check and receipt.operation_id in state.check.evidence
                            else "receipt"
                        )
                        edges.append(
                            TraceEdge(source=source, target=event.event_id, relation=relation)
                        )
                if state.check and state.model_results:
                    for source in models.get(state.model_results[-1].request_id, []):
                        if (
                            node_kinds[source] == "model.completed"
                            and node_cursors[source] <= fact.cursor
                        ):
                            edges.append(
                                TraceEdge(
                                    source=source, target=event.event_id, relation="verification"
                                )
                            )
                if state.model_request_id and state.context_ids:
                    for target in models.get(state.model_request_id, []):
                        context_source = contexts.get(state.context_ids[-1])
                        if context_source:
                            edges.append(
                                TraceEdge(source=context_source, target=target, relation="input")
                            )
        asset_versions: dict[str, JsonValue] = {}
        for request_id, records in models.items():
            if any(
                node_kinds[i] in {"model.received", "model.completed"} for i in records
            ) and not any(node_kinds[i] == "model.started" for i in records):
                missing.append("model-intent:" + request_id)
        if run:
            for context_id in run.context_ids:
                if context_id not in contexts:
                    missing.append("context:" + context_id)
                try:
                    asset_context = await self.deps.context.snapshot(runtime, project, context_id)
                    asset_versions[context_id] = {
                        "asset_snapshot_id": asset_context.asset_snapshot_id,
                        "model_revision": asset_context.declared_model_revision,
                        "policy_version": asset_context.policy_version,
                    }
                except ApplicationError as error:
                    missing.append("context:" + context_id + ":" + error.code)
            for judgment in run.judgments:
                if judgment.raw_event_id not in ids:
                    missing.append(judgment.raw_event_id)
            for result in run.model_results:
                if not any(
                    "received" in value or "completed" in value
                    for value in models.get(result.request_id, [])
                ):
                    missing.append("model-result:" + result.request_id)
            if run.status not in {"paused", "blocked"}:
                reasons.append("run_not_at_recovery_boundary")
            if run.phase == "tool" and run.reason == "tool_outcome_unknown":
                reasons.append("tool_reconciliation_required")
        else:
            reasons.append("checkpoint_unreadable")
        if missing:
            reasons.append("source_evidence_missing_or_unavailable")
        episodes: list[EpisodeSummary] = []
        revisions = sorted({fact.event.scope.goal_revision for fact in checkpoints})
        operation_revisions: dict[str, int] = {}
        for fact in checkpoints:
            try:
                state = AgentRun.model_validate(fact.event.payload["run"])
            except ValidationError:
                continue
            for plan in state.plans:
                operation_revisions.setdefault(plan.operation_id, state.goal_revision)
        for revision in revisions:
            members = [
                fact
                for fact, _ in facts
                if fact.event.scope.goal_id == "agent-goal-" + run_id
                and fact.event.scope.goal_revision == revision
            ]
            if not members:
                continue
            result_ids: set[str] = set()
            observed_tokens = 0
            observed_cost = 0
            context_ids: set[str] = set()
            for fact in members:
                raw = fact.event.payload.get("result")
                if fact.event.kind in {"model.received", "model.completed"} and isinstance(
                    raw, dict
                ):
                    identity = str(raw.get("request_id", ""))
                    usage = raw.get("usage", {})
                    if identity not in result_ids and isinstance(usage, dict):
                        observed_tokens += int(str(usage.get("input_tokens", 0))) + int(
                            str(usage.get("output_tokens", 0))
                        )
                        observed_cost += int(str(usage.get("estimated_cost_microusd", 0)))
                        result_ids.add(identity)
                snapshot = fact.event.payload.get("snapshot")
                if fact.event.kind == "context.snapshot" and isinstance(snapshot, dict):
                    context_ids.add(str(snapshot.get("id", "")))
            episodes.append(
                EpisodeSummary(
                    id=f"{run_id}:{revision}",
                    session_id=run.session_id if run else "",
                    goal_id="agent-goal-" + run_id,
                    run_id=run_id,
                    goal_revision=revision,
                    first_cursor=members[0].cursor,
                    last_cursor=members[-1].cursor,
                    context_ids=tuple(sorted(context_ids)),
                    model_request_ids=tuple(sorted(result_ids)),
                    operation_ids=tuple(
                        sorted(k for k, v in operation_revisions.items() if v == revision)
                    ),
                    observed_tokens=observed_tokens,
                    estimated_cost_microusd=observed_cost,
                )
            )
        checkpoint_state: dict[str, JsonValue] = (
            {}
            if run is None
            else {
                "session_id": run.session_id,
                "goal_id": "agent-goal-" + run_id,
                "goal_revision": run.goal_revision,
                "input_cutoff_unit": run.input_cutoff_unit,
                "asset_versions": asset_versions,
                "history_messages": len(run.history),
                "context_ids": list(run.context_ids),
                "pending_call_ids": [c.id for c in run.pending_calls],
                "operation_ids": [p.operation_id for p in run.plans],
                "model_request_id": run.model_request_id,
                "tokens_confirmed": run.tokens_used,
                "estimated_cost_microusd": run.cost_microusd,
                "judgment_sources": [j.source.model_dump(mode="json") for j in run.judgments],
            }
        )
        return Trajectory.model_validate(
            {
                "project_id": project,
                "run_id": run_id,
                "purpose": purpose,
                "processing_cursor": await self.projection.position(),
                "checkpoint": reference,
                "caught_up": caught_up,
                "checkpoint_state": checkpoint_state,
                "episodes": episodes,
                "nodes": nodes,
                "edges": list({(e.source, e.target, e.relation): e for e in edges}.values()),
                "missing_references": tuple(dict.fromkeys(missing)),
                "recovery_available": not reasons,
                "recovery_reasons": tuple(dict.fromkeys(reasons)),
                "tokens_used": run.tokens_used if run else None,
                "cost_microusd": run.cost_microusd if run else None,
                "usage_complete": bool(
                    run
                    and not missing
                    and not run.model_request_id
                    and not any(r.outcome == "unknown" for r in run.receipts)
                ),
            }
        )

    async def recover(
        self, principal: Principal, project: str, run_id: str, command: RecoveryCommand
    ) -> AgentRun:
        runtime = self.actor(principal)
        await self.checkpoints.owned_seed(principal, project, run_id)
        await self.deps.assets.view(runtime, project)
        digest = hashlib.sha256((project + run_id + command.model_dump_json()).encode()).hexdigest()
        identity = (
            "experience-recover:"
            + hashlib.sha256((principal.owner + "\0" + command.request_id).encode()).hexdigest()
        )
        admitted = await self.deps.events.lookup(identity)
        if admitted and admitted.event.payload.get("digest") != digest:
            raise ApplicationError(
                409, "recovery_request_conflict", "Recovery id belongs to another input"
            )
        action = RunCommand(
            request_id=command.request_id,
            expected_goal_revision=command.expected_goal_revision,
            expected_version=command.expected_version,
            action="resume",
        )
        if admitted:
            accepted = await self.deps.agent.command_result(principal, run_id, action)
            if accepted is not None:
                return accepted
        view = await self.trajectory(principal, project, run_id, "recovery")
        if not view.recovery_available or view.checkpoint is None:
            raise ApplicationError(409, "recovery_blocked", ",".join(view.recovery_reasons))
        if (
            view.checkpoint.event_id != command.checkpoint_event_id
            or view.checkpoint.version != command.expected_version
        ):
            raise ApplicationError(
                409, "recovery_checkpoint_changed", "Checkpoint changed; refresh before recovery"
            )
        if admitted is None:
            record = Event(
                event_id=identity,
                kind="experience.recovery_requested",
                timestamp=self.deps.runtime.now(),
                scope=EventScope.model_validate(
                    {
                        "project_id": project,
                        "run_id": run_id,
                        "goal_revision": command.expected_goal_revision,
                    }
                ),
                source="test"
                if any(n.id == view.checkpoint.event_id and n.source == "test" for n in view.nodes)
                else "runtime",
                payload={
                    "digest": digest,
                    "checkpoint_event_id": command.checkpoint_event_id,
                    "expected_version": command.expected_version,
                },
            )
            try:
                await self.deps.events.append([record])
            except ApplicationError:
                proof = await self.deps.events.lookup(identity)
                if proof is None or proof.event.payload != record.payload:
                    raise
        return await self.deps.agent.command(principal, run_id, action)
