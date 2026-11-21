"""Allowlisted public-port calls. No release, approval, raw shell, or credential grant."""

from dataclasses import dataclass

from auton.constitution.config import Principal
from auton.kernel.documents import digest
from auton.kernel.ports import ApplicationError
from auton.operations.contracts import BackgroundJob, Schedule, TrainingOperation
from auton.operations.dependencies import OperationsDependencies
from auton.training.contracts import TrainingControl, TrainingJob, TrainingPlan
from auton.training.ports import ExecutorTrainingPort


@dataclass(frozen=True)
class Progress:
    status: str
    external_id: str | None = None
    reason: str = ""
    result_digest: str | None = None
    actual_cost: int | None = 0


class Pipelines:
    def __init__(self, deps: OperationsDependencies) -> None:
        self.deps = deps

    def trainer(self, kind: str) -> ExecutorTrainingPort:
        return (
            self.deps.decision_training
            if kind == "decision_training"
            else self.deps.executor_training
        )

    async def training_plan(self, principal: Principal, schedule: Schedule) -> TrainingPlan:
        operation = schedule.command.operation
        assert isinstance(operation, TrainingOperation)
        plans = await self.trainer(operation.kind).plans(principal, schedule.project_id)
        plan = next((p for p in plans if p.id == operation.command.plan_id), None)
        if (
            plan is None
            or plan.status != "ready"
            or not plan.current_evidence_valid
            or plan.manifest_digest != operation.command.expected_plan_digest
            or plan.command.engineering_probe
        ):
            raise ApplicationError(
                409,
                "background_training_plan_invalid",
                "A current qualified non-probe frozen plan is required",
            )
        return plan

    async def sample_keys(self, principal: Principal, schedule: Schedule) -> tuple[str, ...]:
        plan = await self.training_plan(principal, schedule)
        artifact, _ = await self.deps.datasets.read_artifact(
            principal, plan.command.train_artifact_id
        )
        snapshot = await self.deps.datasets.get(principal, artifact.snapshot_id)
        if (
            snapshot.command.project_id != schedule.project_id
            or not snapshot.current_evidence_valid
            or not snapshot.training_ready
        ):
            raise ApplicationError(
                409, "background_training_sources_invalid", "Current owned train data is required"
            )
        return tuple(
            sorted(
                {
                    digest(
                        {"kind": e.kind, "input": e.normalized_input, "target": e.normalized_target}
                    )
                    for e in snapshot.examples
                    if e.split == "train"
                }
            )
        )

    async def execute(
        self,
        principal: Principal,
        job: BackgroundJob,
        schedule: Schedule,
        foreground: bool,
        permitted: bool,
    ) -> Progress:
        operation = job.operation
        request = "ops-" + job.id[:60]
        if operation.kind == "review":
            record = (
                await self.deps.review.get(principal, job.external_id)
                if job.external_id
                else await self.deps.review.review(
                    principal, operation.command.model_copy(update={"request_id": request})
                )
            )
            stages = [s for s in (record.stage_a, record.stage_b) if s is not None]
            unknown = any(s.dispatch == "unknown" or s.cost_microusd is None for s in stages)
            complete = record.status in {"complete", "blocked"}
            return Progress(
                "attention"
                if unknown
                else "succeeded"
                if record.status == "complete"
                else "failed"
                if record.status == "blocked"
                else "waiting",
                record.id,
                "review_requires_attention" if unknown else record.status,
                digest(record.model_dump(mode="json")),
                None
                if unknown
                else sum(s.cost_microusd or 0 for s in stages)
                if complete
                else None,
            )
        if isinstance(operation, TrainingOperation):
            trainer = self.trainer(operation.kind)
            if job.external_id:
                trained = await trainer.get(principal, job.external_id)
                if (foreground or not permitted) and trained.status in {"queued", "running"}:
                    trained = await trainer.control(
                        principal,
                        trained.id,
                        TrainingControl(
                            request_id="ops-stop-"
                            + digest({"job": job.id, "version": trained.version})[:60],
                            expected_version=trained.version,
                            action="cancel",
                        ),
                    )
                    return Progress(
                        "paused", trained.id, "foreground_preempted_checkpoint_required"
                    )
                if trained.status in {"interrupted", "cancelled"}:
                    if (
                        operation.allow_checkpoint_resume
                        and trained.checkpoint
                        and permitted
                        and not foreground
                    ):
                        await self.training_plan(principal, schedule)
                        trained = await trainer.control(
                            principal,
                            trained.id,
                            TrainingControl(
                                request_id="ops-resume-"
                                + digest({"job": job.id, "version": trained.version})[:60],
                                expected_version=trained.version,
                                action="resume",
                            ),
                        )
                    else:
                        return Progress(
                            "paused",
                            trained.id,
                            "checkpoint_resume_requires_grant_window_and_stopped_worker",
                        )
            else:
                await self.training_plan(principal, schedule)
                trained = await trainer.create(
                    principal, operation.command.model_copy(update={"request_id": request})
                )
            return self.training_progress(trained)
        if operation.kind == "dataset":
            value = await self.deps.datasets.build(
                principal, operation.command.model_copy(update={"request_id": request})
            )
            return Progress(
                "succeeded"
                if value.current_evidence_valid and value.status == "ready"
                else "attention",
                value.id,
                value.status,
                value.content_digest,
            )
        if operation.kind == "export":
            value_artifact = await self.deps.datasets.export(
                principal,
                operation.snapshot_id,
                operation.command.model_copy(update={"request_id": request}),
            )
            return Progress(
                "succeeded",
                value_artifact.id,
                "exported",
                digest(value_artifact.model_dump(mode="json")),
            )
        if operation.kind == "withdraw":
            affected = await self.deps.datasets.withdraw(
                principal, operation.command.model_copy(update={"request_id": request})
            )
            return Progress("succeeded", reason="rights_withdrawn", result_digest=digest(affected))
        raise ApplicationError(
            422, "background_operation_unhandled", "Maintenance operations run in the scheduler"
        )

    @staticmethod
    def training_progress(job: TrainingJob) -> Progress:
        status = (
            "succeeded"
            if job.status == "succeeded"
            else "attention"
            if job.status in {"failed", "blocked"}
            else "waiting"
        )
        return Progress(status, job.id, job.reason, digest(job.model_dump(mode="json")))
