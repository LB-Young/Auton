import asyncio
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import Literal

from auton.agent.contracts import Acceptance, AgentRun, CreateRun, RunCommand
from auton.assess.contracts import EvaluateCommand, OptimizationTask
from auton.constitution.config import Principal
from auton.evolve.contracts import (
    ArenaCommand,
    ArenaControl,
    ArenaTrial,
    ArenaView,
    EvolutionConfig,
    Proposal,
)
from auton.evolve.dependencies import EvolutionDependencies
from auton.evolve.gates import EvolutionGate, independence_groups
from auton.evolve.jobs import EvolutionJobs
from auton.evolve.store import EvolutionStore, digest, key
from auton.genome.contracts import ArenaSnapshotCommand
from auton.kernel.ports import ApplicationError


class ArenaRunner:
    def __init__(
        self,
        config: EvolutionConfig,
        deps: EvolutionDependencies,
        store: EvolutionStore,
        gate: EvolutionGate,
        lock: asyncio.Lock,
        slots: EvolutionJobs,
        playbook: Callable[[Principal, Proposal], Awaitable[None]],
    ) -> None:
        self.config, self.deps, self.store, self.gate = config, deps, store, gate
        self.lock, self.slots, self.playbook = lock, slots, playbook
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.accepting = True

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "evolution_user_required", "Only users control isolated evaluation"
            )

    async def load(self, principal: Principal, identity: str) -> ArenaView:
        value = await self.store.get("arena", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "evolution_arena_missing", "No owned arena")
        return ArenaView.model_validate(value)

    async def proposal(self, principal: Principal, identity: str) -> Proposal:
        value = await self.store.get("proposal", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "evolution_proposal_missing", "No owned proposal")
        return Proposal.model_validate(value)

    async def update(self, principal: Principal, arena: ArenaView, **changes: object) -> ArenaView:
        if all(getattr(arena, name) == value for name, value in changes.items()):
            return arena
        result = ArenaView.model_validate(
            {**arena.model_dump(), **changes, "version": arena.version + 1}
        )
        await self.store.put(
            "arena", principal.owner, arena.id, result.model_dump(mode="json"), arena.version
        )
        return result

    async def get(self, principal: Principal, identity: str) -> ArenaView:
        self.user(principal)
        async with self.lock:
            arena = await self.load(principal, identity)
            if arena.status == "complete":
                await self.complete_proposal(principal, arena)
            elif arena.status in {"blocked", "cancelled"}:
                await self.halt_proposal(principal, arena)
            if (
                arena.status in {"running", "cancelling", "waiting_approval"}
                and arena.id not in self.tasks
            ):
                stopped = await self.update(
                    principal,
                    arena,
                    status="blocked",
                    reason="process_interrupted_explicit_resume_required",
                )
                await self.halt_proposal(principal, stopped)
                return stopped
            return arena

    async def list(self, principal: Principal, project: str) -> tuple[ArenaView, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        values = await self.store.list("arena", principal.owner)
        return tuple(
            [
                await self.get(principal, str(value["id"]))
                for value in values
                if value["project_id"] == project
            ]
        )

    async def create(self, principal: Principal, command: ArenaCommand) -> ArenaView:
        self.user(principal)
        identity = key(principal.owner, "arena:" + command.request_id)
        payload = command.model_dump(mode="json")
        async with self.lock:
            if await self.store.receipt(
                principal.owner, "arena:" + command.request_id, "arena", identity, payload
            ):
                saved = await self.load(principal, identity)
                await self.bind_proposal(principal, saved)
                return saved
            proposal = await self.proposal(principal, command.proposal_id)
            if proposal.version != command.expected_proposal_version:
                raise ApplicationError(
                    409,
                    "evolution_proposal_changed",
                    "Refresh the proposal before freezing a trial plan",
                )
            if (
                proposal.status in {"rejected", "evaluating", "ready_for_release"}
                or proposal.config_digest != self.config.digest
            ):
                raise ApplicationError(
                    409,
                    "evolution_proposal_not_evaluable",
                    "Resolve proposal gates or wait for the current arena",
                )
            if any(
                g.verdict == "fail"
                for g in proposal.gates
                if g.name in {"G1_structure", "G4_playbook"}
            ):
                raise ApplicationError(
                    409,
                    "evolution_static_gate_failed",
                    "A failed static gate cannot be evaluated away",
                )
            previous = await self.store.list("arena", principal.owner)
            failures = sum(
                1
                for value in previous
                if value["command"]["proposal_id"] == proposal.id
                and value["status"] in {"blocked", "cancelled", "complete"}
            )
            if failures >= self.config.max_failed_attempts:
                raise ApplicationError(
                    429,
                    "evolution_arena_iteration_limit",
                    "Review prior trials before another bounded proposal",
                )
            count = (
                (len(command.train_cases) + len(command.development_cases)) * 3 * command.repeats
            )
            limits = command.limits
            if (
                count > self.config.max_arena_runs
                or count * limits.max_steps > self.config.max_arena_model_calls
                or count * limits.max_tokens > self.config.max_arena_tokens
                or count * limits.max_cost_microusd > self.config.max_arena_cost_microusd
                or count * limits.max_tool_calls > self.config.max_arena_tool_calls
                or any(
                    value > getattr(self.deps.host_limits, name)
                    for name, value in limits.model_dump().items()
                )
            ):
                raise ApplicationError(
                    403,
                    "evolution_arena_budget",
                    "The entire fixed trial plan exceeds its bounded grant",
                )
            model = next(
                (model for model in self.deps.models.catalog() if model.id == command.model_id),
                None,
            )
            if model is None or "tools" not in model.capabilities:
                raise ApplicationError(
                    422, "evolution_model_unknown", "Choose a registered executor"
                )
            if (await self.deps.assess.bank(principal)).revision != command.bank_revision:
                raise ApplicationError(
                    409, "evolution_bank_changed", "Freeze the current evaluation bank"
                )
            segments: tuple[tuple[Literal["train", "development"], tuple[str, ...]], ...] = (
                ("train", command.train_cases),
                ("development", command.development_cases),
            )
            tasks = tuple(
                [
                    await self.deps.assess.optimization_task(
                        principal, case_id, command.bank_revision, split
                    )
                    for split, identities in segments
                    for case_id in identities
                ]
            )
            for case in tasks:
                if model.location == "remote" and (
                    not command.public or case.data_domain != "public"
                ):
                    raise ApplicationError(
                        403,
                        "evolution_private_case_remote",
                        "Remote arena execution requires explicit public inputs for every case",
                    )
                path = PurePosixPath(case.path)
                if (
                    str(path) != case.path
                    or path.is_absolute()
                    or "\\" in case.path
                    or "\0" in case.path
                    or any(p in {".", ".."} for p in case.path.split("/"))
                ):
                    raise ApplicationError(
                        422, "evolution_case_path", "Arena outputs must be canonical relative files"
                    )
            await self.store.capacity(principal.owner, min(900, count * 12 + 10))
            base = await self.deps.assets.snapshot(
                principal, proposal.command.project_id, proposal.command.base_snapshot_id
            )
            current = await self.deps.assets.resolve(principal, proposal.command.project_id)
            if base.purpose != "runtime" or current.revision != base.revision:
                raise ApplicationError(
                    409,
                    "evolution_parent_changed",
                    "Rebase the patch and repeat evaluation after formal assets change",
                )
            snapshots = {"baseline": base.id}
            for variant, mode, content in (
                ("candidate", "patch", proposal.candidate_content),
                ("ablation", "ablation", None),
            ):
                snapshot = await self.deps.arena_assets.arena_snapshot(
                    principal.model_copy(update={"role": "evolution"}),
                    proposal.command.project_id,
                    ArenaSnapshotCommand.model_validate(
                        {
                            "base_snapshot_id": base.id,
                            "asset_id": proposal.command.asset_id,
                            "expected_content_sha256": proposal.parent_blob_sha256,
                            "mode": mode,
                            "replacement_content": content,
                        }
                    ),
                )
                snapshots[variant] = snapshot.id
            clusters = independence_groups(tasks)
            trials = []
            # All bindings, repetitions and branches are committed before any executor is called.
            for case in tasks:
                for repeat in range(command.repeats):
                    for variant in ("baseline", "candidate", "ablation"):
                        trial_id = key(
                            principal.owner, f"{identity}:{case.case_id}:{repeat}:{variant}"
                        )
                        trials.append(
                            ArenaTrial.model_validate(
                                {
                                    "id": trial_id,
                                    "case_id": case.case_id,
                                    "family": case.family,
                                    "independence_group": clusters[case.case_id],
                                    "split": case.split,
                                    "variant": variant,
                                    "repeat": repeat,
                                    "snapshot_id": snapshots[variant],
                                    "workspace_id": "evo-" + trial_id,
                                    "case_source": case.source,
                                    "critical": case.critical,
                                }
                            )
                        )
            arena = ArenaView(
                frozen_tasks=tasks,
                project_id=proposal.command.project_id,
                id=identity,
                command=command,
                trials=tuple(trials),
                reason="user_frozen_private_trial_plan",
                config_digest=self.config.digest,
                assessment_config_digest=self.deps.assess.status().config_digest,
                source="test" if self.deps.test_source else "runtime",
                created_at=self.deps.runtime.now().timestamp(),
            )
            await self.store.put(
                "arena",
                principal.owner,
                identity,
                arena.model_dump(mode="json"),
                None,
                "arena:" + command.request_id,
                payload,
            )
            await self.bind_proposal(principal, arena)
            return arena

    async def bind_proposal(self, principal: Principal, arena: ArenaView) -> None:
        proposal = await self.proposal(principal, arena.command.proposal_id)
        if (
            proposal.current_arena_id == arena.id
            or proposal.version != arena.command.expected_proposal_version
        ):
            return
        updated = proposal.model_copy(
            update={
                "version": proposal.version + 1,
                "status": "evaluating",
                "current_arena_id": arena.id,
            }
        )
        await self.store.put(
            "proposal",
            principal.owner,
            proposal.id,
            updated.model_dump(mode="json"),
            proposal.version,
        )

    async def complete_proposal(self, principal: Principal, arena: ArenaView) -> None:
        proposal = await self.proposal(principal, arena.command.proposal_id)
        if proposal.current_arena_id != arena.id or proposal.status != "evaluating":
            if proposal.current_arena_id == arena.id:
                await self.playbook(principal, proposal)
            return
        gates = arena.gates or self.gate.evaluate(proposal, arena, self.config)
        updated = proposal.model_copy(
            update={
                "version": proposal.version + 1,
                "status": "blocked",
                "gates": gates,
                "reasons": tuple(dict.fromkeys(reason for g in gates for reason in g.reasons)),
            }
        )
        await self.store.put(
            "proposal",
            principal.owner,
            proposal.id,
            updated.model_dump(mode="json"),
            proposal.version,
        )
        await self.playbook(principal, updated)

    async def halt_proposal(self, principal: Principal, arena: ArenaView) -> None:
        proposal = await self.proposal(principal, arena.command.proposal_id)
        if proposal.current_arena_id != arena.id or proposal.status != "evaluating":
            return
        updated = proposal.model_copy(
            update={
                "version": proposal.version + 1,
                "status": "blocked",
                "reasons": tuple(dict.fromkeys((*proposal.reasons, arena.reason))),
            }
        )
        await self.store.put(
            "proposal",
            principal.owner,
            proposal.id,
            updated.model_dump(mode="json"),
            proposal.version,
        )
        await self.playbook(principal, updated)

    def launch(self, principal: Principal, identity: str) -> None:
        if identity in self.tasks:
            return
        self.slots.acquire("arena:" + identity)
        self.tasks[identity] = asyncio.create_task(self.drive(principal, identity))
        self.tasks[identity].add_done_callback(
            lambda done: done.exception() if not done.cancelled() else None
        )

    async def control(
        self, principal: Principal, identity: str, command: ArenaControl
    ) -> ArenaView:
        self.user(principal)
        async with self.lock:
            arena = await self.load(principal, identity)
            payload = command.model_dump(mode="json")
            if await self.store.receipt(
                principal.owner, "arena-control:" + command.request_id, "arena", identity, payload
            ):
                if arena.status in {"running", "cancelling", "waiting_approval"}:
                    self.launch(principal, identity)
                return arena
            if arena.version != command.expected_version:
                raise ApplicationError(
                    409, "evolution_arena_changed", "Refresh the exact arena checkpoint"
                )
            if arena.status in {"complete", "cancelled"}:
                raise ApplicationError(
                    409, "evolution_arena_terminal", "The fixed arena is terminal"
                )
            if (
                command.action != "cancel"
                and (await self.proposal(principal, arena.command.proposal_id)).current_arena_id
                != arena.id
            ):
                raise ApplicationError(
                    409, "evolution_arena_superseded", "Select the current candidate evaluation"
                )
            changes: dict[str, object] = {}
            if command.action == "start" and arena.status == "draft":
                changes = {"status": "running", "reason": "user_started_private_trials"}
            elif command.action == "resume" and arena.status == "blocked":
                changes = {
                    "status": "running",
                    "reason": "user_resumed_private_trials",
                    "resume_command_id": command.request_id,
                }
            elif command.action == "approve_current" and arena.status == "waiting_approval":
                changes = {
                    "status": "running",
                    "reason": "user_approved_current_private_operation",
                    "approval_command_id": command.request_id,
                }
            elif command.action == "cancel":
                changes = {
                    "status": "cancelling",
                    "reason": "user_cancelled_arena",
                    "approval_command_id": None,
                    "resume_command_id": None,
                }
            else:
                raise ApplicationError(
                    409, "evolution_arena_action", "Action is not valid at this arena boundary"
                )
            self.slots.acquire("arena:" + identity)
            try:
                result = ArenaView.model_validate(
                    {**arena.model_dump(), **changes, "version": arena.version + 1}
                )
                await self.store.put(
                    "arena",
                    principal.owner,
                    identity,
                    result.model_dump(mode="json"),
                    arena.version,
                    "arena-control:" + command.request_id,
                    payload,
                )
                self.launch(principal, identity)
                return result
            except BaseException:
                if identity not in self.tasks:
                    self.slots.release("arena:" + identity)
                raise

    async def request(
        self, principal: Principal, arena: ArenaView, trial: ArenaTrial
    ) -> tuple[CreateRun, OptimizationTask]:
        task = next(
            (
                t
                for t in arena.frozen_tasks
                if t.case_id == trial.case_id and t.split == trial.split
            ),
            None,
        )
        if task is None:
            raise ApplicationError(
                409, "evolution_frozen_input_missing", "The trial has no original frozen task"
            )
        return CreateRun(
            request_id="evo-" + trial.id,
            project_id=arena.project_id,
            workspace_id=trial.workspace_id,
            model_id=arena.command.model_id,
            goal=task.prompt,
            data_domain="public"
            if arena.command.public and task.data_domain == "public"
            else "local-only",
            boundaries=(
                "Only write the declared delivery inside the private trial workspace.",
                "Report observed tool receipts; never expand permissions or approve yourself.",
            ),
            allowed_tools=("file.write",),
            acceptance=Acceptance(kind="file", path=task.path, sha256=task.sha256),
            limits=arena.command.limits,
            asset_snapshot_id=trial.snapshot_id,
        ), task

    def observed(self, trial: ArenaTrial, run: AgentRun) -> ArenaTrial:
        pending = next(
            (
                p
                for p in reversed(run.plans)
                if p.requires_approval and p.operation_id not in run.approvals
            ),
            None,
        )
        return trial.model_copy(
            update={
                "run_id": run.id,
                "run_version": run.version,
                "status": run.status,
                "tokens": run.tokens_used,
                "cost_microusd": run.cost_microusd,
                "confirmed_calls": len(run.model_results),
                "unknown_calls": max(
                    0, run.steps - len(run.model_results) - len(run.undispatched_model_request_ids)
                ),
                "tool_calls": len(run.receipts),
                "pending_preview": pending.preview if pending else None,
                "source": run.source,
            }
        )

    async def persist_trial(
        self,
        principal: Principal,
        arena: ArenaView,
        index: int,
        trial: ArenaTrial,
        **changes: object,
    ) -> ArenaView:
        trials = list(arena.trials)
        trials[index] = trial
        return await self.update(
            principal,
            arena,
            trials=tuple(trials),
            total_tokens=sum(t.tokens for t in trials),
            total_cost_microusd=sum(t.cost_microusd for t in trials),
            total_model_calls=sum(t.confirmed_calls for t in trials),
            unknown_model_calls=sum(t.unknown_calls for t in trials),
            total_tool_calls=sum(t.tool_calls for t in trials),
            **changes,
        )

    async def qualify(
        self,
        principal: Principal,
        arena: ArenaView,
        trial: ArenaTrial,
        run: AgentRun,
        proposal: Proposal,
        task: OptimizationTask,
    ) -> ArenaTrial:
        job = await self.deps.assess.evaluate(
            principal,
            EvaluateCommand(
                request_id="evo-check-" + trial.id[:48] + "-" + str(run.version),
                project_id=arena.project_id,
                run_id=run.id,
                expected_version=run.version,
                case_id=trial.case_id,
                bank_revision=arena.command.bank_revision,
            ),
        )
        assert job.report
        report = await self.deps.assess.report(principal, job.report.id)
        snapshots = [
            await self.deps.context.snapshot(
                principal.model_copy(update={"role": "runtime"}), arena.project_id, identity
            )
            for identity in run.context_ids
        ]
        actual = await self.deps.assets.snapshot(principal, arena.project_id, trial.snapshot_id)
        base = await self.deps.assets.snapshot(
            principal, arena.project_id, proposal.command.base_snapshot_id
        )
        others = tuple(a for a in actual.assets if a.id != proposal.command.asset_id)
        original_others = tuple(a for a in base.assets if a.id != proposal.command.asset_id)
        target = next((a for a in actual.assets if a.id == proposal.command.asset_id), None)
        scoped = (
            others == original_others
            and actual.instructions == base.instructions
            and actual.revision == base.revision
            and run.command.asset_snapshot_id == trial.snapshot_id
            and run.input_asset_snapshot_id == trial.snapshot_id
            and all(snapshot.asset_snapshot_id == trial.snapshot_id for snapshot in snapshots)
        )
        if trial.variant == "baseline":
            scoped &= actual.id == base.id
        else:
            scoped &= (
                actual.purpose == "optimization_arena"
                and actual.parent_snapshot_id == base.id
                and actual.arena_asset_id == proposal.command.asset_id
            )
            scoped &= (
                (actual.arena_mode == "ablation" and target is None)
                if trial.variant == "ablation"
                else (
                    actual.arena_mode == "patch"
                    and target is not None
                    and target.content == proposal.candidate_content
                )
            )
        identities = {
            (r.model_id, r.reported_model, r.system_fingerprint) for r in run.model_results
        }
        registered = next(
            (
                m.model_dump(mode="json", exclude={"health"})
                for m in self.deps.models.catalog()
                if m.id == run.command.model_id
            ),
            None,
        )
        declaration = {k: v for k, v in run.executor_spec.items() if k != "health"}
        executor = (
            digest(
                {
                    "declared": declaration,
                    "observed": sorted(identities),
                    "runtime": run.runtime_revision,
                }
            )
            if len(identities) == 1 and all(i[2] for i in identities) and registered == declaration
            else None
        )
        calls = [call for result in run.model_results for call in result.tool_calls]
        followed = bool(calls) and all(
            call.name == "file_write"
            and call.arguments.get("path") == task.path
            and (
                not rule.require_absent_or_null_old_digest
                or call.arguments.get("expected_sha256") is None
            )
            for call in calls
            for rule in arena.command.checkpoints
        )
        retained = bool(
            snapshots
            and any(proposal.command.asset_id in e.asset_ids for e in snapshots[0].evidence)
        )
        signature = (
            digest(
                {
                    "goal": task.prompt,
                    "acceptance": run.command.acceptance.model_dump(mode="json"),
                    "domain": run.command.data_domain,
                    "tools": run.command.allowed_tools,
                    "budget": run.budget_limits,
                    "executor": executor,
                    "other_assets": [a.model_dump(mode="json") for a in others],
                    "instructions": actual.instructions,
                    "source_revision": base.revision,
                }
            )
            if scoped and executor
            else None
        )
        return trial.model_copy(
            update={
                "status": "complete",
                "report_id": report.id,
                "outcome": report.outcome if report.current_evidence_valid else "environment_error",
                "environment_verified": report.environment_verified
                and report.current_evidence_valid
                and scoped,
                "executor_signature": executor,
                "comparison_signature": signature,
                "checkpoints_followed": followed,
                "target_retained": retained,
                "pending_preview": None,
                "reasons": tuple(dict.fromkeys((*trial.reasons, run.reason, *report.reasons))),
            }
        )

    async def tick(self, principal: Principal, arena: ArenaView) -> ArenaView:
        proposal = await self.proposal(principal, arena.command.proposal_id)
        if arena.status != "cancelling" and arena.config_digest != self.config.digest:
            raise ApplicationError(
                409,
                "evolution_configuration_changed",
                "A fixed arena cannot run under changed gates",
            )
        if arena.status != "cancelling":
            if (
                arena.assessment_config_digest != self.deps.assess.status().config_digest
                or (await self.deps.assess.bank(principal)).revision != arena.command.bank_revision
            ):
                raise ApplicationError(
                    409, "evolution_evaluator_changed", "Frozen evaluator or bank changed"
                )
            if proposal.current_arena_id != arena.id:
                raise ApplicationError(
                    409, "evolution_arena_superseded", "A newer evaluation owns the proposal"
                )
            base = await self.deps.assets.snapshot(
                principal, arena.project_id, proposal.command.base_snapshot_id
            )
            current = await self.deps.assets.resolve(principal, arena.project_id)
            if current.revision != base.revision:
                raise ApplicationError(
                    409, "evolution_parent_changed", "Formal inputs changed during the arena"
                )
            if (
                self.deps.runtime.now().timestamp() - arena.created_at
                > self.config.arena_timeout_seconds
            ):
                return await self.update(
                    principal,
                    arena,
                    status="cancelling",
                    reason="arena_deadline_expired",
                    approval_command_id=None,
                    resume_command_id=None,
                )
        index = next((i for i, t in enumerate(arena.trials) if t.status != "complete"), None)
        if index is None:
            if arena.status == "cancelling":
                return await self.update(
                    principal, arena, status="cancelled", reason="user_cancelled_after_all_trials"
                )
            finished = arena.model_copy(update={"status": "complete"})
            gates = self.gate.evaluate(proposal, finished, self.config)
            finished = await self.update(
                principal,
                arena,
                status="complete",
                reason="fixed_trial_plan_complete_not_automatic_publication",
                gates=gates,
                ready_for_release=False,
            )
            await self.complete_proposal(principal, finished)
            return finished
        trial = arena.trials[index]
        request, case = await self.request(principal, arena, trial)
        if trial.run_id is None:
            found = await self.deps.agent.find_creation(principal, request)
            if found:
                trial = self.observed(trial, found)
                arena = await self.persist_trial(
                    principal, arena, index, trial, current_trial=trial.id
                )
            elif arena.status == "cancelling":
                return await self.update(principal, arena, status="cancelled", reason=arena.reason)
            else:
                await self.store.capacity(principal.owner, 16)
                arena = await self.update(principal, arena, current_trial=trial.id)
                await self.deps.tools.create_workspace(
                    principal, trial.workspace_id, "Isolated Skill trial", False
                )
                found = await self.deps.agent.create(principal, request)
                return await self.persist_trial(
                    principal, arena, index, self.observed(trial, found)
                )
        assert trial.run_id
        run = await self.deps.agent.get(principal, trial.run_id)
        if arena.status == "cancelling":
            if run.status not in {"succeeded", "failed", "cancelled"}:
                run = await self.deps.agent.command(
                    principal,
                    run.id,
                    RunCommand(
                        request_id="evo-cancel-" + trial.id[:40] + "-" + str(run.goal_revision),
                        expected_goal_revision=run.goal_revision,
                        action="cancel",
                    ),
                )
            observed = self.observed(trial, run)
            unknown_tools = any(r.outcome == "unknown" for r in run.receipts)
            if (
                run.status in {"succeeded", "failed", "cancelled"}
                and not observed.unknown_calls
                and not unknown_tools
            ):
                return await self.persist_trial(
                    principal, arena, index, observed, status="cancelled", reason=arena.reason
                )
            if (
                run.status == "blocked"
                or observed.unknown_calls
                and run.status in {"failed", "cancelled"}
            ):
                return await self.persist_trial(
                    principal,
                    arena,
                    index,
                    observed,
                    status="blocked",
                    reason="trial_reconciliation_required_no_new_dispatch",
                )
            return await self.persist_trial(principal, arena, index, observed)
        if run.command != request or run.goal_revision != 1:
            raise ApplicationError(
                409, "evolution_trial_scope_changed", "The exact frozen trial goal was changed"
            )
        action_id = arena.approval_command_id or arena.resume_command_id
        if action_id:
            action: Literal["approve", "resume"] = (
                "approve" if arena.approval_command_id else "resume"
            )
            control = RunCommand(
                request_id="evo-control-" + key(principal.owner, action_id)[:48],
                expected_goal_revision=1,
                expected_version=trial.run_version,
                action=action,
            )
            receipt = await self.deps.agent.command_result(principal, run.id, control)
            if receipt is None:
                if action == "approve" and run.status != "waiting_approval":
                    raise ApplicationError(
                        409,
                        "evolution_trial_approval_stale",
                        "The reviewed operation is no longer pending",
                    )
                if action == "approve" or run.status in {"blocked", "paused"}:
                    run = await self.deps.agent.command(principal, run.id, control)
            arena = await self.update(
                principal, arena, approval_command_id=None, resume_command_id=None
            )
        trial = self.observed(trial, run)
        if run.status == "waiting_approval":
            return await self.persist_trial(
                principal,
                arena,
                index,
                trial,
                status="waiting_approval",
                reason="review_current_private_file_diff",
            )
        if run.status in {"paused", "pausing"}:
            return await self.persist_trial(
                principal,
                arena,
                index,
                trial,
                status="blocked",
                reason="user_paused_trial_explicit_resume_required",
            )
        if run.status in {"succeeded", "failed", "blocked", "cancelled"}:
            if (
                run.model_request_id
                or trial.unknown_calls
                or any(r.outcome == "unknown" for r in run.receipts)
            ):
                return await self.persist_trial(
                    principal,
                    arena,
                    index,
                    trial,
                    status="blocked",
                    reason="trial_reconciliation_required_no_new_dispatch",
                )
            trial = await self.qualify(principal, arena, trial, run, proposal, case)
            return await self.persist_trial(
                principal,
                arena,
                index,
                trial,
                status="running",
                reason="independent_trial_recorded",
            )
        return await self.persist_trial(principal, arena, index, trial, status="running")

    async def drive(self, principal: Principal, identity: str) -> None:
        try:
            while self.accepting:
                async with self.lock:
                    arena = await self.load(principal, identity)
                    if arena.status not in {"running", "waiting_approval", "cancelling"}:
                        return
                    try:
                        current = await self.tick(principal, arena)
                        if current.status in {"blocked", "cancelled"}:
                            await self.halt_proposal(principal, current)
                    except ApplicationError as error:
                        latest = await self.load(principal, identity)
                        if latest.status == "cancelling":
                            blocked = await self.update(
                                principal, latest, status="blocked", reason=error.code
                            )
                            await self.halt_proposal(principal, blocked)
                            return
                        await self.update(
                            principal,
                            latest,
                            status="cancelling",
                            reason=error.code,
                            approval_command_id=None,
                            resume_command_id=None,
                        )
                await asyncio.sleep(0.2)
        finally:
            self.tasks.pop(identity, None)
            self.slots.release("arena:" + identity)
