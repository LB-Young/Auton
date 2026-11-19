import asyncio
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import anyio

from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.kernel.documents import digest, key
from auton.kernel.ports import ApplicationError
from auton.training.contracts import (
    BaseModelSpec,
    TrainingBundle,
    TrainingCheckpoint,
    TrainingConfig,
    TrainingControl,
    TrainingJob,
    TrainingJobCommand,
    TrainingPlan,
    TrainingPlanCommand,
    TrainingStatus,
)
from auton.training.data import TrainingDataReader, file_digest
from auton.training.dependencies import TrainingDependencies
from auton.training.ports import TrainingBackendPort
from auton.training.store import TrainingStore


class ExecutorTraining:
    def __init__(
        self,
        config: TrainingConfig,
        deps: TrainingDependencies,
        store: TrainingStore,
        data: TrainingDataReader,
        backend: TrainingBackendPort,
    ) -> None:
        self.config, self.deps, self.store, self.data, self.backend = (
            config,
            deps,
            store,
            data,
            backend,
        )
        self.lock = asyncio.Lock()
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.closing = False

    async def start(self) -> None:
        await self.store.start()
        self.closing = False
        for owner in await self.store.owners():
            for value in await self.store.list("job", owner):
                job = TrainingJob.model_validate(value)
                if job.status in {"queued", "running"}:
                    self.launch(Principal(owner=owner, role="user"), job.id, job.status == "queued")

    async def close(self) -> None:
        self.closing = True
        for task in tuple(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks.values()), return_exceptions=True)
        await self.store.close()

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "training_user_required", "Only users can start or control training"
            )

    def status(self) -> TrainingStatus:
        return TrainingStatus(
            backend=self.config.backend,
            workload=self.config.workload,
            configured=self.config.backend != "disabled",
            model_ids=tuple(b.id for b in self.config.base_models),
        )

    def base(self, identity: str) -> BaseModelSpec:
        for spec in self.config.base_models:
            if spec.id == identity:
                return spec
        raise ApplicationError(
            409, "training_base_not_configured", "Operator must configure a base model manifest"
        )

    async def inspect(self, principal: Principal, command: TrainingPlanCommand) -> TrainingPlan:
        await self.deps.assets.resolve(principal, command.project_id)
        blockers = []
        if self.config.backend == "disabled":
            blockers.append("training_backend_disabled")
        if command.steps > self.config.max_steps:
            blockers.append("training_step_budget")
        if command.engineering_probe and command.steps > 3:
            blockers.append("engineering_probe_max_three_steps")
        base_digest = None
        try:
            spec = self.base(command.base_model_id)
            expected = "encoder_choice" if self.config.workload == "decision" else "causal_lm"
            if spec.architecture != expected:
                raise ApplicationError(
                    409,
                    "training_architecture_mismatch",
                    "Base architecture must match supervision kind",
                )
            base_digest = await self.data.base(spec)
        except ApplicationError as error:
            blockers.append(error.code)
        manifests: dict[str, str] = {}
        examples: dict[str, int] = {}
        groups: dict[str, int] = {}
        try:
            _, manifests, examples, groups = await self.data.read(principal, command)
        except ApplicationError as error:
            blockers.append(error.code)
        if not command.engineering_probe:
            for scope, minimum in (
                ("train", 20),
                ("validation", 10),
                ("replay", 10),
                ("anchor", 10),
            ):
                if groups.get(scope, 0) < minimum:
                    blockers.append("insufficient_independent_" + scope + "_groups")
        if not examples.get("train"):
            blockers.append("training_data_empty")
        frozen = {
            "command": command.model_dump(mode="json"),
            "config": self.config.digest,
            "base": base_digest,
            "datasets": manifests,
        }
        return TrainingPlan(
            id=key(principal.owner, "plan:" + command.request_id),
            command=command,
            config_digest=self.config.digest,
            manifest_digest=digest(frozen),
            base_manifest_digest=base_digest,
            dataset_manifests=manifests,
            examples=examples,
            groups=groups,
            status="blocked" if blockers else "ready",
            blockers=tuple(blockers),
        )

    async def plan(self, principal: Principal, command: TrainingPlanCommand) -> TrainingPlan:
        self.user(principal)
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(403, "training_secret_in_command", "Do not include credentials")
        async with self.lock:
            identity = key(principal.owner, "plan:" + command.request_id)
            old = await self.store.get("plan", principal.owner, identity)
            if old:
                saved = TrainingPlan.model_validate(old)
                if saved.command != command:
                    raise ApplicationError(
                        409, "training_plan_conflict", "Plan request scope is immutable"
                    )
                return await self.current(principal, saved)
            result = await self.inspect(principal, command)
            await self.store.put(
                "plan", principal.owner, identity, result.model_dump(mode="json"), None
            )
            return result

    async def current(self, principal: Principal, plan: TrainingPlan) -> TrainingPlan:
        observed = await self.inspect(principal, plan.command)
        if observed.manifest_digest != plan.manifest_digest or observed.blockers != plan.blockers:
            return plan.model_copy(
                update={
                    "status": "blocked",
                    "current_evidence_valid": False,
                    "blockers": (*observed.blockers, "training_inputs_changed"),
                }
            )
        return plan

    async def load_plan(self, principal: Principal, identity: str) -> TrainingPlan:
        value = await self.store.get("plan", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "training_plan_missing", "No owned training plan")
        return await self.current(principal, TrainingPlan.model_validate(value))

    async def plans(self, principal: Principal, project: str) -> tuple[TrainingPlan, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            [
                await self.current(principal, TrainingPlan.model_validate(v))
                for v in await self.store.list("plan", principal.owner)
                if v["command"]["project_id"] == project
            ]
        )

    async def load(self, principal: Principal, identity: str) -> TrainingJob:
        value = await self.store.get("job", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "training_job_missing", "No owned training job")
        return TrainingJob.model_validate(value)

    async def save(self, principal: Principal, old: TrainingJob, **changes: Any) -> TrainingJob:
        updated = old.model_copy(update={**changes, "version": old.version + 1})
        await self.store.put(
            "job", principal.owner, old.id, updated.model_dump(mode="json"), old.version
        )
        return updated

    async def create(self, principal: Principal, command: TrainingJobCommand) -> TrainingJob:
        self.user(principal)
        async with self.lock:
            identity = key(principal.owner, "job:" + command.request_id)
            old = await self.store.get("job", principal.owner, identity)
            if old:
                saved = TrainingJob.model_validate(old)
                if saved.command != command:
                    raise ApplicationError(409, "training_job_conflict", "Job request is immutable")
                return saved
            plan = await self.load_plan(principal, command.plan_id)
            if (
                plan.status != "ready"
                or not plan.current_evidence_valid
                or plan.manifest_digest != command.expected_plan_digest
            ):
                raise ApplicationError(
                    409, "training_plan_not_ready", "Training needs a current frozen ready plan"
                )
            if len(self.tasks) >= self.config.max_active_jobs:
                raise ApplicationError(
                    429, "training_active_limit", "Training concurrency is bounded"
                )
            result = TrainingJob(
                id=identity,
                command=command,
                project_id=plan.command.project_id,
                plan_digest=plan.manifest_digest,
                status="queued",
                created_at=self.deps.runtime.now().timestamp(),
            )
            await self.store.put(
                "job", principal.owner, identity, result.model_dump(mode="json"), None
            )
            self.launch(principal, result.id, True)
            return result

    def launch(self, principal: Principal, identity: str, fresh: bool) -> None:
        if identity not in self.tasks and not self.closing:
            task = asyncio.create_task(self.drive(principal, identity, fresh))
            self.tasks[identity] = task
            task.add_done_callback(lambda _: self.tasks.pop(identity, None))

    def worker_id(self, job: TrainingJob) -> str:
        return key(job.id, str(job.attempt))

    def directory(self, job: TrainingJob) -> Path:
        root = self.config.directory / "jobs" / job.id / str(job.attempt)
        for parent in (self.config.directory, root.parent.parent, root.parent, root):
            parent.mkdir(exist_ok=True, mode=0o700)
            if parent.is_symlink():
                raise ApplicationError(
                    409, "training_path_invalid", "Training paths cannot be symlinks"
                )
            parent.chmod(0o700)
        return root.resolve()

    async def stage(
        self, principal: Principal, job: TrainingJob, plan: TrainingPlan
    ) -> tuple[Path, str]:
        data, _, _, _ = await self.data.read(principal, plan.command)
        root = self.directory(job)
        if shutil.disk_usage(root).free < self.config.min_free_bytes:
            raise ApplicationError(
                507, "training_disk_space", "Insufficient training staging space"
            )
        manifest: dict[str, Any] = {
            "protocol": "auton-training-worker-v1",
            "workload": self.config.workload,
            "plan_digest": plan.manifest_digest,
            "command": plan.command.model_dump(mode="json"),
            "device": self.config.device,
            "tool_parser": self.base(plan.command.base_model_id).tool_parser,
            "max_wall_seconds": self.config.max_wall_seconds,
            "max_output_bytes": self.config.max_output_bytes,
            "data_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in data.items()},
        }
        if job.checkpoint:
            previous = (
                self.directory(job.model_copy(update={"attempt": job.attempt - 1})) / "output"
            )
            folder = previous / ("step-" + str(job.checkpoint.step).zfill(8))
            self.verify_checkpoint(folder, job.checkpoint, job.plan_digest)
            manifest["resume"] = job.checkpoint.model_dump(mode="json")
            baseline_path = previous / "baseline.json"
            if (
                baseline_path.is_symlink()
                or not baseline_path.is_file()
                or baseline_path.stat().st_size > 100000
            ):
                raise ApplicationError(
                    409, "training_invalid_baseline", "Baseline summary missing or oversized"
                )
            manifest["baseline"] = json.loads(baseline_path.read_text())

        def write() -> None:
            source = root / "input"
            target = root / "output"
            source.mkdir(exist_ok=True, mode=0o755)
            target.mkdir(exist_ok=True, mode=0o777)
            source.chmod(0o755)
            target.chmod(
                0o777
            )  # Enclosed by owner-only parents; writable inside non-root container.
            if source.is_symlink() or target.is_symlink():
                raise ApplicationError(409, "training_path_invalid", "No symlink staging")

            def immutable(path: Path, content: bytes) -> None:
                if path.exists() or path.is_symlink():
                    if path.is_symlink() or path.read_bytes() != content:
                        raise ApplicationError(
                            409, "training_staging_conflict", "Staged input differs"
                        )
                    return
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())

            if job.checkpoint:
                destination = source / "resume"
                destination.mkdir(exist_ok=True, mode=0o755)
                if destination.is_symlink():
                    raise ApplicationError(409, "training_path_invalid", "No symlink resume input")
                for name in job.checkpoint.files:
                    immutable(destination / name, (folder / name).read_bytes())
            for scope, content in data.items():
                immutable(source / (scope + ".jsonl"), content)
            immutable(source / "manifest.json", json.dumps(manifest, sort_keys=True).encode())

        await anyio.to_thread.run_sync(write)
        return root, digest(manifest)

    def verify_checkpoint(
        self, folder: Path, checkpoint: TrainingCheckpoint, expected: str
    ) -> None:
        if checkpoint.manifest_digest != expected or checkpoint.step < 1:
            raise ApplicationError(
                409, "training_checkpoint_scope", "Checkpoint has another training lineage"
            )
        if set(checkpoint.files) != {"adapter.safetensors", "state.safetensors"}:
            raise ApplicationError(
                409, "training_checkpoint_files", "Only safe tensor training state can resume"
            )
        for name, checksum in checkpoint.files.items():
            path = folder / name
            if (
                folder.is_symlink()
                or path.is_symlink()
                or not path.is_file()
                or file_digest(path) != checksum
            ):
                raise ApplicationError(
                    409, "training_checkpoint_corrupt", "Checkpoint digest differs"
                )

    def read_progress(self, job: TrainingJob) -> TrainingCheckpoint | None:
        output = self.directory(job) / "output"
        total = 0
        for path in output.rglob("*"):
            if path.is_symlink():
                raise ApplicationError(
                    409, "training_output_symlink", "Worker outputs cannot be symlinks"
                )
            if path.is_file():
                total += path.stat().st_size
        if total > self.config.max_output_bytes:
            raise ApplicationError(
                429, "training_output_limit", "Worker disk output budget exceeded"
            )
        progress = output / "progress.json"
        if not progress.exists():
            return None
        if progress.stat().st_size > 10000:
            raise ApplicationError(
                409, "training_invalid_progress", "Oversized checkpoint manifest"
            )
        value = json.loads(progress.read_text())
        checkpoint = TrainingCheckpoint.model_validate(value["checkpoint"])
        if value["folder"] != "step-" + str(checkpoint.step).zfill(8):
            raise ApplicationError(409, "training_invalid_progress", "Invalid checkpoint directory")
        self.verify_checkpoint(output / value["folder"], checkpoint, job.plan_digest)
        return checkpoint

    async def drive(self, principal: Principal, identity: str, fresh: bool) -> None:
        worker_manifest = ""
        job = await self.load(principal, identity)
        try:
            plan = await self.load_plan(principal, job.command.plan_id)
            if plan.status != "ready":
                raise ApplicationError(
                    409, "training_source_invalid", "Training inputs no longer qualify"
                )
            if fresh:
                root, worker_manifest = await self.stage(principal, job, plan)
                async with self.lock:
                    latest = await self.load(principal, identity)
                    if latest.status != "queued":
                        return
                    job = await self.save(
                        principal,
                        latest,
                        status="running",
                        started_at=self.deps.runtime.now().timestamp(),
                    )
                    await self.backend.start(
                        self.worker_id(job),
                        root,
                        self.base(plan.command.base_model_id).directory.resolve(),
                        worker_manifest,
                    )
            else:
                root = self.directory(job)
                worker_manifest = digest(json.loads((root / "input/manifest.json").read_text()))
            while True:
                async with self.lock:
                    job = await self.load(principal, identity)
                    if job.status != "running":
                        return
                current = await self.load_plan(principal, job.command.plan_id)
                if current.status != "ready" or not current.current_evidence_valid:
                    raise ApplicationError(
                        409, "training_source_invalid", "Sources or rights changed; stop worker"
                    )
                if (
                    job.started_at is not None
                    and self.deps.runtime.now().timestamp() - job.started_at
                    > self.config.max_wall_seconds
                ):
                    raise ApplicationError(
                        429, "training_wall_budget", "Training wall budget exceeded"
                    )
                state = await self.backend.state(self.worker_id(job), worker_manifest)
                checkpoint = await anyio.to_thread.run_sync(self.read_progress, job)
                if checkpoint and (
                    checkpoint.step < job.completed_steps or checkpoint.step > plan.command.steps
                ):
                    raise ApplicationError(
                        409,
                        "training_invalid_progress",
                        "Worker step count is outside frozen budget",
                    )
                if checkpoint and checkpoint != job.checkpoint:
                    async with self.lock:
                        job = await self.save(
                            principal,
                            await self.load(principal, identity),
                            checkpoint=checkpoint,
                            completed_steps=checkpoint.step,
                        )
                if state.status == "succeeded":
                    await self.finish(principal, job, plan)
                    return
                if state.status != "running":
                    raise ApplicationError(
                        409,
                        "training_worker_oom"
                        if state.reason == "oom"
                        else "training_worker_" + state.status,
                        state.reason or "Worker identity missing; never redispatch automatically",
                    )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            if worker_manifest:
                await self.backend.stop(self.worker_id(job), worker_manifest)
            if self.closing:
                async with self.lock:
                    latest = await self.load(principal, identity)
                    if latest.status in {"queued", "running"}:
                        await self.save(
                            principal,
                            latest,
                            status="interrupted",
                            reason="service_shutdown_manual_resume",
                        )
            raise
        except Exception as error:
            stopped = False
            if worker_manifest:
                try:
                    await self.backend.stop(self.worker_id(job), worker_manifest)
                    stopped = True
                except Exception:
                    pass
            async with self.lock:
                latest = await self.load(principal, identity)
                if latest.status in {"queued", "running"}:
                    code = (
                        error.code
                        if isinstance(error, ApplicationError)
                        else "training_worker_protocol_error"
                    )
                    await self.save(
                        principal,
                        latest,
                        status="failed",
                        reason=code + ("" if stopped else ":stop_unconfirmed"),
                    )

    async def finish(self, principal: Principal, job: TrainingJob, plan: TrainingPlan) -> None:
        if job.completed_steps != plan.command.steps or job.checkpoint is None:
            raise ApplicationError(
                409, "training_incomplete_result", "No complete committed checkpoint"
            )
        path = self.directory(job) / "output/result.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100000:
            raise ApplicationError(
                409, "training_invalid_result", "Worker result missing or oversized"
            )
        result = json.loads(path.read_text())
        if (
            result.get("protocol") != "auton-training-worker-v1"
            or result.get("plan_digest") != job.plan_digest
        ):
            raise ApplicationError(
                409, "training_result_scope", "Result is for another frozen plan"
            )
        if not (await self.load_plan(principal, plan.id)).current_evidence_valid:
            raise ApplicationError(
                409, "training_source_invalid", "Sources changed before candidate registration"
            )
        auxiliary = {"result.json": file_digest(path)}
        prediction_path = path.parent / "predictions-validation.json"
        if prediction_path.exists():
            if prediction_path.is_symlink() or prediction_path.stat().st_size > 1000000:
                raise ApplicationError(
                    409, "training_invalid_predictions", "Invalid prediction evidence"
                )
            auxiliary[prediction_path.name] = file_digest(prediction_path)
        bundle = TrainingBundle(
            id=key(job.id, "bundle"),
            project_id=job.project_id,
            job_id=job.id,
            plan_id=plan.id,
            files=job.checkpoint.files,
            lineage_digest=job.plan_digest,
            metrics=result["metrics"],
            auxiliary_files=auxiliary,
            source="test" if self.deps.test_source else "runtime",
            kind=self.config.workload,
            release_blockers=(
                "independent_deployment_evaluation_required",
                "protected_release_window_required",
                "engineering_probe" if plan.command.engineering_probe else "quality_gate_pending",
            ),
        )
        async with self.lock:
            latest = await self.load(principal, job.id)
            if latest.status != "running":
                return
            old = await self.store.get("bundle", principal.owner, bundle.id)
            if old is None:
                await self.store.put(
                    "bundle", principal.owner, bundle.id, bundle.model_dump(mode="json"), None
                )
            elif TrainingBundle.model_validate(old) != bundle:
                raise ApplicationError(
                    409, "training_bundle_conflict", "Candidate bundle is immutable"
                )
            await self.save(
                principal,
                await self.load(principal, job.id),
                status="succeeded",
                bundle_id=bundle.id,
                metrics=bundle.metrics,
            )

    async def get(self, principal: Principal, identity: str) -> TrainingJob:
        self.user(principal)
        return await self.load(principal, identity)

    async def jobs(self, principal: Principal, project: str) -> tuple[TrainingJob, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            TrainingJob.model_validate(v)
            for v in await self.store.list("job", principal.owner)
            if v["project_id"] == project
        )

    async def bundles(self, principal: Principal, project: str) -> tuple[TrainingBundle, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        output = []
        for value in await self.store.list("bundle", principal.owner):
            if value["project_id"] == project:
                bundle = TrainingBundle.model_validate(value)
                source_valid = False
                try:
                    plan_value = await self.store.get("plan", principal.owner, bundle.plan_id)
                    if plan_value is not None:
                        original = TrainingPlan.model_validate(plan_value)
                        _, manifests, _, _ = await self.data.read(principal, original.command)
                        base_digest = await self.data.base(
                            self.base(original.command.base_model_id)
                        )
                        source_valid = (
                            manifests == original.dataset_manifests
                            and base_digest == original.base_manifest_digest
                        )
                except (ApplicationError, OSError, ValueError):
                    pass
                intact = False
                try:
                    job = await self.load(principal, bundle.job_id)
                    checkpoint = await anyio.to_thread.run_sync(self.read_progress, job)
                    intact = checkpoint is not None and checkpoint.files == bundle.files
                except (ApplicationError, OSError, ValueError):
                    pass
                output.append(bundle.model_copy(update={"source_current": source_valid and intact}))
        return tuple(output)

    async def control(
        self, principal: Principal, identity: str, command: TrainingControl
    ) -> TrainingJob:
        self.user(principal)
        async with self.lock:
            if await self.store.receipt(
                principal.owner,
                command.request_id,
                "job",
                identity,
                command.model_dump(mode="json"),
            ):
                return await self.load(principal, identity)
            job = await self.load(principal, identity)
            if job.version != command.expected_version:
                raise ApplicationError(
                    409, "training_version_changed", "Refresh current job before control"
                )
            root = self.directory(job)
            manifest_path = root / "input/manifest.json"
            manifest = (
                digest(json.loads(manifest_path.read_text())) if manifest_path.exists() else ""
            )
            if command.action == "cancel":
                if job.status not in {"queued", "running", "interrupted"}:
                    raise ApplicationError(
                        409, "training_cancel_terminal", "Terminal jobs cannot be cancelled"
                    )
                if manifest:
                    await self.backend.stop(self.worker_id(job), manifest)
                status = "cancelled"
                checkpoint = (
                    await anyio.to_thread.run_sync(self.read_progress, job) if manifest else None
                )
                changes: dict[str, Any] = {"status": status, "reason": "user_cancelled"}
                if checkpoint:
                    changes.update(checkpoint=checkpoint, completed_steps=checkpoint.step)
            else:
                if job.status not in {"failed", "interrupted", "cancelled"} or not job.checkpoint:
                    raise ApplicationError(
                        409,
                        "training_resume_unavailable",
                        "Resume needs a verified committed checkpoint",
                    )
                if (
                    not manifest
                    or (await self.backend.state(self.worker_id(job), manifest)).status == "running"
                ):
                    raise ApplicationError(
                        409,
                        "training_previous_worker_active",
                        "Previous worker must be confirmed stopped",
                    )
                if identity in self.tasks:
                    raise ApplicationError(
                        409,
                        "training_previous_monitor_active",
                        "Wait for the previous monitor to stop",
                    )
                plan = await self.load_plan(principal, job.command.plan_id)
                if plan.status != "ready" or len(self.tasks) >= self.config.max_active_jobs:
                    raise ApplicationError(
                        409,
                        "training_resume_blocked",
                        "Current sources and a free worker slot are required",
                    )
                self.verify_checkpoint(
                    root / "output" / ("step-" + str(job.checkpoint.step).zfill(8)),
                    job.checkpoint,
                    job.plan_digest,
                )
                changes = {
                    "status": "queued",
                    "attempt": job.attempt + 1,
                    "reason": "manual_resume",
                    "started_at": None,
                }
            updated = job.model_copy(update={**changes, "version": job.version + 1})
            await self.store.put(
                "job",
                principal.owner,
                identity,
                updated.model_dump(mode="json"),
                job.version,
                command.request_id,
                command.model_dump(mode="json"),
            )
            task = self.tasks.get(identity)
            if task:
                task.cancel()
            if command.action == "resume":
                self.launch(principal, identity, True)
            return updated
