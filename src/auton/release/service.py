import asyncio

from auton.agent.contracts import AgentRun, CreateRun
from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import ApplicationError
from auton.release.adapters import GenomeReleaseBackend, ModelReleaseBackend
from auton.release.contracts import (
    ReleaseApproval,
    ReleaseConfig,
    ReleaseControl,
    ReleaseObservation,
    ReleasePlanCommand,
    ReleaseRecord,
    ReleaseStatus,
    ReleaseValidationRun,
)
from auton.release.dependencies import ReleaseDependencies
from auton.release.policy import RolloutPolicy
from auton.release.sources import ReleaseSource, ReleaseSourceReader


class Releases:
    def __init__(
        self,
        config: ReleaseConfig,
        deps: ReleaseDependencies,
        store: VersionedDocumentStore,
        sources: ReleaseSourceReader,
        policy: RolloutPolicy,
        genome: GenomeReleaseBackend,
        models: ModelReleaseBackend,
    ) -> None:
        self.config, self.deps, self.store, self.sources, self.policy, self.genome, self.models = (
            config,
            deps,
            store,
            sources,
            policy,
            genome,
            models,
        )
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        await self.store.start()

    async def close(self) -> None:
        async with self.lock:
            await self.store.close()

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "release_user_required", "Only users approve or control releases"
            )

    def status(self) -> ReleaseStatus:
        return ReleaseStatus(
            policy_revision=self.config.schema_revision,
            min_independent_families=self.config.min_independent_families,
        )

    async def load(self, principal: Principal, identity: str) -> ReleaseRecord:
        value = await self.store.get("release", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "release_missing", "No owned release")
        return ReleaseRecord.model_validate(value)

    async def save(
        self, principal: Principal, old: ReleaseRecord, **changes: object
    ) -> ReleaseRecord:
        result = ReleaseRecord.model_validate(
            {**old.model_dump(), **changes, "version": old.version + 1}
        )
        await self.store.put(
            "release", principal.owner, result.id, result.model_dump(mode="json"), old.version
        )
        return result

    async def plan(self, principal: Principal, command: ReleasePlanCommand) -> ReleaseRecord:
        self.user(principal)
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(
                403, "release_secret_input", "Credentials cannot enter release metadata"
            )
        identity = key(principal.owner, "plan:" + command.request_id)
        async with self.lock:
            value = await self.store.get("release", principal.owner, identity)
            if value:
                saved = ReleaseRecord.model_validate(value)
                if saved.command != command:
                    raise ApplicationError(
                        409, "release_plan_conflict", "Release plan is immutable"
                    )
                return await self.current(principal, saved)
            source = await self.sources.read(principal, command)
            report = await self.policy.evaluate(principal, command, source)
            if await self.store.get(
                "incident", principal.owner, key(principal.owner, source.artifact_identity)
            ):
                report = report.model_copy(
                    update={
                        "eligible": False,
                        "blockers": (
                            *report.blockers,
                            "artifact_incident_requires_independent_review",
                        ),
                    }
                )
            result = ReleaseRecord(
                id=identity,
                command=command,
                config_digest=self.config.digest,
                report=report,
                status="ready" if report.eligible else "blocked",
                created_at=self.deps.runtime.now().timestamp(),
            )
            await self.store.put(
                "release", principal.owner, identity, result.model_dump(mode="json"), None
            )
            return result

    async def current(self, principal: Principal, record: ReleaseRecord) -> ReleaseRecord:
        try:
            source = await self.sources.read(principal, record.command)
            evidence = await self.policy.evaluate(principal, record.command, source)
            valid = (
                record.config_digest == self.config.digest
                and evidence.evidence_digest == record.report.evidence_digest
            )
            return (
                record
                if valid
                else record.model_copy(
                    update={
                        "current_evidence_valid": False,
                        "reason": "release_sources_or_policy_changed",
                    }
                )
            )
        except ApplicationError as error:
            return record.model_copy(
                update={
                    "current_evidence_valid": False,
                    "reason": "release_source_unavailable:" + error.code,
                }
            )

    async def get(self, principal: Principal, identity: str) -> ReleaseRecord:
        self.user(principal)
        return await self.current(principal, await self.load(principal, identity))

    async def list(self, principal: Principal, project: str) -> tuple[ReleaseRecord, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            [
                await self.current(principal, ReleaseRecord.model_validate(v))
                for v in await self.store.list("release", principal.owner)
                if v["command"]["project_id"] == project
            ]
        )

    async def event(
        self,
        principal: Principal,
        record: ReleaseRecord,
        kind: str,
        source: ReleaseSource,
        percentage: int,
    ) -> str:
        identity = "release-receipt:" + key(principal.owner, record.id + ":" + kind)
        event = Event(
            event_id=identity,
            kind=kind,
            timestamp=self.deps.runtime.now(),
            source="test" if self.deps.test_source else "runtime",
            scope=EventScope(project_id=record.command.project_id),
            payload={
                "owner_key": key(principal.owner, "release-owner"),
                "release_id": record.id,
                "source_digest": source.digest,
                "target_digest": source.target_digest,
                "evidence_digest": record.report.evidence_digest,
                "candidate_sha256": (source.metadata or {}).get("candidate_sha256"),
                "percentage": percentage,
                "baseline_model_id": record.command.baseline_model_id,
                "scope_digest": digest(record.command.scope.model_dump(mode="json")),
                "languages": list(
                    ("zh", "en", "mixed", "other")
                    if kind == "release.validation_authorized"
                    else record.command.scope.languages
                ),
                "data_domains": list(
                    ("public", "local-only")
                    if kind == "release.validation_authorized"
                    else record.command.scope.data_domains
                ),
            },
        )
        existing = await self.deps.events.lookup(identity)
        if existing:
            if existing.event.payload != event.payload:
                raise ApplicationError(
                    409, "release_receipt_conflict", "Approval receipt has another frozen scope"
                )
        else:
            await self.deps.events.append([event])
        return identity

    async def approve(
        self, principal: Principal, identity: str, command: ReleaseApproval
    ) -> ReleaseRecord:
        self.user(principal)
        async with self.lock:
            receipt = "approve:" + command.request_id
            if await self.store.receipt(
                principal.owner, receipt, "release", identity, command.model_dump(mode="json")
            ):
                return await self.get(principal, identity)
            record = await self.current(principal, await self.load(principal, identity))
            if (
                record.version != command.expected_version
                or record.status != "ready"
                or not record.current_evidence_valid
                or not record.report.eligible
                or record.report.evidence_digest != command.expected_evidence_digest
                or not command.risks_reviewed
            ):
                raise ApplicationError(
                    409,
                    "release_not_approvable",
                    "Review the exact current qualified report and risks",
                )
            source = await self.sources.read(principal, record.command)
            event = await self.event(
                principal, record, "release.approved", source, record.command.percentage
            )
            result = record.model_copy(
                update={
                    "version": record.version + 1,
                    "status": "approved",
                    "approval_event_id": event,
                }
            )
            await self.store.put(
                "release",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                record.version,
                receipt,
                command.model_dump(mode="json"),
            )
            return result

    async def prepare_validation(self, principal: Principal, identity: str) -> ReleaseRecord:
        self.user(principal)
        async with self.lock:
            record = await self.load(principal, identity)
            if record.command.kind != "executor_model":
                raise ApplicationError(
                    409,
                    "release_validation_kind",
                    "This staged runtime validator is for executor models",
                )
            source = await self.sources.read(principal, record.command)
            if source.blockers:
                raise ApplicationError(
                    409,
                    "release_validation_source_blocked",
                    "Resolve artifact/rights/deployment blockers before offline validation",
                )
            if record.validation_event_id and record.effect_version is not None:
                return record
            await self.models.warm(source)
            if not record.validation_event_id:
                event = await self.event(
                    principal, record, "release.validation_authorized", source, 100
                )
                record = await self.save(principal, record, validation_event_id=event)
            version = await self.models.activate(principal, record, source, True)
            return await self.save(
                principal,
                record,
                effect_version=version,
                reason="offline_validation_only_no_default_switch",
            )

    async def validation_run(
        self, principal: Principal, identity: str, command: ReleaseValidationRun
    ) -> AgentRun:
        self.user(principal)
        record = await self.load(principal, identity)
        if not record.validation_event_id or not record.command.target_model_id:
            raise ApplicationError(
                409,
                "release_validation_not_prepared",
                "Prewarm and authorize offline validation first",
            )
        source = await self.sources.read(principal, record.command)
        if source.blockers:
            raise ApplicationError(
                409,
                "release_validation_source_blocked",
                "Training source or deployment no longer qualifies",
            )
        workspace_id = "release-eval-" + key(identity, command.request_id)[:32]
        try:
            await self.deps.workspaces.workspace(principal, workspace_id)
        except ApplicationError as error:
            if error.code != "workspace_not_found":
                raise
            await self.deps.workspaces.create_workspace(
                principal, workspace_id, "Isolated release evaluation", False
            )
        actor = CreateRun.model_validate(
            {
                "request_id": "release-eval-"
                + key(principal.owner, identity + ":" + command.request_id)[:64],
                "project_id": record.command.project_id,
                "workspace_id": workspace_id,
                "goal": command.goal,
                "model_id": record.command.target_model_id,
                "allowed_tools": ["file.write", "file.read"]
                if command.acceptance.kind == "file"
                else ["file.read"],
                "acceptance": command.acceptance,
                "data_domain": command.data_domain,
            }
        )
        goal = "agent-goal-" + key(principal.owner, actor.request_id)
        await self.deps.models_writer.grant_evaluation(
            principal, record.command.project_id, goal, actor.model_id, actor.digest
        )
        return await self.deps.agent.create(principal, actor)

    async def quiesce(self, principal: Principal, record: ReleaseRecord) -> tuple[str, ...]:
        pending = []
        for run in await self.deps.agent.list(principal, record.command.project_id):
            affected = (
                record.command.kind == "genome" and record.id in run.input_asset_release_ids
            ) or run.executor_spec.get("declared_revision") == record.command.source_id
            if affected and run.status not in {"succeeded", "failed", "cancelled"}:
                pending.append(run.id)
                from auton.agent.contracts import RunCommand

                try:
                    await self.deps.agent.command(
                        principal,
                        run.id,
                        RunCommand.model_validate(
                            {
                                "request_id": "release-stop-"
                                + key(record.id, run.id + ":" + str(run.version))[:40],
                                "expected_goal_revision": run.goal_revision,
                                "expected_version": run.version,
                                "action": "cancel",
                            }
                        ),
                    )
                except ApplicationError:
                    pass
        return tuple(pending)

    async def control(
        self, principal: Principal, identity: str, command: ReleaseControl
    ) -> ReleaseRecord:
        self.user(principal)
        async with self.lock:
            receipt = "control:" + command.request_id
            if await self.store.receipt(
                principal.owner, receipt, "release", identity, command.model_dump(mode="json")
            ):
                return await self.get(principal, identity)
            record = await self.load(principal, identity)
            if record.version != command.expected_version:
                raise ApplicationError(
                    409, "release_version_changed", "Refresh the current release before control"
                )
            if command.action == "activate":
                current = await self.current(principal, record)
                if (
                    current.status not in {"approved", "activating"}
                    or not current.current_evidence_valid
                    or not current.approval_event_id
                ):
                    raise ApplicationError(
                        409, "release_activation_denied", "Current independent approval required"
                    )
                source = await self.sources.read(principal, record.command)
                if record.command.mode == "offline":
                    version = None
                    status = "offline_registered"
                else:
                    record = await self.save(principal, record, status="activating")
                    if record.command.kind == "genome":
                        version = await self.genome.activate(principal, record, source)
                    elif record.command.kind == "executor_model":
                        version = await self.models.activate(principal, record, source)
                    else:
                        raise ApplicationError(
                            409,
                            "decision_online_not_authorized",
                            "Student has no production routing authority",
                        )
                    status = "active"
                changes: dict[str, object] = {
                    "status": status,
                    "effect_version": version,
                    "reason": "user_approved_scope_only",
                }
            else:
                if record.status not in {"active", "paused", "rollback_pending"}:
                    raise ApplicationError(
                        409,
                        "release_control_state",
                        "Only an applied release can pause or roll back",
                    )
                if record.command.kind == "genome":
                    effect = await self.genome.control(principal, record, command.action)
                    version = effect.version
                else:
                    model_effect = await self.models.control(principal, record, command.action)
                    version = model_effect.version
                affected = (
                    await self.quiesce(principal, record) if command.action == "rollback" else ()
                )
                changes = {
                    "status": "paused"
                    if command.action == "pause"
                    else "rollback_pending"
                    if affected
                    else "rolled_back",
                    "effect_version": version,
                    "affected_run_ids": affected,
                    "reason": "safe_checkpoint_reconciliation_required"
                    if affected
                    else "controlled_scope_change",
                }
            result = ReleaseRecord.model_validate(
                {**record.model_dump(), **changes, "version": record.version + 1}
            )
            await self.store.put(
                "release",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                record.version,
                receipt,
                command.model_dump(mode="json"),
            )
            return result

    async def observe(
        self, principal: Principal, identity: str, command: ReleaseObservation
    ) -> ReleaseRecord:
        self.user(principal)
        record = await self.load(principal, identity)
        report = await self.deps.assess.report(principal, command.report_id)
        if report.project_id != record.command.project_id or not report.current_evidence_valid:
            raise ApplicationError(
                409, "release_observation_scope", "Current owned independent observation required"
            )
        run = await self.deps.agent.get(principal, report.run_id)
        if record.command.kind == "genome":
            snapshot = await self.deps.assets.snapshot(
                principal, record.command.project_id, run.input_asset_snapshot_id or "missing"
            )
            matches = record.id in snapshot.release_ids
        else:
            matches = (
                run.model_release_id == record.id and run.model_assignment_purpose == "operational"
            )
        if not matches or report.source != "runtime":
            raise ApplicationError(
                409,
                "release_observation_candidate",
                "Observation must come from the actual candidate cohort",
            )
        if command.report_id in record.observation_ids:
            return record
        if (
            record.version != command.expected_version
            or len(record.observation_ids) >= self.config.max_observations
        ):
            raise ApplicationError(
                409,
                "release_observation_limit",
                "Refresh release or review bounded monitoring window",
            )
        severe = (
            any(s.critical and s.verdict == "fail" for s in report.signals)
            or report.metrics.unknown_tools > 0
        )
        if severe:
            source = await self.sources.read(principal, record.command)
            incident_id = key(principal.owner, source.artifact_identity)
            old_incident = await self.store.get("incident", principal.owner, incident_id)
            if old_incident is None:
                await self.store.put(
                    "incident",
                    principal.owner,
                    incident_id,
                    {
                        "id": incident_id,
                        "version": 0,
                        "project_id": record.command.project_id,
                        "report_id": report.id,
                        "artifact_identity": source.artifact_identity,
                    },
                    None,
                )
        if severe and record.status == "active":
            record = await self.control(
                principal,
                identity,
                ReleaseControl(
                    request_id="safety-" + command.request_id,
                    expected_version=record.version,
                    action="rollback",
                ),
            )
        async with self.lock:
            latest = await self.load(principal, identity)
            if command.report_id in latest.observation_ids:
                return latest
            return await self.save(
                principal,
                latest,
                observation_ids=(*latest.observation_ids, command.report_id),
                reason="critical_observation_rollback_requested"
                if severe
                else "independent_observation_recorded",
            )

    async def verify_runtime_source(self, principal: Principal, identity: str) -> None:
        owner = principal.model_copy(update={"role": "user"})
        record = await self.load(owner, identity)
        source = await self.sources.read(owner, record.command)
        if source.blockers or source.digest != record.report.source_digest:
            raise ApplicationError(
                409,
                "release_runtime_source_invalid",
                "Publication sources were withdrawn or changed",
            )
        incident = await self.store.get(
            "incident", owner.owner, key(owner.owner, source.artifact_identity)
        )
        if incident is not None:
            raise ApplicationError(
                409,
                "release_source_incident",
                "This artifact is suspended pending independent review",
            )
        if record.validation_event_id and record.status in {"blocked", "ready", "approved"}:
            return
        if record.status not in {"active", "paused"}:
            raise ApplicationError(
                409, "release_runtime_invalid", "Runtime publication is no longer approved"
            )
