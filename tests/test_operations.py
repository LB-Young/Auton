"""Explicit control-protocol fixtures; no training/model/production-quality claims."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auton.constitution.config import Principal
from auton.kernel.config import KernelConfig
from auton.kernel.documents import key
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.operations.contracts import (
    BackgroundJob,
    BackupCommand,
    MaintenanceOperation,
    OperationsConfig,
    OperationsControl,
    RestoreCommand,
    ScheduleCommand,
)
from auton.operations.dependencies import OperationsDependencies
from auton.operations.factory import SchedulerFactory
from auton.operations.service import Scheduler
from auton.training.contracts import TrainingJob

USER = Principal(owner="ops-owner", role="user")


class FixturePorts:
    def __init__(self) -> None:
        self.active = 0
        self.dataset_effects: dict[str, Any] = {}
        self.dataset_calls: list[str] = []
        self.lose_ack = False
        self.train_effects: dict[str, TrainingJob] = {}
        self.train_starts = 0
        self.train_stops = 0
        self.train_resumes = 0
        self.review_starts = 0
        self.unknown = False
        self.review_failed = False
        self.run_values: list[Any] = []
        self.report_values: list[Any] = []
        self.plan = SimpleNamespace(
            id="a" * 64,
            status="ready",
            current_evidence_valid=True,
            manifest_digest="b" * 64,
            command=SimpleNamespace(engineering_probe=False, train_artifact_id="c" * 64),
        )

    async def resolve(self, principal: Principal, project: str) -> Any:
        if principal.owner != USER.owner or project != "project":
            raise ApplicationError(404, "fixture_project_missing", "No owned fixture project")
        return SimpleNamespace(id="snapshot")

    def foreground_active(self) -> int:
        return self.active

    async def list(self, principal: Principal, project: str) -> Any:
        return self.run_values

    async def reports(self, principal: Principal, project: str) -> Any:
        return self.report_values

    async def jobs(self, principal: Principal, project: str) -> Any:
        return tuple(self.train_effects.values())

    async def plans(self, principal: Principal, project: str) -> Any:
        return (self.plan,)

    async def read_artifact(self, principal: Principal, identity: str) -> Any:
        return SimpleNamespace(snapshot_id="d" * 64), b"synthetic unit fixture"

    async def get(self, principal: Principal, identity: str) -> Any:
        if identity in self.train_effects:
            return self.train_effects[identity]
        return SimpleNamespace(
            command=SimpleNamespace(project_id="project"),
            current_evidence_valid=True,
            training_ready=True,
            examples=[
                SimpleNamespace(
                    kind="executor",
                    split="train",
                    normalized_input=f"input-{i}",
                    normalized_target="target",
                )
                for i in range(20)
            ],
        )

    async def build(self, principal: Principal, command: Any) -> Any:
        self.dataset_calls.append(command.request_id)
        value = self.dataset_effects.setdefault(
            command.request_id,
            SimpleNamespace(
                id=key(principal.owner, command.request_id),
                status="ready",
                current_evidence_valid=True,
                content_digest="e" * 64,
            ),
        )
        if self.lose_ack:
            self.lose_ack = False
            raise ApplicationError(
                503, "fixture_ack_lost", "Committed fixture lost its acknowledgement"
            )
        return value

    async def create(self, principal: Principal, command: Any) -> TrainingJob:
        identity = key(principal.owner, command.request_id)
        if identity not in self.train_effects:
            self.train_starts += 1
            self.train_effects[identity] = TrainingJob(
                id=identity,
                command=command,
                project_id="project",
                plan_digest=command.expected_plan_digest,
                status="running",
                created_at=1,
            )
        return self.train_effects[identity]

    async def control(self, principal: Principal, identity: str, command: Any) -> TrainingJob:
        old = self.train_effects[identity]
        assert old.version == command.expected_version
        self.train_stops += command.action == "cancel"
        self.train_resumes += command.action == "resume"
        checkpoint = {
            "step": 1,
            "files": {"adapter.safetensors": "f" * 64, "state.safetensors": "f" * 64},
            "manifest_digest": old.plan_digest,
        }
        new = old.model_copy(
            update={
                "version": old.version + 1,
                "status": "cancelled" if command.action == "cancel" else "running",
                "checkpoint": __import__(
                    "auton.training.contracts", fromlist=["TrainingCheckpoint"]
                ).TrainingCheckpoint.model_validate(checkpoint),
            }
        )
        # Pydantic validation mirrors the public training contract.
        new = TrainingJob.model_validate(new.model_dump())
        self.train_effects[identity] = new
        return new


class Harness:
    def __init__(self, root: Path, events: Any, config: OperationsConfig | None = None) -> None:
        self.now = datetime(2026, 11, 19, 12, tzinfo=UTC)
        self.ports = FixturePorts()
        self.events = events
        self.deps = OperationsDependencies(
            cast(Any, self.ports),
            cast(Any, self.ports),
            cast(Any, self.ports),
            cast(Any, self.ports),
            cast(Any, self.ports),
            cast(Any, self.ports),
            cast(Any, self.ports),
            events,
            RuntimeDependencies(
                now=lambda: self.now, new_id=lambda: __import__("uuid").uuid4().hex
            ),
            40000,
            True,
        )
        result = SchedulerFactory().create(
            config
            or OperationsConfig(directory=root, enabled=True, poll_seconds=1, backoff_seconds=1),
            self.deps,
        )
        assert isinstance(result, Scheduler)
        self.service = result

    async def start(self) -> None:
        await self.service.start()
        if self.service.task:
            self.service.task.cancel()
            await asyncio.gather(self.service.task, return_exceptions=True)
            self.service.task = None

    def advance(self, seconds: int = 2) -> None:
        self.now += timedelta(seconds=seconds)

    def command(
        self, identity: str = "schedule", kind: str = "telemetry", **changes: Any
    ) -> ScheduleCommand:
        operation: dict[str, Any] = {"kind": kind}
        if kind == "dataset":
            operation["command"] = {
                "request_id": "original",
                "project_id": "project",
                "kind": "executor",
                "grant_id": "1" * 64,
                "subjects": [
                    {
                        "run_id": "2" * 64,
                        "expected_version": 0,
                        "family": "family",
                        "origin_group": "origin",
                    }
                ],
            }
        if kind in {"executor_training", "decision_training"}:
            operation["command"] = {
                "request_id": "original",
                "plan_id": "a" * 64,
                "expected_plan_digest": "b" * 64,
            }
            operation["allow_checkpoint_resume"] = True
        return ScheduleCommand.model_validate(
            {
                "request_id": identity,
                "project_id": "project",
                "operation": operation,
                "enabled": True,
                "confirm_background_actions": True,
                "expires_at": self.now.timestamp() + 86400,
                **changes,
            }
        )


@pytest.fixture
async def harness(tmp_path: Path) -> Any:
    events = EventLogFactory().create(KernelConfig(backend="memory"))
    await events.start()
    h = Harness(tmp_path / "ops", events)
    await h.start()
    yield h
    await h.service.close()
    await events.close()


def test_background_grants_default_false_and_repeat_cannot_create_paid_loops() -> None:
    value = {
        "request_id": "disabled",
        "project_id": "project",
        "operation": {"kind": "telemetry"},
        "expires_at": 1,
    }
    assert not ScheduleCommand.model_validate(value).enabled
    with pytest.raises(ValidationError):
        ScheduleCommand.model_validate({**value, "enabled": True})
    with pytest.raises(ValidationError):
        ScheduleCommand.model_validate(
            {
                **value,
                "repeat": True,
                "operation": {
                    "kind": "executor_training",
                    "command": {
                        "request_id": "train",
                        "plan_id": "a" * 64,
                        "expected_plan_digest": "b" * 64,
                    },
                },
            }
        )


async def test_schedule_idempotent_job_once_restart_and_source_scope(harness: Harness) -> None:
    s = harness.service
    c = harness.command()
    schedule = await s.schedule(USER, c)
    assert await s.schedule(USER, c) == schedule
    with pytest.raises(ApplicationError):
        await s.schedule(USER, c.model_copy(update={"repeat": True}))
    await s.tick(USER)
    jobs = await s.jobs(USER, "project")
    assert len(jobs) == 1 and jobs[0].status == "succeeded"
    harness.advance()
    await s.tick(USER)
    await s.close()
    await harness.start()
    await s.tick(USER)
    assert len(await s.jobs(USER, "project")) == 1
    with pytest.raises(ApplicationError):
        await s.jobs(Principal(owner="other", role="user"), "project")
    with pytest.raises(ApplicationError):
        await s.schedule(USER.model_copy(update={"role": "runtime"}), c)


async def test_resource_window_foreground_priority_and_one_logical_dataset_effect(
    harness: Harness,
) -> None:
    h = harness
    h.ports.active = 1
    h.ports.lose_ack = True
    await h.service.schedule(USER, h.command("data", "dataset"))
    await h.service.tick(USER)
    assert (
        not h.ports.dataset_calls
        and (await h.service.jobs(USER, "project"))[0].reason == "foreground_priority"
    )
    h.ports.active = 0
    h.advance()
    await h.service.tick(USER)
    job = (await h.service.jobs(USER, "project"))[0]
    assert job.status == "queued" and job.reason == "fixture_ack_lost" and job.dispatched
    h.advance()
    await h.service.tick(USER)
    assert (
        len(h.ports.dataset_effects) == 1
        and len(h.ports.dataset_calls) == 2
        and len(set(h.ports.dataset_calls)) == 1
    )
    assert (await h.service.jobs(USER, "project"))[0].status == "succeeded"


async def test_utc_window_and_lease_expiry_fences_old_worker(harness: Harness) -> None:
    h = harness
    await h.service.schedule(USER, h.command(window={"start_hour_utc": 13, "end_hour_utc": 14}))
    await h.service.tick(USER)
    job = (await h.service.jobs(USER, "project"))[0]
    assert job.status == "queued" and "window" in job.reason
    a, b = await asyncio.gather(
        h.service.queue.claim(USER, job.id), h.service.queue.claim(USER, job.id)
    )
    assert (a is None) != (b is None)
    first = a or b
    assert first
    h.advance(h.service.config.lease_seconds + 1)
    second = await h.service.queue.claim(USER, job.id)
    assert second and first.lease_token != second.lease_token
    with pytest.raises(ApplicationError, match="Expired/replaced"):
        await h.service.queue.save(USER.owner, first, first.lease_token, status="succeeded")
    await h.service.queue.save(
        USER.owner, second, second.lease_token, status="queued", lease_token=None, lease_until=0
    )
    h.advance(3600)
    await h.service.tick(USER)
    assert (await h.service.jobs(USER, "project"))[0].status == "succeeded"


async def test_training_new_sample_gate_foreground_preemption_and_explicit_checkpoint_resume(
    harness: Harness,
) -> None:
    h = harness
    await h.service.schedule(USER, h.command("train-first", "executor_training"))
    await h.service.tick(USER)
    job = (await h.service.jobs(USER, "project"))[0]
    assert job.status == "waiting" and h.ports.train_starts == 1
    h.ports.active = 1
    h.advance()
    await h.service.tick(USER)
    assert (await h.service.jobs(USER, "project"))[
        0
    ].status == "paused" and h.ports.train_stops == 1
    h.ports.active = 0
    h.advance()
    await h.service.tick(USER)
    assert h.ports.train_starts == 1 and h.ports.train_resumes == 1
    trained = h.ports.train_effects[job.external_id or ""]
    h.ports.train_effects[trained.id] = trained.model_copy(update={"status": "succeeded"})
    h.advance()
    await h.service.tick(USER)
    assert (await h.service.queue.get(USER.owner, job.id)).status == "succeeded"
    await h.service.schedule(USER, h.command("renamed-same-data", "executor_training"))
    await h.service.tick(USER)
    assert h.ports.train_starts == 1
    assert any(
        j.reason == "background_fresh_data_insufficient"
        for j in await h.service.jobs(USER, "project")
    )


async def test_unknown_costs_and_foreground_do_not_starve_monitoring_or_inflate_alerts(
    harness: Harness,
) -> None:
    h = harness
    h.ports.run_values = [
        SimpleNamespace(
            id="run",
            source="test",
            status="blocked",
            cost_microusd=10,
            model_request_id="unknown",
            undispatched_model_request_ids=(),
            model_results=(),
            receipts=(),
            judgments=(),
        )
    ]

    # Separate port surfaces return the correct public type, not agent runs as reviews/data.
    async def empty(*args: Any) -> tuple[Any, ...]:
        return ()

    h.service.deps = replace(
        h.service.deps,
        review=cast(Any, SimpleNamespace(list=empty)),
        datasets=cast(Any, SimpleNamespace(list=empty)),
    )
    h.service.telemetry.deps = h.service.deps
    h.ports.active = 1
    first = await h.service.telemetry.collect(USER, "project", "3" * 64)
    alerts = await h.service.alerts(USER, "project")
    assert first.unknown_charges == 1 and len(alerts) == 1 and alerts[0].version == 0
    h.advance()
    await h.service.telemetry.collect(USER, "project", "4" * 64)
    assert (await h.service.alerts(USER, "project"))[0].version == 0
    h.ports.run_values = []
    h.advance()
    await h.service.telemetry.collect(USER, "project", "5" * 64)
    resolved = (await h.service.alerts(USER, "project"))[0]
    assert not resolved.active and resolved.version == 1


async def test_backup_corruption_restore_empty_paused_and_exact_job_identity(
    harness: Harness, tmp_path: Path
) -> None:
    h = harness
    await h.service.schedule(USER, h.command("backup", "dataset"))
    await h.service.tick(USER)
    before = (await h.service.jobs(USER, "project"))[0]
    manifest = await h.service.backup(USER, BackupCommand(request_id="snapshot"))
    assert await h.service.backup(USER, BackupCommand(request_id="snapshot")) == manifest
    with pytest.raises(ApplicationError, match="overwrites"):
        await h.service.restore(
            USER,
            RestoreCommand(
                backup_id=manifest.id, expected_sha256=manifest.sha256, confirm_empty_target=True
            ),
        )
    restored = Harness(tmp_path / "restored", h.events)
    restored.ports = h.ports
    restored.service.deps = replace(restored.service.deps, assets=cast(Any, h.ports))
    restored.service.backups.deps = restored.service.deps
    await restored.start()
    try:
        source = h.service.backups.path(USER, manifest.id)
        destination = restored.service.backups.path(USER, manifest.id)
        raw = source.read_bytes()
        destination.write_bytes(raw + b"corrupt")
        command = RestoreCommand(
            backup_id=manifest.id, expected_sha256=manifest.sha256, confirm_empty_target=True
        )
        with pytest.raises(ApplicationError):
            await restored.service.restore(USER, command)
        assert not await restored.service.schedules(USER)
        destination.write_bytes(raw)
        await restored.service.restore(USER, command)
        assert await restored.service.paused(USER)
        await restored.service.tick(USER)
        after = (await restored.service.jobs(USER, "project"))[0]
        assert (
            after.id == before.id
            and after.status == "succeeded"
            and len(h.ports.dataset_effects) == 1
        )
    finally:
        await restored.service.close()


async def test_retention_physically_removes_only_owned_expired_monitor_samples(
    harness: Harness,
) -> None:
    h = harness
    await h.service.telemetry.collect(USER, "project", "6" * 64)
    h.advance(31 * 86400)
    assert h.service.retention.apply(USER, "other", h.now.timestamp()) == 0
    assert h.service.retention.apply(USER, "project", h.now.timestamp()) == 1
    assert not await h.service.samples(USER, "project")


async def test_job_control_replays_idempotently_and_disabled_host_does_not_dispatch(
    harness: Harness,
) -> None:
    h = harness
    h.ports.active = 1
    await h.service.schedule(USER, h.command("pause", "dataset"))
    await h.service.tick(USER)
    job = (await h.service.jobs(USER, "project"))[0]
    command = OperationsControl(
        request_id="pause-job", expected_version=job.version, action="pause"
    )
    paused = await h.service.control_job(USER, job.id, command)
    assert await h.service.control_job(USER, job.id, command) == paused
    await h.service.control_owner(USER, True)
    h.ports.active = 0
    h.advance()
    await h.service.tick(USER)
    assert not h.ports.dataset_calls


def test_api_disabled_defaults_empty_state_and_no_publication_port(client: TestClient) -> None:
    assert client.get("/api/v1/operations/status").json()["enabled"] is False
    assert client.get("/api/v1/operations/status").json()["publication_authority"] is False
    assert client.post("/api/v1/operations/tick", json={}).json() == []
    assert client.post("/api/v1/operations/control", json={"paused": True}).json() is True


async def test_bounded_backoff_never_changes_public_request_identity(harness: Harness) -> None:
    h = harness
    calls = []

    async def fail(principal: Principal, command: Any) -> Any:
        calls.append(command.request_id)
        raise ApplicationError(503, "fixture_temporary_unavailable", "Fixture unavailable")

    h.ports.build = fail  # type: ignore[method-assign]
    await h.service.schedule(USER, h.command("retry", "dataset"))
    for _ in range(5):
        await h.service.tick(USER)
        h.advance(10)
    job = (await h.service.jobs(USER, "project"))[0]
    assert (
        len(calls) == 3 and len(set(calls)) == 1 and job.status == "attention" and job.failures == 3
    )


async def test_dependencies_do_not_bypass_foreground_and_expired_grants_stop(
    harness: Harness,
) -> None:
    h = harness
    h.ports.active = 1
    await h.service.schedule(USER, h.command("first", "dataset"))
    await h.service.tick(USER)
    upstream = (await h.service.jobs(USER, "project"))[0]
    await h.service.schedule(USER, h.command("second", depends_on=[upstream.id]))
    await h.service.tick(USER)
    assert any(
        j.reason == "waiting_for_approved_dependencies"
        for j in await h.service.jobs(USER, "project")
    )
    h.ports.active = 0
    h.advance()
    await h.service.tick(USER)
    h.advance()
    await h.service.tick(USER)
    assert all(j.status == "succeeded" for j in await h.service.jobs(USER, "project"))
    h.ports.active = 1
    await h.service.schedule(
        USER, h.command("expiring", "dataset", expires_at=h.now.timestamp() + 1)
    )
    await h.service.tick(USER)
    h.advance(2)
    await h.service.tick(USER)
    assert any(
        j.reason == "background_grant_expired" and j.status == "attention"
        for j in await h.service.jobs(USER, "project")
    )


async def test_unknown_review_charge_reserves_full_budget(harness: Harness) -> None:
    h = harness
    h.service.config = h.service.config.model_copy(update={"owner_budget_microusd": 40000})

    class Review:
        starts = 0

        async def review(self, principal: Principal, command: Any) -> Any:
            self.starts += 1
            return SimpleNamespace(
                id="9" * 64,
                status="blocked",
                stage_a=SimpleNamespace(dispatch="unknown", cost_microusd=None),
                stage_b=None,
                model_dump=lambda **kwargs: {"fixture": "unknown"},
            )

    review = Review()
    h.service.pipelines.deps = replace(h.service.deps, review=cast(Any, review))
    operation = {
        "kind": "review",
        "command": {
            "request_id": "original",
            "project_id": "project",
            "run_id": "r",
            "expected_run_version": 0,
            "judgment_id": "j",
            "question_id": "q",
        },
    }
    await h.service.schedule(USER, h.command("no-budget", operation=operation))
    await h.service.tick(USER)
    assert review.starts == 0
    await h.service.schedule(
        USER, h.command("unknown-review", operation=operation, budget_microusd=40000)
    )
    await h.service.tick(USER)
    unknown = next(j for j in await h.service.jobs(USER, "project") if j.external_id)
    assert (
        review.starts == 1
        and unknown.status == "attention"
        and unknown.actual_cost_microusd is None
        and unknown.reserved_cost_microusd == 40000
    )
    await h.service.schedule(
        USER, h.command("exhausted-review", operation=operation, budget_microusd=40000)
    )
    await h.service.tick(USER)
    assert review.starts == 1


async def test_drift_is_advisory_persistent_and_not_a_training_grant(harness: Harness) -> None:
    h = harness
    h.ports.report_values = [
        SimpleNamespace(source="runtime", current_evidence_valid=True, outcome="pass", judges=())
        for _ in range(20)
    ]
    await h.service.telemetry.collect(USER, "project", "a" * 64)
    for report in h.ports.report_values[:10]:
        report.outcome = "fail"
    h.advance()
    degraded = await h.service.telemetry.collect(USER, "project", "b" * 64)
    h.advance()
    repeated = await h.service.telemetry.collect(USER, "project", "c" * 64)
    assert (
        degraded.drift_advisory and repeated.drift_advisory and not repeated.causal_benefit_verified
    )
    assert h.ports.train_starts == 0
    alert = next(
        a for a in await h.service.alerts(USER, "project") if a.code == "operational_drift_advisory"
    )
    assert alert.active and alert.version == 0


async def test_stale_backup_advances_past_surviving_audit_versions(
    harness: Harness, tmp_path: Path
) -> None:
    h = harness
    schedule = await h.service.schedule(USER, h.command("stale"))
    backup = await h.service.backup(USER, BackupCommand(request_id="stale-backup"))
    changed = await h.service.control_schedule(
        USER,
        schedule.id,
        OperationsControl(
            request_id="after-backup", expected_version=schedule.version, action="pause"
        ),
    )
    await h.service.control_owner(USER, True)
    restored = Harness(tmp_path / "rebased", h.events)
    await restored.start()
    try:
        restored.service.backups.path(USER, backup.id).write_bytes(
            h.service.backups.path(USER, backup.id).read_bytes()
        )
        await restored.service.restore(
            USER,
            RestoreCommand(
                backup_id=backup.id, expected_sha256=backup.sha256, confirm_empty_target=True
            ),
        )
        restored_schedule = (await restored.service.schedules(USER))[0]
        assert restored_schedule.version > changed.version
        await restored.service.control_schedule(
            USER,
            schedule.id,
            OperationsControl(
                request_id="new-control", expected_version=restored_schedule.version, action="pause"
            ),
        )
        assert await restored.service.paused(USER)
        await restored.service.control_owner(USER, False)
        assert not await restored.service.paused(USER)
    finally:
        await restored.service.close()


async def test_autonomous_loop_processes_only_enabled_grants(harness: Harness) -> None:
    h = harness
    await h.service.schedule(USER, h.command("autonomous"))
    h.service.task = asyncio.create_task(h.service.loop())
    for _ in range(100):
        jobs = await h.service.jobs(USER, "project")
        if jobs and jobs[0].status == "succeeded":
            break
        await asyncio.sleep(0.01)
    assert jobs and jobs[0].status == "succeeded"
    assert len(await h.service.jobs(USER, "project")) == 1


async def test_observer_mode_is_a_distinct_allowlisted_namespace(
    harness: Harness, tmp_path: Path
) -> None:
    observer = Harness(
        tmp_path / "observer",
        harness.events,
        OperationsConfig(directory=tmp_path / "observer", enabled=True, observer_only=True),
    )
    await observer.start()
    try:
        assert observer.service.store.namespace == "operations_observe"
        with pytest.raises(ApplicationError, match="Observer mode"):
            await observer.service.schedule(USER, observer.command("forbidden", "dataset"))
        await observer.service.schedule(USER, observer.command("allowed"))
        await observer.service.tick(USER)
        assert (await observer.service.jobs(USER, "project"))[0].status == "succeeded"
        assert observer.ports.train_starts == 0
    finally:
        await observer.service.close()


async def test_queue_backpressure_and_long_time_retention_are_bounded(harness: Harness) -> None:
    h = harness
    h.service.queue.config = h.service.config.model_copy(update={"max_queued_jobs": 10})
    for i in range(10):
        await h.service.queue.add(
            USER.owner,
            BackgroundJob(
                id=key(USER.owner, str(i)),
                project_id="project",
                schedule_id="f" * 64,
                cycle=0,
                operation=MaintenanceOperation(kind="telemetry"),
                created_at=h.now.timestamp(),
                next_due=h.now.timestamp(),
            ),
        )
    with pytest.raises(ApplicationError, match="queue is full"):
        await h.service.queue.add(
            USER.owner,
            BackgroundJob(
                id="e" * 64,
                project_id="project",
                schedule_id="f" * 64,
                cycle=1,
                operation=MaintenanceOperation(kind="telemetry"),
                created_at=h.now.timestamp(),
                next_due=h.now.timestamp(),
            ),
        )
    for day in range(40):
        await h.service.telemetry.collect(USER, "project", key(USER.owner, "day-" + str(day)))
        h.service.retention.apply(USER, "project", h.now.timestamp())
        h.advance(86400)
    assert len(await h.service.samples(USER, "project")) <= 31
    assert len(await h.service.jobs(USER, "project")) == 10


async def test_pause_stops_only_the_owned_background_training_worker(harness: Harness) -> None:
    h = harness
    await h.service.schedule(USER, h.command("training-pause", "executor_training"))
    await h.service.tick(USER)
    job = (await h.service.jobs(USER, "project"))[0]
    command = OperationsControl(
        request_id="pause-running", expected_version=job.version, action="pause"
    )
    paused = await h.service.control_job(USER, job.id, command)
    assert paused.status == "paused" and h.ports.train_stops == 1
    assert h.ports.train_effects[job.external_id or ""].status == "cancelled"
    assert await h.service.control_job(USER, job.id, command) == paused and h.ports.train_stops == 1
