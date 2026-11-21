import asyncio
from typing import Any

from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.ports import ApplicationError
from auton.operations.backup import OperationsBackups
from auton.operations.contracts import (
    BackgroundJob,
    BackupCommand,
    BackupManifest,
    OperationsAlert,
    OperationsConfig,
    OperationsControl,
    OperationsStatus,
    RestoreCommand,
    Schedule,
    ScheduleCommand,
    TelemetrySample,
    TrainingOperation,
)
from auton.operations.dependencies import OperationsDependencies
from auton.operations.pipelines import Pipelines, Progress
from auton.operations.queue import TERMINAL, JobQueue
from auton.operations.telemetry import RetentionPolicy, Telemetry
from auton.training.contracts import TrainingControl


class Scheduler:
    def __init__(
        self,
        config: OperationsConfig,
        deps: OperationsDependencies,
        store: VersionedDocumentStore,
        queue: JobQueue,
        telemetry: Telemetry,
        retention: RetentionPolicy,
    ) -> None:
        self.config, self.deps, self.store, self.queue, self.telemetry, self.retention = (
            config,
            deps,
            store,
            queue,
            telemetry,
            retention,
        )
        self.pipelines = Pipelines(deps)
        self.backups = OperationsBackups(config, deps, store)
        self.lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None
        self.closing = False
        self.last_error = ""

    async def start(self) -> None:
        await self.store.start()
        self.telemetry.start()
        self.closing = False
        if self.config.enabled:
            self.task = asyncio.create_task(self.loop())

    async def close(self) -> None:
        self.closing = True
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        async with self.lock:
            await self.store.close()

    async def loop(self) -> None:
        while not self.closing:
            try:
                owners = [
                    str(r[0])
                    for r in self.store.database().execute(
                        "SELECT DISTINCT owner FROM heads WHERE kind='schedule'"
                    )
                ]
                for owner in owners:
                    await self.tick(Principal(owner=owner, role="user"))
                self.last_error = ""
            except ApplicationError as error:
                self.last_error = error.code
            except Exception:
                self.last_error = "background_internal_error"
            await asyncio.sleep(self.config.poll_seconds)

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "background_user_required", "Only users grant/control background work"
            )

    def status(self) -> OperationsStatus:
        return OperationsStatus(
            enabled=self.config.enabled,
            observer_only=self.config.observer_only,
            config_digest=self.config.digest,
            last_error=self.last_error,
        )

    async def paused(self, principal: Principal) -> bool:
        value = await self.store.get("control", principal.owner, key(principal.owner, "control"))
        return bool(value and value["paused"])

    async def schedules(
        self, principal: Principal, project: str | None = None
    ) -> tuple[Schedule, ...]:
        self.user(principal)
        if project:
            await self.deps.assets.resolve(principal, project)
        return tuple(
            Schedule.model_validate(v)
            for v in await self.store.list("schedule", principal.owner)
            if project is None or v["project_id"] == project
        )

    async def schedule(self, principal: Principal, command: ScheduleCommand) -> Schedule:
        self.user(principal)
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(
                403, "background_secret_input", "Credentials cannot enter background commands"
            )
        if self.config.observer_only and command.operation.kind not in {"telemetry", "retention"}:
            raise ApplicationError(
                403,
                "background_observer_only",
                "Observer mode cannot call models, train, or change source rights",
            )
        await self.deps.assets.resolve(principal, command.project_id)
        identity = key(principal.owner, "schedule:" + command.request_id)
        async with self.lock:
            value = await self.store.get("schedule", principal.owner, identity)
            if value:
                old = Schedule.model_validate(value)
                if old.command != command:
                    raise ApplicationError(
                        409, "background_schedule_conflict", "Schedule input/grant is immutable"
                    )
                return old
            now = self.deps.runtime.now().timestamp()
            if (
                command.expires_at <= now
                or command.budget_microusd > self.config.owner_budget_microusd
            ):
                raise ApplicationError(
                    409, "background_grant_invalid", "An unexpired bounded grant is required"
                )
            for dependency in command.depends_on:
                prior = await self.queue.get(principal.owner, dependency)
                if prior.project_id != command.project_id:
                    raise ApplicationError(
                        403,
                        "background_dependency_scope",
                        "Dependencies must be owned in the same project",
                    )
            result = Schedule(
                id=identity,
                project_id=command.project_id,
                command=command,
                config_digest=self.config.digest,
                enabled=command.enabled,
                next_due=now,
                reason="ready" if command.enabled else "user_disabled",
            )
            await self.store.put(
                "schedule", principal.owner, identity, result.model_dump(mode="json"), None
            )
            return result

    async def save_schedule(self, principal: Principal, old: Schedule, **changes: Any) -> Schedule:
        result = Schedule.model_validate(
            {**old.model_dump(), **changes, "version": old.version + 1}
        )
        await self.store.put(
            "schedule", principal.owner, old.id, result.model_dump(mode="json"), old.version
        )
        return result

    async def control_schedule(
        self, principal: Principal, identity: str, command: OperationsControl
    ) -> Schedule:
        self.user(principal)
        async with self.lock:
            value = await self.store.get("schedule", principal.owner, identity)
            if value is None:
                raise ApplicationError(404, "background_schedule_missing", "No owned schedule")
            old = Schedule.model_validate(value)
            if await self.store.receipt(
                principal.owner,
                command.request_id,
                "schedule",
                identity,
                command.model_dump(mode="json"),
            ):
                return old
            if old.version != command.expected_version:
                raise ApplicationError(
                    409, "background_schedule_changed", "Refresh the current schedule"
                )
            if command.action == "resume" and (
                not old.command.confirm_background_actions
                or old.command.expires_at <= self.deps.runtime.now().timestamp()
                or old.config_digest != self.config.digest
            ):
                raise ApplicationError(
                    409, "background_grant_invalid", "Current explicit scoped grant is required"
                )
            result = old.model_copy(
                update={
                    "version": old.version + 1,
                    "enabled": command.action == "resume",
                    "reason": "user_" + command.action,
                }
            )
            await self.store.put(
                "schedule",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                old.version,
                command.request_id,
                command.model_dump(mode="json"),
            )
            return result

    async def control_owner(self, principal: Principal, paused: bool) -> bool:
        self.user(principal)
        async with self.lock:
            identity = key(principal.owner, "control")
            value = await self.store.get("control", principal.owner, identity)
            if value and value["paused"] == paused:
                return paused
            version = int(value["version"]) + 1 if value else 0
            await self.store.put(
                "control",
                principal.owner,
                identity,
                {"id": identity, "version": version, "paused": paused},
                version - 1 if value else None,
            )
            return paused

    async def jobs(self, principal: Principal, project: str) -> tuple[BackgroundJob, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return await self.queue.jobs(principal.owner, project)

    async def control_job(
        self, principal: Principal, identity: str, command: OperationsControl
    ) -> BackgroundJob:
        self.user(principal)
        async with self.lock:
            job = await self.queue.get(principal.owner, identity)
            if await self.store.receipt(
                principal.owner,
                command.request_id,
                "job",
                identity,
                command.model_dump(mode="json"),
            ):
                return job
            if job.version != command.expected_version or (
                job.lease_token and job.lease_until > self.deps.runtime.now().timestamp()
            ):
                raise ApplicationError(
                    409, "background_job_changed", "Job is changed or still leased"
                )
            if job.status in TERMINAL:
                raise ApplicationError(
                    409,
                    "background_job_terminal",
                    "Terminal jobs require a new reviewed source, not an automatic restart",
                )
            if (
                command.action in {"pause", "cancel"}
                and job.external_id
                and isinstance(job.operation, TrainingOperation)
            ):
                trainer = self.pipelines.trainer(job.operation.kind)
                trained = await trainer.get(principal, job.external_id)
                if trained.status in {"queued", "running", "interrupted"}:
                    await trainer.control(
                        principal,
                        trained.id,
                        TrainingControl(
                            request_id="ops-user-stop-" + key(job.id, command.request_id)[:60],
                            expected_version=trained.version,
                            action="cancel",
                        ),
                    )
            status = (
                "cancelled"
                if command.action == "cancel"
                else "paused"
                if command.action == "pause"
                else "waiting"
                if job.external_id
                else "queued"
            )
            return await self.queue.save(
                principal.owner,
                job,
                status=status,
                reason="user_" + command.action,
                request_id=command.request_id,
                request_command=command.model_dump(mode="json"),
                next_due=self.deps.runtime.now().timestamp(),
            )

    async def tick(self, principal: Principal) -> tuple[BackgroundJob, ...]:
        self.user(principal)
        async with self.lock:
            now = self.deps.runtime.now().timestamp()
            enabled = self.config.enabled and not await self.paused(principal)
            schedules = await self.schedules(principal)
            mapping = {s.id: s for s in schedules}
            if enabled:
                for schedule in schedules:
                    if (
                        not schedule.enabled
                        or schedule.config_digest != self.config.digest
                        or schedule.command.expires_at <= now
                        or schedule.next_due > now
                        or (schedule.cycle and not schedule.command.repeat)
                    ):
                        continue
                    job = BackgroundJob(
                        id=key(principal.owner, "job:" + schedule.id + ":" + str(schedule.cycle)),
                        project_id=schedule.project_id,
                        schedule_id=schedule.id,
                        cycle=schedule.cycle,
                        operation=schedule.command.operation,
                        created_at=now,
                        next_due=now,
                    )
                    await self.queue.add(principal.owner, job)
                    updated = await self.save_schedule(
                        principal,
                        schedule,
                        cycle=schedule.cycle + 1,
                        next_due=now + schedule.command.interval_seconds,
                        reason="enqueued",
                    )
                    mapping[schedule.id] = updated
            jobs = await self.queue.jobs(principal.owner)
            priorities = {
                "withdraw": 0,
                "telemetry": 1,
                "retention": 1,
                "review": 2,
                "dataset": 3,
                "export": 3,
                "executor_training": 4,
                "decision_training": 4,
            }
            ordered = sorted(
                jobs,
                key=lambda j: (
                    priorities[j.operation.kind],
                    0 if j.external_id else 1,
                    j.next_due,
                    j.created_at,
                    j.id,
                ),
            )
            processed = 0
            for job in ordered:
                if (
                    processed >= self.config.max_jobs_per_tick
                    or job.status in TERMINAL
                    or job.status == "paused"
                    and job.reason == "user_pause"
                ):
                    continue
                current_schedule = mapping.get(job.schedule_id)
                if current_schedule is None:
                    continue
                schedule = current_schedule
                permitted = (
                    enabled
                    and (
                        not self.config.observer_only
                        or job.operation.kind in {"telemetry", "retention"}
                    )
                    and schedule.enabled
                    and schedule.config_digest == self.config.digest
                    and schedule.command.expires_at > now
                    and schedule.command.window.allows(self.deps.runtime.now().hour)
                )
                foreground = self.deps.agent.foreground_active() > 0
                dependency_jobs = [
                    await self.queue.get(principal.owner, i) for i in schedule.command.depends_on
                ]
                reason = ""
                if not job.external_id and schedule.command.expires_at <= now:
                    if not (job.lease_token and job.lease_until > now):
                        await self.queue.save(
                            principal.owner,
                            job,
                            status="attention",
                            reason="background_grant_expired",
                        )
                    continue
                if not job.external_id:
                    if not permitted:
                        reason = "disabled_expired_or_outside_resource_window"
                    elif foreground and job.operation.kind not in {
                        "withdraw",
                        "telemetry",
                        "retention",
                    }:
                        reason = "foreground_priority"
                    elif any(d.status != "succeeded" for d in dependency_jobs):
                        reason = "waiting_for_approved_dependencies"
                if reason:
                    if job.reason != reason and not (job.lease_token and job.lease_until > now):
                        await self.queue.save(principal.owner, job, reason=reason)
                    continue
                leased = await self.queue.claim(principal, job.id)
                if leased is None:
                    continue
                processed += 1
                await self.process(
                    principal,
                    leased,
                    schedule,
                    foreground if self.config.preempt_training else False,
                    permitted,
                )
            return await self.queue.jobs(principal.owner)

    async def process(
        self,
        principal: Principal,
        job: BackgroundJob,
        schedule: Schedule,
        foreground: bool,
        permitted: bool,
    ) -> None:
        token = job.lease_token or ""
        try:
            if not job.dispatched:
                reservation = (
                    self.deps.review_cost_reservation if job.operation.kind == "review" else 0
                )
                jobs = await self.queue.jobs(principal.owner)
                occupied = sum(
                    j.actual_cost_microusd
                    if j.status in TERMINAL and j.actual_cost_microusd is not None
                    else j.reserved_cost_microusd
                    for j in jobs
                    if j.id != job.id
                )
                if (
                    reservation > schedule.command.budget_microusd
                    or occupied + reservation > self.config.owner_budget_microusd
                ):
                    raise ApplicationError(
                        409,
                        "background_budget_exhausted",
                        "Explicit reserved review budget is insufficient",
                    )
                sample_keys: tuple[str, ...] = ()
                if isinstance(job.operation, TrainingOperation):
                    sample_keys = await self.pipelines.sample_keys(principal, schedule)
                    consumed = {
                        s for j in jobs if j.id != job.id and j.dispatched for s in j.sample_keys
                    }
                    if len(set(sample_keys) - consumed) < self.config.min_new_training_examples:
                        raise ApplicationError(
                            409,
                            "background_fresh_data_insufficient",
                            "Require new qualified examples; a renamed plan is not new data",
                        )
                job = await self.queue.save(
                    principal.owner,
                    job,
                    token,
                    reserved_cost_microusd=reservation,
                    sample_keys=sample_keys,
                    dispatched=True,
                    actual_cost_microusd=None if reservation else 0,
                )
            if job.operation.kind == "telemetry":
                sample = await self.telemetry.collect(principal, job.project_id, job.id)
                progress = Progress(
                    "succeeded", result_digest=digest(sample.model_dump(mode="json"))
                )
            elif job.operation.kind == "retention":
                deleted = self.retention.apply(
                    principal, job.project_id, self.deps.runtime.now().timestamp()
                )
                progress = Progress(
                    "succeeded",
                    reason="owned_monitor_samples_deleted:" + str(deleted),
                    result_digest=digest({"deleted": deleted}),
                )
            else:
                progress = await asyncio.wait_for(
                    self.pipelines.execute(principal, job, schedule, foreground, permitted),
                    timeout=self.config.dispatch_timeout_seconds,
                )
            await self.queue.save(
                principal.owner,
                job,
                token,
                status=progress.status,
                reason=progress.reason,
                failures=0,
                external_id=progress.external_id,
                result_digest=progress.result_digest,
                actual_cost_microusd=progress.actual_cost,
                lease_token=None,
                lease_until=0,
                next_due=self.deps.runtime.now().timestamp() + self.config.poll_seconds,
            )
        except asyncio.CancelledError:
            raise  # Durable lease survives; never manufacture an acknowledgement.
        except (ApplicationError, TimeoutError) as error:
            code = (
                error.code if isinstance(error, ApplicationError) else "background_dispatch_timeout"
            )
            retry = (
                isinstance(error, TimeoutError)
                or isinstance(error, ApplicationError)
                and error.status >= 500
            ) and job.failures + 1 < self.config.max_attempts
            # Retrying calls uses exactly the same public request ID. Source modules
            # reconcile dispatch uncertainty and forbid automatic unknown-call replay.
            await self.queue.save(
                principal.owner,
                job,
                token,
                status="queued" if retry else "attention",
                reason=code,
                failures=job.failures + 1,
                lease_token=None,
                lease_until=0,
                next_due=self.deps.runtime.now().timestamp()
                + min(3600, self.config.backoff_seconds * 2 ** max(0, job.attempts - 1)),
            )

        except Exception:
            # Unknown adapter/programming failures are not silently retried.
            await self.queue.save(
                principal.owner,
                job,
                token,
                status="attention",
                reason="background_operation_protocol_error",
                failures=job.failures + 1,
                lease_token=None,
                lease_until=0,
            )

    async def samples(self, principal: Principal, project: str) -> tuple[TelemetrySample, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return await self.telemetry.samples(principal, project)

    async def alerts(self, principal: Principal, project: str) -> tuple[OperationsAlert, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return await self.telemetry.alerts(principal, project)

    async def backup(self, principal: Principal, command: BackupCommand) -> BackupManifest:
        self.user(principal)
        async with self.lock:
            return await self.backups.create(principal, command)

    async def restore(self, principal: Principal, command: RestoreCommand) -> BackupManifest:
        self.user(principal)
        async with self.lock:
            return await self.backups.restore(principal, command)
