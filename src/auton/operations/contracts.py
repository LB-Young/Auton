from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from auton.datasets.contracts import DatasetBuild, DatasetWithdrawal, Digest, ExportCommand, Id
from auton.decision_review.contracts import ReviewCommand
from auton.kernel.documents import digest
from auton.model.contracts import Contract
from auton.training.contracts import TrainingJobCommand


class OperationsConfig(Contract):
    directory: Path = Path(".auton_local/operations")
    enabled: bool = False
    observer_only: bool = False
    poll_seconds: float = Field(default=5, ge=1, le=60)
    lease_seconds: int = Field(default=120, ge=60, le=3600)
    dispatch_timeout_seconds: int = Field(default=30, ge=1, le=50)
    max_jobs_per_tick: int = Field(default=2, ge=1, le=8)
    max_queued_jobs: int = Field(default=200, ge=10, le=1000)
    max_documents: int = Field(default=100000, ge=1000, le=1000000)
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_seconds: int = Field(default=30, ge=1, le=600)
    owner_budget_microusd: int = Field(default=1000000, ge=0, le=100000000)
    min_new_training_examples: int = Field(default=20, ge=20, le=10000)
    preempt_training: bool = True
    sample_retention_days: int = Field(default=30, ge=1, le=365)
    max_samples: int = Field(default=1000, ge=20, le=10000)
    drift_delta: float = Field(default=0.2, ge=0.1, le=1)
    backlog_alert: int = Field(default=20, ge=1, le=1000)

    @property
    def digest(self) -> str:
        return digest(
            self.model_dump(mode="json", exclude={"directory", "enabled", "poll_seconds"})
        )


class ReviewOperation(Contract):
    kind: Literal["review"]
    command: ReviewCommand


class DatasetOperation(Contract):
    kind: Literal["dataset"]
    command: DatasetBuild


class ExportOperation(Contract):
    kind: Literal["export"]
    snapshot_id: Digest
    command: ExportCommand


class WithdrawOperation(Contract):
    kind: Literal["withdraw"]
    command: DatasetWithdrawal


class TrainingOperation(Contract):
    kind: Literal["executor_training", "decision_training"]
    command: TrainingJobCommand
    allow_checkpoint_resume: bool = False


class MaintenanceOperation(Contract):
    kind: Literal["telemetry", "retention"]


Operation = Annotated[
    ReviewOperation
    | DatasetOperation
    | ExportOperation
    | WithdrawOperation
    | TrainingOperation
    | MaintenanceOperation,
    Field(discriminator="kind"),
]


class ResourceWindow(Contract):
    start_hour_utc: int = Field(default=0, ge=0, le=23)
    end_hour_utc: int = Field(default=24, ge=1, le=24)

    def allows(self, hour: int) -> bool:
        start, end = self.start_hour_utc, self.end_hour_utc
        return start <= hour < end if start < end else hour >= start or hour < end


class ScheduleCommand(Contract):
    request_id: Id
    project_id: Id
    operation: Operation
    enabled: bool = False
    confirm_background_actions: bool = False
    expires_at: float = Field(gt=0, allow_inf_nan=False)
    interval_seconds: int = Field(default=3600, ge=30, le=604800)
    repeat: bool = False
    window: ResourceWindow = Field(default_factory=ResourceWindow)
    depends_on: tuple[Digest, ...] = Field(default=(), max_length=8)
    budget_microusd: int = Field(default=0, ge=0, le=100000000)

    @model_validator(mode="after")
    def bounded(self) -> "ScheduleCommand":
        if self.enabled and not self.confirm_background_actions:
            raise ValueError("Enabling background actions requires explicit scoped confirmation")
        if self.repeat and self.operation.kind not in {"telemetry", "retention"}:
            raise ValueError("Paid/source-bound commands are one-shot; enroll new frozen inputs")
        if (
            hasattr(self.operation, "command")
            and hasattr(self.operation.command, "project_id")
            and self.operation.command.project_id != self.project_id
        ):
            raise ValueError("Operation project must match schedule")
        return self


class Schedule(Contract):
    id: Digest
    version: int = 0
    command: ScheduleCommand
    project_id: str
    config_digest: Digest
    enabled: bool
    next_due: float
    cycle: int = 0
    reason: str = "user_disabled"


class BackgroundJob(Contract):
    id: Digest
    version: int = 0
    project_id: str
    schedule_id: Digest
    cycle: int
    operation: Operation
    status: Literal[
        "queued", "leased", "waiting", "paused", "succeeded", "failed", "cancelled", "attention"
    ] = "queued"
    reason: str = "queued"
    created_at: float
    next_due: float
    attempts: int = 0
    failures: int = 0
    lease_token: str | None = None
    lease_until: float = 0
    external_id: str | None = None
    dispatched: bool = False
    reserved_cost_microusd: int = 0
    actual_cost_microusd: int | None = 0
    sample_keys: tuple[str, ...] = ()
    result_digest: str | None = None


class OperationsControl(Contract):
    request_id: Id
    expected_version: int = Field(ge=0)
    action: Literal["pause", "resume", "cancel"]


class OperationsStatus(Contract):
    observer_only: bool = False
    owner_paused: bool = False
    enabled: bool
    config_digest: Digest
    coordinator: Literal["single_process_fenced_leases"] = "single_process_fenced_leases"
    publication_authority: Literal[False] = False
    last_error: str = ""


class TelemetrySample(Contract):
    id: Digest
    project_id: str
    created_at: float
    source_counts: dict[str, int]
    runs: int
    foreground_active: int
    passed: int
    failed: int
    operational_pass_rate: float | None
    known_cost_microusd: int
    unknown_charges: int
    review_backlog: int
    withdrawn_datasets: int
    training_states: dict[str, int]
    queue_states: dict[str, int]
    drift_advisory: bool = False
    causal_benefit_verified: Literal[False] = False


class OperationsAlert(Contract):
    id: Digest
    version: int = 0
    project_id: str
    code: str
    active: bool
    changed_at: float
    sample_id: str | None = None
    delivery: Literal["local_control_panel_only"] = "local_control_panel_only"


class BackupCommand(Contract):
    request_id: Id


class BackupManifest(Contract):
    id: Digest
    sha256: Digest
    bytes: int
    config_digest: Digest
    records: int
    created_at: float
    scope: Literal["owned_operations_state_only"] = "owned_operations_state_only"


class RestoreCommand(Contract):
    backup_id: Digest
    expected_sha256: Digest
    confirm_empty_target: bool = False


class OwnerPause(Contract):
    paused: bool


class TelemetryBaseline(Contract):
    id: Digest
    version: int = 0
    project_id: str
    operational_pass_rate: float = Field(ge=0, le=1)
    report_count: int = Field(ge=20)
