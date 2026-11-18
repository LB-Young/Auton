import asyncio
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from auton.agent.contracts import RunCommand, RunLimits
from auton.agent.ports import AgentRuntimePort
from auton.assess.contracts import EvaluateCommand
from auton.assess.ports import AssessPort
from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.delegation.contracts import (
    ChildState,
    ContrastCommand,
    DelegationCommand,
    DelegationConfig,
    DelegationCreate,
    DelegationStatus,
    DelegationView,
    SingleMultiContrast,
    identity,
)
from auton.delegation.integrator import ResultIntegrator
from auton.delegation.roles import RoleFactory
from auton.delegation.store import DelegationStore
from auton.genome.ports import AssetReadPort
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.model.ports import ModelGatewayPort
from auton.tools.ports import ToolHostPort

TERMINAL = {"succeeded", "failed", "cancelled"}


@dataclass(frozen=True)
class DelegationDependencies:
    agent: AgentRuntimePort
    tools: ToolHostPort
    assess: AssessPort
    assets: AssetReadPort
    runtime: RuntimeDependencies
    host_limits: RunLimits
    models: ModelGatewayPort
    test_source: bool = False


class Delegation:
    def __init__(
        self,
        config: DelegationConfig,
        deps: DelegationDependencies,
        store: DelegationStore,
        roles: RoleFactory,
        integrator: ResultIntegrator,
    ) -> None:
        self.config, self.deps, self.store = config, deps, store
        self.roles, self.integrator = roles, integrator
        self.ready = False
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        if self.ready:
            return
        await self.store.start()
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        # Shutdown does not issue new commands or erase unknown child/model effects.
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        await self.store.close()

    def user(self, principal: Principal) -> None:
        if not self.ready:
            raise ApplicationError(503, "delegation_not_ready", "Supervisor unavailable")
        if principal.role != "user":
            raise ApplicationError(403, "delegation_user_required", "Only users control delegation")

    def launch(self, principal: Principal, parent: str) -> None:
        if parent in self.tasks:
            return
        if len(self.tasks) >= self.config.max_active_parents:
            raise ApplicationError(
                429, "delegation_busy", "Supervisor concurrency is full; explicitly retry"
            )
        self.tasks[parent] = asyncio.create_task(self.drive(principal, parent))

    async def update(self, owner: str, old: DelegationView, **changes: object) -> DelegationView:
        if old.version >= 4095:
            raise ApplicationError(
                429, "delegation_history_limit", "Supervisor reached checkpoint bound"
            )
        new = DelegationView.model_validate(
            {
                **old.model_dump(),
                **changes,
                "version": old.version + 1,
                "updated_at": self.deps.runtime.now().timestamp(),
            }
        )
        await self.store.save(owner, new, old.version)
        return new

    def status(self) -> DelegationStatus:
        return DelegationStatus(
            host_limits=self.deps.host_limits,
            max_children=self.config.max_children,
            max_parallel=self.config.max_parallel,
            child_timeout_seconds=self.config.child_timeout_seconds,
        )

    async def contrast(
        self, principal: Principal, parent: str, command: ContrastCommand
    ) -> SingleMultiContrast:
        value = await self.get(principal, parent)
        baseline = await self.deps.agent.get(principal, command.baseline_run_id)
        if (
            baseline.version != command.expected_version
            or baseline.command.project_id != value.command.project_id
        ):
            raise ApplicationError(
                409, "delegation_baseline_changed", "Select the exact owned baseline checkpoint"
            )
        job = await self.deps.assess.evaluate(
            principal,
            EvaluateCommand(
                request_id="contrast-"
                + identity(principal.owner, parent + command.request_id)[:56],
                project_id=value.command.project_id,
                run_id=baseline.id,
                expected_version=baseline.version,
            ),
        )
        assert job.report
        reasons = []
        if value.status != "integrated" or not value.integration_receipt:
            reasons.append("multi_not_independently_integrated")
        else:
            try:
                await self.deps.assets.snapshot(
                    principal.model_copy(update={"role": "runtime"}),
                    value.command.project_id,
                    value.input_snapshot_id,
                )
                await self.artifacts(principal, value)
                _, data = await self.deps.tools.artifact(
                    principal, value.integration_receipt.operation_id
                )
                if hashlib.sha256(data).hexdigest() != value.command.acceptance.sha256:
                    reasons.append("multi_artifact_changed")
            except ApplicationError as error:
                reasons.append("multi_evidence_unavailable:" + error.code)
        if (
            baseline.command.goal != value.command.goal
            or baseline.command.boundaries != value.command.boundaries
            or baseline.command.acceptance != value.command.acceptance
            or baseline.command.asset_snapshot_id != value.input_snapshot_id
            or baseline.command.data_domain != ("public" if value.command.public else "local-only")
        ):
            reasons.append("task_scope_or_input_snapshot_differs")
        if baseline.budget_limits != value.command.limits.model_dump():
            reasons.append("original_total_budget_differs")
        if baseline.command.allowed_tools != ("file.write",) or any(
            c.allowed_tools != ("file.write",) for c in value.command.children
        ):
            reasons.append("workspace_read_or_extra_tools_change_inputs")
        if (
            not job.report.environment_verified
            or not job.report.metrics.usage_complete
            or value.unknown_calls
            or value.unknown_tools
        ):
            reasons.append("environment_or_usage_unverified")
        if baseline.source != value.source:
            reasons.append("synthetic_and_runtime_not_comparable")
        if any(
            "no_longer" in reason or "source_unavailable" in reason or "subject_changed" in reason
            for reason in job.report.reasons
        ):
            reasons.append("baseline_evidence_no_longer_current")
        workers = [
            await self.deps.agent.get(principal, c.run_id) for c in value.children if c.run_id
        ]
        comparison = SingleMultiContrast(
            supervisor_id=value.id,
            baseline_run_id=baseline.id,
            comparable=not reasons,
            reasons=tuple(reasons),
            baseline_outcome=job.report.outcome,
            multi_outcome=value.status,
            baseline_calls=len(baseline.model_results),
            worker_calls=sum(len(worker.model_results) for worker in workers),
            baseline_tokens=baseline.tokens_used,
            worker_tokens=value.total_tokens,
            baseline_cost_microusd=baseline.cost_microusd,
            worker_cost_microusd=value.total_cost_microusd,
            cost_delta_microusd=value.total_cost_microusd - baseline.cost_microusd,
            source=value.source,
        )
        await self.store.contrast(
            principal.owner, command.request_id, comparison, command.model_dump(mode="json")
        )
        return comparison

    async def create(self, principal: Principal, command: DelegationCreate) -> DelegationView:
        self.user(principal)
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(
                403, "delegation_sensitive_input", "Credentials cannot enter supervisor state"
            )
        parent = identity(principal.owner, "supervisor:" + command.request_id)
        async with self.lock:
            if await self.store.receipt(
                principal.owner,
                "create:" + command.request_id,
                parent,
                command.model_dump(mode="json"),
            ):
                return await self.store.load(principal.owner, parent)
            if len(command.children) > self.config.max_children:
                raise ApplicationError(422, "delegation_children_limit", "Too many workers")
            catalog = {model.id: model for model in self.deps.models.catalog()}
            if any(child.model_id not in catalog for child in command.children):
                raise ApplicationError(
                    422, "delegation_model_unknown", "Choose registered worker models"
                )
            if any(
                v > getattr(self.deps.host_limits, k)
                for k, v in command.limits.model_dump().items()
            ):
                raise ApplicationError(
                    403, "delegation_budget_escalation", "Parent grant exceeds host budget"
                )
            workspace = await self.deps.tools.workspace(principal, command.workspace_id)
            if workspace.read_only:
                raise ApplicationError(
                    403, "delegation_read_only", "Parent workspace cannot receive integration"
                )
            snapshot = await self.deps.assets.resolve(
                principal.model_copy(update={"role": "runtime"}), command.project_id
            )
            now = self.deps.runtime.now().timestamp()
            value = DelegationView(
                id=parent,
                command=command,
                input_snapshot_id=snapshot.id,
                children=tuple(ChildState(id=c.id) for c in command.children),
                interaction_group=tuple(c.id for c in command.children),
                created_at=now,
                updated_at=now,
                source="test" if self.deps.test_source else "runtime",
            )
            for child in command.children:
                self.roles.create(value, child, {})
            await self.store.save(
                principal.owner,
                value,
                None,
                "create:" + command.request_id,
                command.model_dump(mode="json"),
            )
            return value

    async def get(self, principal: Principal, parent: str) -> DelegationView:
        self.user(principal)
        async with self.lock:
            value = await self.store.load(principal.owner, parent)
            if (
                value.status in {"running", "integrating", "cancelling"}
                and parent not in self.tasks
            ):
                value = await self.update(
                    principal.owner,
                    value,
                    status="blocked",
                    reason="process_interrupted_explicit_resume_required",
                )
            return value

    async def list(self, principal: Principal, project_id: str) -> tuple[DelegationView, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal.model_copy(update={"role": "runtime"}), project_id)
        values = await self.store.list(principal.owner)
        return tuple(
            [await self.get(principal, v.id) for v in values if v.command.project_id == project_id]
        )

    async def command(
        self, principal: Principal, parent: str, command: DelegationCommand
    ) -> DelegationView:
        self.user(principal)
        async with self.lock:
            value = await self.store.load(principal.owner, parent)
            payload = command.model_dump(mode="json")
            if await self.store.receipt(principal.owner, command.request_id, parent, payload):
                if value.status in {"running", "integrating", "cancelling"}:
                    self.launch(principal, parent)
                return value
            if value.version != command.expected_version:
                raise ApplicationError(
                    409, "delegation_version_changed", "Refresh supervisor before controlling it"
                )
            if value.status in {"integrated", "cancelled"}:
                raise ApplicationError(409, "delegation_terminal", "Supervisor is terminal")
            changes: dict[str, object] = {}
            if command.action in {"start", "resume"}:
                if value.status not in {"draft", "blocked"}:
                    raise ApplicationError(
                        409, "delegation_not_resumable", "Supervisor is not at a resume boundary"
                    )
                changes = {
                    "status": "integrating" if value.approved_integration else "running",
                    "reason": "user_started",
                }
            elif command.action == "cancel":
                changes = {"status": "cancelling", "reason": "user_cancelled"}
            elif command.action == "approve_integration":
                if value.status != "waiting_approval" or not value.integration:
                    raise ApplicationError(
                        409, "delegation_no_merge", "No current integration to approve"
                    )
                changes = {
                    "status": "integrating",
                    "reason": "user_approved_integration",
                    "approved_integration": True,
                }
            else:
                if value.status != "running":
                    raise ApplicationError(
                        409, "delegation_not_running", "Supervisor is not running"
                    )
                state = next((c for c in value.children if c.id == command.child_id), None)
                if state is None or state.status != "waiting_approval" or state.version is None:
                    raise ApplicationError(
                        409, "delegation_child_not_waiting", "No child approval at this checkpoint"
                    )
                # Persist exact user intent; the worker cannot manufacture this request.
                children = tuple(
                    c.model_copy(update={"approval_command_id": command.request_id})
                    if c.id == state.id
                    else c
                    for c in value.children
                )
                changes = {"children": children, "reason": "user_approved_child"}
            if parent not in self.tasks and len(self.tasks) >= self.config.max_active_parents:
                raise ApplicationError(429, "delegation_busy", "Supervisor concurrency is full")
            new = DelegationView.model_validate(
                {
                    **value.model_dump(),
                    **changes,
                    "version": value.version + 1,
                    "updated_at": self.deps.runtime.now().timestamp(),
                }
            )
            await self.store.save(principal.owner, new, value.version, command.request_id, payload)
            self.launch(principal, parent)
            return new

    async def artifacts(self, principal: Principal, parent: DelegationView) -> dict[str, str]:
        result = {}
        for state in parent.children:
            if state.status != "verified" or not state.run_id:
                continue
            run = await self.deps.agent.get(principal, state.run_id)
            if (
                run.version != state.version
                or run.goal_revision != 1
                or run.command != state.command
            ):
                raise ApplicationError(
                    409, "delegation_child_changed", "Child no longer matches its bound checkpoint"
                )
            spec = next(c for c in parent.command.children if c.id == state.id)
            receipt = next(
                (
                    r
                    for r in reversed(run.receipts)
                    if r.artifact
                    and r.artifact.path == spec.acceptance.path
                    and r.outcome == "succeeded"
                ),
                None,
            )
            if receipt is None:
                raise ApplicationError(
                    409, "delegation_artifact_missing", "Verified child artifact is unavailable"
                )
            result[state.id] = receipt.operation_id
        return result

    async def tick(self, principal: Principal, parent: DelegationView) -> DelegationView:
        # Caller holds the coordinator lock across bounded dispatch and state publication.
        if parent.status != "cancelling":
            await self.deps.assets.snapshot(
                principal.model_copy(update={"role": "runtime"}),
                parent.command.project_id,
                parent.input_snapshot_id,
            )
        if parent.status == "integrating":
            if not parent.approved_integration or not parent.integration:
                raise ApplicationError(
                    403, "delegation_approval_missing", "User integration approval is required"
                )
            request = await self.integrator.request(
                principal, parent, await self.artifacts(principal, parent)
            )
            plan = await self.deps.tools.prepare(request)
            if plan != parent.integration:
                raise ApplicationError(
                    409, "delegation_merge_changed", "Approved integration plan changed"
                )
            approval = await self.deps.tools.approve(principal, plan.operation_id)
            receipt = await self.deps.tools.execute(
                request.principal, plan.operation_id, approval.id
            )
            if receipt.outcome != "succeeded":
                return await self.update(
                    principal.owner,
                    parent,
                    status="blocked",
                    reason="integration_" + receipt.outcome,
                    integration_receipt=receipt,
                    total_tool_calls=sum(c.tool_calls for c in parent.children) + 1,
                    unknown_tools=sum(c.unknown_tools for c in parent.children)
                    + int(receipt.outcome == "unknown"),
                )
            _, data = await self.deps.tools.artifact(principal, plan.operation_id)
            if hashlib.sha256(data).hexdigest() != parent.command.acceptance.sha256:
                raise ApplicationError(
                    409,
                    "delegation_parent_verification_failed",
                    "Integrated file no longer matches parent acceptance",
                )
            return await self.update(
                principal.owner,
                parent,
                status="integrated",
                reason="independent_parent_digest_matches",
                integration_receipt=receipt,
                total_tool_calls=sum(c.tool_calls for c in parent.children) + 1,
                unknown_tools=sum(c.unknown_tools for c in parent.children),
            )
        if parent.status not in {"running", "cancelling"}:
            return parent
        children = list(parent.children)
        failed_reason: str | None = None
        for i, state in enumerate(children):
            if not state.run_id and state.command:
                found = await self.deps.agent.find_creation(principal, state.command)
                if found:
                    state = state.model_copy(update={"run_id": found.id})
                    children[i] = state
            if not state.run_id:
                if parent.status == "cancelling" and state.command:
                    children[i] = state.model_copy(update={"status": "cancelled", "command": None})
                continue
            run = await self.deps.agent.get(principal, state.run_id)
            if run.command != state.command or run.goal_revision != 1:
                failed_reason = "child_scope_or_goal_changed"
            unknown = max(
                0, run.steps - len(run.model_results) - len(run.undispatched_model_request_ids)
            )
            if parent.status == "cancelling":
                if run.status not in TERMINAL and run.status != "cancelling":
                    run = await self.deps.agent.command(
                        principal,
                        run.id,
                        RunCommand(
                            request_id="cancel-"
                            + parent.id[:40]
                            + "-"
                            + str(i)
                            + "-"
                            + str(run.goal_revision),
                            expected_goal_revision=run.goal_revision,
                            action="cancel",
                        ),
                    )
            elif state.approval_command_id:
                approval_command = RunCommand(
                    request_id="approve-"
                    + identity(principal.owner, state.approval_command_id)[:56],
                    expected_version=state.version,
                    expected_goal_revision=1,
                    action="approve",
                )
                observed = await self.deps.agent.command_result(principal, run.id, approval_command)
                if observed is not None:
                    pass
                elif run.version != state.version or run.status != "waiting_approval":
                    failed_reason = "child_approval_checkpoint_changed"
                else:
                    run = await self.deps.agent.command(principal, run.id, approval_command)
            pending_plan = next(
                (
                    p
                    for p in reversed(run.plans)
                    if p.requires_approval and p.operation_id not in run.approvals
                ),
                None,
            )
            updated = state.model_copy(
                update={
                    "status": run.status,
                    "version": run.version,
                    "reason": run.reason,
                    "tokens": run.tokens_used,
                    "cost_microusd": run.cost_microusd,
                    "unknown_calls": unknown,
                    "unknown_tools": sum(r.outcome == "unknown" for r in run.receipts),
                    "tool_calls": len(run.receipts),
                    "approval_command_id": None,
                    "pending_operation_id": pending_plan.operation_id if pending_plan else None,
                    "pending_preview": pending_plan.preview if pending_plan else None,
                }
            )
            if parent.status != "cancelling":
                if run.status == "succeeded":
                    job = await self.deps.assess.evaluate(
                        principal,
                        EvaluateCommand(
                            request_id="child-check-" + run.id[:45] + "-" + str(run.version),
                            project_id=parent.command.project_id,
                            run_id=run.id,
                            expected_version=run.version,
                        ),
                    )
                    if (
                        not job.report
                        or job.report.outcome != "pass"
                        or not job.report.metrics.usage_complete
                    ):
                        failed_reason = "child_independent_acceptance_failed"
                    else:
                        updated = updated.model_copy(
                            update={"status": "verified", "report_id": job.id}
                        )
                elif run.status in {"blocked", "failed", "cancelled", "paused", "pausing"}:
                    failed_reason = "child_not_successful:" + run.reason
                if (
                    state.started_at
                    and self.deps.runtime.now().timestamp() - state.started_at
                    > self.config.child_timeout_seconds
                    and updated.status != "verified"
                ):
                    failed_reason = "child_timeout"
            children[i] = updated
        totals = {
            "total_tokens": sum(c.tokens for c in children),
            "total_cost_microusd": sum(c.cost_microusd for c in children),
            "total_tool_calls": sum(c.tool_calls for c in children)
            + int(parent.integration_receipt is not None),
            "unknown_calls": sum(c.unknown_calls for c in children),
            "unknown_tools": sum(c.unknown_tools for c in children)
            + int(
                parent.integration_receipt is not None
                and parent.integration_receipt.outcome == "unknown"
            ),
        }
        if parent.status == "cancelling":
            if parent.approved_integration and parent.integration:
                try:
                    receipt = await self.deps.tools.reconcile(
                        principal, parent.integration.operation_id
                    )
                    if parent.integration_receipt is None:
                        totals["total_tool_calls"] += 1
                    totals["unknown_tools"] = sum(c.unknown_tools for c in children) + int(
                        receipt.outcome == "unknown"
                    )
                    if receipt.outcome == "unknown":
                        return await self.changed(
                            principal.owner,
                            parent,
                            children,
                            **totals,
                            status="blocked",
                            reason="integration_reconciliation_required",
                            integration_receipt=receipt,
                        )
                    parent = await self.update(principal.owner, parent, integration_receipt=receipt)
                except ApplicationError as error:
                    if error.code != "operation_not_started":
                        raise
            settled = all(
                (not c.run_id and c.command is None)
                or (c.status in TERMINAL and not c.unknown_calls and not c.unknown_tools)
                for c in children
            )
            if not settled and all(
                not c.run_id or c.status in {*TERMINAL, "blocked"} for c in children
            ):
                return await self.changed(
                    principal.owner,
                    parent,
                    children,
                    **totals,
                    status="blocked",
                    reason=parent.reason + ":child_reconciliation_required",
                )
            return await self.changed(
                principal.owner,
                parent,
                children,
                **totals,
                status=("cancelled" if parent.reason == "user_cancelled" else "blocked")
                if settled
                else "cancelling",
                reason="user_cancelled_after_integration_committed"
                if settled
                and parent.reason == "user_cancelled"
                and parent.integration_receipt
                and parent.integration_receipt.outcome == "succeeded"
                else parent.reason,
            )
        if failed_reason:
            return await self.changed(
                principal.owner,
                parent,
                children,
                **totals,
                status="cancelling",
                reason=failed_reason,
            )
        if all(c.status == "verified" for c in children):
            value = parent.model_copy(update={"children": tuple(children)})
            request = await self.integrator.request(
                principal, value, await self.artifacts(principal, value)
            )
            plan = await self.deps.tools.prepare(request)
            return await self.changed(
                principal.owner,
                parent,
                children,
                **totals,
                status="waiting_approval",
                reason="independent_children_verified_user_merge_required",
                integration=plan,
            )
        active = sum(c.run_id is not None and c.status != "verified" for c in children)
        for i, state in enumerate(children):
            spec = parent.command.children[i]
            if (
                state.run_id
                or active >= self.config.max_parallel
                or not all(
                    next(c for c in children if c.id == dep).status == "verified"
                    for dep in spec.depends_on
                )
            ):
                continue
            handoff = {}
            fragments = await self.artifacts(
                principal, parent.model_copy(update={"children": tuple(children)})
            )
            for dep in spec.depends_on:
                _, data = await self.deps.tools.artifact(principal, fragments[dep])
                if len(data) > 1000:
                    raise ApplicationError(
                        413, "delegation_handoff_limit", "Dependency output exceeds bounded handoff"
                    )
                handoff[dep] = data.decode("utf-8")
            command = self.roles.create(parent, spec, handoff)
            state = state.model_copy(update={"status": "dispatch_intent", "command": command})
            children[i] = state
            parent = await self.changed(principal.owner, parent, children, **totals)
            await self.deps.tools.create_workspace(
                principal, command.workspace_id, "Private worker " + spec.id, False
            )
            run = await self.deps.agent.create(principal, command)
            children[i] = state.model_copy(
                update={
                    "run_id": run.id,
                    "status": run.status,
                    "version": run.version,
                    "started_at": self.deps.runtime.now().timestamp(),
                }
            )
            parent = await self.changed(principal.owner, parent, children, **totals)
            active += 1
        return await self.changed(principal.owner, parent, children, **totals)

    async def changed(
        self, owner: str, parent: DelegationView, children: Sequence[ChildState], **changes: object
    ) -> DelegationView:
        values: dict[str, object] = {"children": tuple(children), **changes}
        if all(getattr(parent, key) == value for key, value in values.items()):
            return parent
        return await self.update(owner, parent, **values)

    async def drive(self, principal: Principal, parent_id: str) -> None:
        try:
            while self.ready:
                async with self.lock:
                    parent = await self.store.load(principal.owner, parent_id)
                    if parent.status not in {"running", "integrating", "cancelling"}:
                        return
                    try:
                        parent = await self.tick(principal, parent)
                    except ApplicationError as error:
                        latest = await self.store.load(principal.owner, parent_id)
                        if latest.status == "cancelling":
                            await self.update(
                                principal.owner, latest, status="blocked", reason=error.code
                            )
                            return
                        await self.update(
                            principal.owner, latest, status="cancelling", reason=error.code
                        )
                await asyncio.sleep(0.1)
        finally:
            self.tasks.pop(parent_id, None)
