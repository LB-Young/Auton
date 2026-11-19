"""Metadata-only local telemetry; alerts are emitted only on state transitions."""

from collections import Counter

from auton.constitution.config import Principal
from auton.kernel.documents import VersionedDocumentStore, key
from auton.operations.contracts import (
    OperationsAlert,
    OperationsConfig,
    TelemetryBaseline,
    TelemetrySample,
)
from auton.operations.dependencies import OperationsDependencies
from auton.operations.queue import JobQueue


class Telemetry:
    def __init__(
        self,
        config: OperationsConfig,
        deps: OperationsDependencies,
        store: VersionedDocumentStore,
        queue: JobQueue,
    ) -> None:
        self.config, self.deps, self.store, self.queue = config, deps, store, queue

    def start(self) -> None:
        self.store.database().execute(
            "CREATE TABLE IF NOT EXISTS ops_samples(owner TEXT, project TEXT,id "
            "TEXT,created REAL,payload TEXT,PRIMARY KEY(owner,id))"
        )

    async def samples(self, principal: Principal, project: str) -> tuple[TelemetrySample, ...]:
        return tuple(
            TelemetrySample.model_validate_json(row[0])
            for row in self.store.database().execute(
                "SELECT payload FROM ops_samples WHERE owner=? AND project=? ORDER BY "
                "created DESC,id DESC LIMIT ?",
                (principal.owner, project, self.config.max_samples),
            )
        )

    async def alerts(self, principal: Principal, project: str) -> tuple[OperationsAlert, ...]:
        return tuple(
            OperationsAlert.model_validate(v)
            for v in await self.store.list("alert", principal.owner)
            if v["project_id"] == project
        )

    async def alert(
        self,
        principal: Principal,
        project: str,
        code: str,
        active: bool,
        sample_id: str | None = None,
    ) -> None:
        identity = key(principal.owner, "alert:" + project + ":" + code)
        value = await self.store.get("alert", principal.owner, identity)
        old = OperationsAlert.model_validate(value) if value else None
        if (old is None and not active) or (old and old.active == active):
            return
        result = OperationsAlert(
            id=identity,
            version=old.version + 1 if old else 0,
            project_id=project,
            code=code,
            active=active,
            changed_at=self.deps.runtime.now().timestamp(),
            sample_id=sample_id,
        )
        await self.store.put(
            "alert",
            principal.owner,
            identity,
            result.model_dump(mode="json"),
            old.version if old else None,
        )

    async def collect(self, principal: Principal, project: str, identity: str) -> TelemetrySample:
        existing = (
            self.store.database()
            .execute(
                "SELECT payload FROM ops_samples WHERE owner=? AND id=?",
                (principal.owner, identity),
            )
            .fetchone()
        )
        if existing:
            return TelemetrySample.model_validate_json(existing[0])
        runs = await self.deps.agent.list(principal, project)
        reports = await self.deps.assess.reports(principal, project)
        reviews = await self.deps.review.list(principal, project)
        datasets = await self.deps.datasets.list(principal, project)
        training = (
            *await self.deps.executor_training.jobs(principal, project),
            *await self.deps.decision_training.jobs(principal, project),
        )
        jobs = await self.queue.jobs(principal.owner, project)
        stages = {
            stage.request_id: stage
            for review in reviews
            for stage in (review.stage_a, review.stage_b)
            if stage is not None
        }
        judges = {judge.request_id: judge for report in reports for judge in report.judges}
        unknown = sum(s.dispatch == "unknown" or s.cost_microusd is None for s in stages.values())
        unknown += sum(
            j.dispatch_outcome == "unknown" or j.cost_microusd is None for j in judges.values()
        )
        unknown += sum(receipt.outcome == "unknown" for run in runs for receipt in run.receipts)
        unknown += sum(
            bool(
                run.model_request_id
                and run.model_request_id not in run.undispatched_model_request_ids
                and run.model_request_id not in {r.request_id for r in run.model_results}
                and run.status in {"blocked", "failed", "cancelled"}
            )
            for run in runs
        )
        known = (
            sum(run.cost_microusd for run in runs)
            + sum(s.cost_microusd or 0 for s in stages.values())
            + sum(j.cost_microusd or 0 for j in judges.values())
        )
        reviewed = {
            (r.command.run_id, r.command.judgment_id, r.command.question_id)
            for r in reviews
            if r.status == "complete"
        }
        decisions = {
            (r.id, j.request_id, a.question_id)
            for r in runs
            for j in r.judgments
            for a in j.answers
            if a.status == "answered"
        }
        current_reports = [
            r
            for r in reports
            if r.source == "runtime" and r.current_evidence_valid and r.outcome in {"pass", "fail"}
        ]
        passed = sum(r.outcome == "pass" for r in current_reports)
        rate = passed / len(current_reports) if current_reports else None
        baseline_id = key(principal.owner, "baseline:" + project)
        baseline_value = await self.store.get("baseline", principal.owner, baseline_id)
        if baseline_value is None and rate is not None and len(current_reports) >= 20:
            baseline = TelemetryBaseline(
                id=baseline_id,
                project_id=project,
                operational_pass_rate=rate,
                report_count=len(current_reports),
            )
            await self.store.put(
                "baseline", principal.owner, baseline_id, baseline.model_dump(mode="json"), None
            )
            baseline_value = baseline.model_dump(mode="json")
        drift = bool(
            baseline_value
            and rate is not None
            and len(current_reports) >= 20
            and float(baseline_value["operational_pass_rate"]) - rate >= self.config.drift_delta
        )
        result = TelemetrySample(
            id=identity,
            project_id=project,
            created_at=self.deps.runtime.now().timestamp(),
            source_counts=dict(Counter(r.source for r in runs)),
            runs=len(runs),
            foreground_active=sum(
                r.status in {"queued", "running", "waiting_approval"} for r in runs
            ),
            passed=passed,
            failed=len(current_reports) - passed,
            operational_pass_rate=rate,
            known_cost_microusd=known,
            unknown_charges=unknown,
            review_backlog=len(decisions - reviewed),
            withdrawn_datasets=sum(not d.current_evidence_valid for d in datasets),
            training_states=dict(Counter(j.status for j in training)),
            queue_states=dict(Counter(j.status for j in jobs)),
            drift_advisory=drift,
        )
        with self.store.database():
            self.store.database().execute(
                "INSERT INTO ops_samples VALUES(?,?,?,?,?)",
                (principal.owner, project, result.id, result.created_at, result.model_dump_json()),
            )
            # Bound even if the separate retention schedule has not yet run.
            self.store.database().execute(
                "DELETE FROM ops_samples WHERE owner=? AND project=? AND id NOT IN "
                "(SELECT id FROM ops_samples WHERE owner=? AND project=? "
                "ORDER BY created DESC,id DESC LIMIT ?)",
                (principal.owner, project, principal.owner, project, self.config.max_samples),
            )
        for code, active in {
            "unknown_usage_or_effect": unknown > 0,
            "review_backlog": result.review_backlog >= self.config.backlog_alert,
            "operational_drift_advisory": drift,
            "dataset_rights_changed": result.withdrawn_datasets > 0,
            "worker_attention": any(j.status == "attention" for j in jobs),
        }.items():
            await self.alert(principal, project, code, active, result.id)
        return result


class RetentionPolicy:
    def __init__(self, config: OperationsConfig, store: VersionedDocumentStore) -> None:
        self.config, self.store = config, store

    def apply(self, principal: Principal, project: str, now: float) -> int:
        db = self.store.database()
        with db:
            db.execute(
                "DELETE FROM ops_samples WHERE owner=? AND project=? AND created<?",
                (principal.owner, project, now - self.config.sample_retention_days * 86400),
            )
        return db.changes()


class TelemetryFactory:
    def create(
        self,
        config: OperationsConfig,
        deps: OperationsDependencies,
        store: VersionedDocumentStore,
        queue: JobQueue,
    ) -> Telemetry:
        return Telemetry(config, deps, store, queue)


class RetentionPolicyFactory:
    def create(self, config: OperationsConfig, store: VersionedDocumentStore) -> RetentionPolicy:
        return RetentionPolicy(config, store)
