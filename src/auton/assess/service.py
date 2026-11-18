import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, TypeVar, cast

from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.agent.ports import AgentRuntimePort
from auton.assess.contracts import (
    Aggregate,
    AssessConfig,
    AssessmentStatus,
    BatchEvaluation,
    BatchResult,
    BlindWindow,
    BlindWindowCommand,
    CalibrationCommand,
    CalibrationReport,
    CaseBank,
    Comparison,
    EvalCase,
    EvalJob,
    EvalReport,
    EvaluateCommand,
    GroupCalibration,
    ImportCases,
    JudgeObservation,
    Metrics,
    SeedCommand,
    Signal,
    Verdict,
    WindowView,
)
from auton.assess.environment import conditions
from auton.assess.grouping import scope_groups
from auton.assess.human import human_signals
from auton.assess.ports import CheckerPort, EvalStorePort, JudgePort
from auton.assess.seeds import SeedCaseFactory
from auton.assess.statistics import aggregate, kappa, wilson
from auton.assess.store import digest, key, normalized
from auton.constitution.config import Principal
from auton.context.ports import ContextEnginePort
from auton.kernel.events import StoredEvent
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.ports import ModelGatewayPort
from auton.tools.ports import ToolHostPort

T = TypeVar("T")
ENVIRONMENT_ERRORS = frozenset(
    {
        "provider_unavailable",
        "provider_unreachable",
        "provider_timeout",
        "stream_interrupted",
        "request_interrupted",
        "request_result_unknown",
        "model_not_ready",
        "model_busy",
        "incomplete_stream",
        "provider_rejected",
        "provider_denied",
        "data_egress_denied",
        "action_denied",
        "invalid_stream",
        "request_timeout",
        "credential_missing",
        "model_not_found",
        "rate_limited",
        "tokenizer_unavailable",
        "connection_failed",
        "transport_error",
        "context_limit",
    }
)


@dataclass(frozen=True)
class AssessDependencies:
    agent: AgentRuntimePort
    tools: ToolHostPort
    context: ContextEnginePort
    models: ModelGatewayPort
    events: EventLogPort
    runtime: RuntimeDependencies
    judge_journal_isolated: bool = False


def candidate_revision(run: AgentRun) -> str:
    identities = sorted(
        {(r.model_id, r.reported_model, r.system_fingerprint or "") for r in run.model_results}
    )
    return digest(
        {
            "executor": run.command.model_id,
            "declared_executor": {
                k: v
                for k, v in run.executor_spec.items()
                if k
                not in {
                    "health",
                    "price_revision",
                    "input_microusd_per_million",
                    "output_microusd_per_million",
                    "context_tokens",
                    "declared_context_tokens",
                    "max_output_tokens",
                    "capability_source",
                }
            },
            "runtime": run.runtime_revision,
            "observed_models": identities,
        }
    )


def judge_identity(observation: JudgeObservation, config: AssessConfig) -> str | None:
    if not observation.reported_model or not observation.fingerprint:
        return None
    return digest(
        {
            "model": observation.reported_model,
            "fingerprint": observation.fingerprint,
            "configured_model": config.judge_model,
            "rubric": config.rubric_revision,
            "configuration": config.digest,
        }
    )


class Assessment:
    def __init__(
        self,
        config: AssessConfig,
        deps: AssessDependencies,
        store: EvalStorePort,
        checker: CheckerPort,
        judge: JudgePort,
    ) -> None:
        self.config, self.deps, self.store, self.checker, self.judge = (
            config,
            deps,
            store,
            checker,
            judge,
        )
        self.ready = False
        self.accepting = False
        self.active: dict[str, asyncio.Task[object]] = {}
        self.bindings: dict[str, str] = {}

    async def start(self) -> None:
        await self.store.start()
        from auton.assess.contracts import PROTECTED_NORMALIZATION_REVISION
        from auton.assess.rubric import RUBRIC

        await self.store.put(
            "configuration",
            "system",
            self.config.digest,
            {
                "config": self.config.model_dump(mode="json", exclude={"directory"}),
                "rubric": RUBRIC,
                "normalization_revision": PROTECTED_NORMALIZATION_REVISION,
            },
        )
        self.ready = True
        self.accepting = True

    async def close(self) -> None:
        self.accepting = False
        await asyncio.gather(*list(self.active.values()), return_exceptions=True)
        self.ready = False
        await self.store.close()

    def user(self, principal: Principal) -> None:
        if not self.ready:
            raise ApplicationError(503, "assessment_not_ready", "Assessment service unavailable")
        if principal.role != "user":
            raise ApplicationError(
                403,
                "assessment_role_denied",
                "Protected assessment is a user control-plane operation",
            )

    async def execute(
        self,
        principal: Principal,
        identity: str,
        body: object,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        self.user(principal)
        if not self.accepting:
            raise ApplicationError(503, "assessment_stopping", "Assessment is draining active jobs")
        task_key = key(principal.owner, identity)
        hashed = digest(body)
        if task_key in self.active:
            if self.bindings[task_key] != hashed:
                raise ApplicationError(
                    409, "assessment_request_conflict", "Pending request has different input"
                )
            return cast(T, await asyncio.shield(self.active[task_key]))
        if len(self.active) >= self.config.max_active_jobs:
            raise ApplicationError(429, "assessment_job_limit", "Too many active assessment jobs")

        async def invoke() -> object:
            return await operation()

        task = asyncio.create_task(invoke())
        self.active[task_key], self.bindings[task_key] = task, hashed

        def completed(done: asyncio.Task[object]) -> None:
            self.active.pop(task_key, None)
            self.bindings.pop(task_key, None)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        return cast(T, await asyncio.shield(task))

    def status(self) -> AssessmentStatus:
        return AssessmentStatus(
            config_digest=self.config.digest,
            rubric_revision=self.config.rubric_revision,
            judge_model=self.config.judge_model,
            min_calibration_samples=self.config.min_calibration_samples,
            min_calibration_lower=self.config.min_calibration_lower,
            active_jobs=len(self.active),
            max_calibration_calls=self.config.max_calibration_calls,
            private_judge_journal=self.deps.judge_journal_isolated,
        )

    async def seed(self, principal: Principal, command: SeedCommand) -> CaseBank:
        return await self.import_cases(
            principal,
            ImportCases(
                request_id=command.request_id,
                expected_revision=command.expected_revision,
                cases=SeedCaseFactory().create(),
            ),
        )

    async def bank(self, principal: Principal) -> CaseBank:
        return await self.store.bank(principal)

    async def import_cases(self, principal: Principal, command: ImportCases) -> CaseBank:
        return await self.execute(
            principal,
            "import:" + command.request_id,
            command.model_dump(mode="json"),
            lambda: self.store.import_cases(principal, command),
        )

    async def train_cases(self, principal: Principal) -> tuple[EvalCase, ...]:
        if principal.role not in {"user", "training", "evolution"}:
            raise ApplicationError(
                403, "assessment_role_denied", "Training cases need a permitted consumer"
            )
        bank = await self.store.bank(principal)
        return tuple(
            [
                await self.store.read_case(principal, case.id, bank.revision, "training")
                for case in bank.cases
                if case.split == "train"
            ]
        )

    async def open_window(self, principal: Principal, command: BlindWindowCommand) -> BlindWindow:
        return await self.execute(
            principal,
            "window:" + command.request_id,
            command.model_dump(mode="json"),
            lambda: self.store.open_window(principal, command),
        )

    async def _subject(
        self, principal: Principal, command: EvaluateCommand
    ) -> tuple[AgentRun, StoredEvent]:
        run = await self.deps.agent.get(principal, command.run_id)
        if run.command.project_id != command.project_id:
            raise ApplicationError(
                404, "assessment_run_scope", "Run does not belong to this project"
            )
        if run.version != command.expected_version:
            raise ApplicationError(
                409,
                "assessment_checkpoint_changed",
                "Choose the current exact checkpoint before assessment",
            )
        source = await self.deps.events.lookup(
            checkpoint_event_id(principal.owner, run.id, run.version)
        )
        if source is None or AgentRun.model_validate(source.event.payload.get("run")) != run:
            raise ApplicationError(
                409,
                "assessment_checkpoint_unavailable",
                "Exact source checkpoint cannot be verified",
            )
        for identity in run.context_ids:
            await self.deps.context.snapshot(
                principal.model_copy(update={"role": "runtime"}), run.command.project_id, identity
            )
        return run, source

    async def evaluate(self, principal: Principal, command: EvaluateCommand) -> EvalJob:
        return await self.execute(
            principal,
            "run:" + command.request_id,
            command.model_dump(mode="json"),
            lambda: self._evaluate(principal, command),
        )

    async def _evaluate(
        self, principal: Principal, command: EvaluateCommand, reservation: str | None = None
    ) -> EvalJob:
        identity = key(principal.owner, "run:" + command.request_id)
        old_plan = await self.store.get("plan", principal.owner, identity)
        plan: dict[str, object] = {
            "command": command.model_dump(mode="json"),
            "configuration": self.config.digest,
        }
        if old_plan and old_plan != plan:
            raise ApplicationError(
                409,
                "assessment_request_conflict",
                "Assessment request has different input or protected configuration",
            )
        old = await self.store.get("report", principal.owner, identity)
        if old:
            return EvalJob(
                id=identity,
                command=command,
                status="complete",
                reason="immutable_report",
                report=await self.report(principal, identity),
            )
        run, source = await self._subject(principal, command)
        case = None
        split: Literal["operational", "train", "development", "test", "meta"] = "operational"
        if command.case_id:
            if not command.bank_revision:
                raise ApplicationError(
                    422, "assessment_bank_required", "Case assessment binds an immutable bank"
                )
            case = await self.store.protected_case(
                principal.owner, command.case_id, command.bank_revision
            )
            split = case.split
            if split == "meta":
                raise ApplicationError(
                    403,
                    "meta_calibration_only",
                    "Meta gold is only consumed by the calibration workflow",
                )
            if split == "test":
                window = await self._window(
                    principal.owner, command.window_id, command.bank_revision, "test"
                )
                if window.candidate_revision != candidate_revision(run):
                    raise ApplicationError(
                        409,
                        "assessment_candidate_changed",
                        "Observed candidate does not match the blind window",
                    )
                bank = await self.store.bank(principal)
                if reservation is None and bank.counts["test"] != 1:
                    raise ApplicationError(
                        409,
                        "assessment_batch_required",
                        "All test cases must be fixed in one protected batch",
                    )
                await self.store.consume_window(
                    principal.owner,
                    window.id,
                    command.bank_revision,
                    "test",
                    reservation or identity,
                )
        elif command.window_id or command.bank_revision:
            raise ApplicationError(
                422, "assessment_case_required", "A protected bank/window requires a case binding"
            )
        await self.store.put("plan", principal.owner, identity, plan)
        signature, environment_verified, environment_reasons, evidence_text = await conditions(
            principal, run, source, self.deps.events, self.deps.context
        )
        signals = list(await self.checker.check(principal, run, source, case))
        signals.extend(await human_signals(principal, run, source, self.deps.events))
        judges: list[JudgeObservation] = []
        evidence_text[source.event.event_id] = json.dumps(
            {
                "status": run.status,
                "goal_revision": run.goal_revision,
                "tool_protocol": [
                    {"name": s.name, "verdict": s.verdict, "reason": s.reason}
                    for s in signals
                    if s.source == "deterministic"
                ],
            }
        )
        for receipt in run.receipts:
            evidence_text[receipt.operation_id] = json.dumps(
                {
                    "tool": receipt.tool,
                    "outcome": receipt.outcome,
                    "artifact": receipt.artifact.model_dump(mode="json")
                    if receipt.artifact
                    else None,
                }
            )
        if case:
            evidence_text.update(
                {"case:" + case.id + ":" + ref: text for ref, text in case.evidence_text.items()}
            )
        if (
            command.semantic
            and run.final_text
            and run.status in {"succeeded", "failed", "cancelled", "blocked"}
        ):
            public = run.command.data_domain == "public" and (
                case is None or case.data_domain == "public"
            )
            actor_models = tuple(
                {run.command.model_id, *[result.reported_model for result in run.model_results]}
            )
            fingerprints = tuple(
                {
                    result.system_fingerprint
                    for result in run.model_results
                    if result.system_fingerprint
                }
            )
            for trial in range(command.repeats):
                observation = await self.judge.evaluate(
                    principal,
                    f"{identity}.{trial}",
                    run.command.goal,
                    run.final_text,
                    public,
                    tuple(evidence_text),
                    actor_models,
                    fingerprints,
                    evidence_text,
                )
                judges.append(observation)
                signals.append(
                    Signal(
                        name=f"judge_{trial}",
                        source="model-judge",
                        verdict=observation.verdict,
                        evidence=observation.evidence,
                        reason=observation.reason,
                    )
                )
        required_groups = scope_groups(
            run.command.goal,
            run.final_text,
            run.command.acceptance.kind,
            case.domain if case else "general",
            case.tags if case else (),
            case.critical if case else False,
            bool(evidence_text),
        )
        semantic: Verdict = "unknown"
        reasons = list(environment_reasons)
        calibration = (
            await self._calibrated(principal, tuple(judges), required_groups) if judges else False
        )
        if judges:
            if any(j.self_eval_bias for j in judges):
                reasons.append("self_evaluation_bias")
            elif calibration and len({j.verdict for j in judges}) == 1:
                semantic = judges[0].verdict
            else:
                reasons.append("judge_uncalibrated_drifted_or_disagrees")
        business = next((s for s in signals if s.name == "business"), None)
        if business and any(
            j.verdict in {"pass", "fail"}
            and business.verdict in {"pass", "fail"}
            and j.verdict != business.verdict
            for j in judges
        ):
            reasons.append("deterministic_and_model_signals_disagree")
        critical = any(s.critical and s.verdict == "fail" for s in signals)
        unknown_tools = sum(r.outcome == "unknown" for r in run.receipts)
        outcome: Literal["pass", "fail", "unknown", "environment_error", "incomplete"]
        if critical:
            outcome = "fail"
        elif run.status in {
            "queued",
            "running",
            "waiting_approval",
            "paused",
            "pausing",
            "cancelling",
        }:
            outcome = "incomplete"
        elif run.reason in ENVIRONMENT_ERRORS or any(
            s.reason.startswith(("artifact_unavailable:", "evidence_unavailable:")) for s in signals
        ):
            outcome = "environment_error"
        elif case and business and business.reason == "case_input_mismatch":
            outcome = "unknown"
        elif any(
            s.source == "deterministic"
            and s.name
            in {"tool_protocol", "citation_structure", "write_scope", "budget_completion"}
            and s.verdict == "fail"
            for s in signals
        ):
            outcome = "fail"
        elif business and business.verdict == "fail":
            outcome = "fail"
        elif command.semantic:
            outcome = semantic
        elif (
            run.command.acceptance.kind == "file"
            and business
            and business.verdict == "pass"
            and not unknown_tools
            and all(s.verdict == "pass" for s in signals if s.name == "tool_protocol")
        ):
            outcome = "pass"
        else:
            outcome = "unknown"
        model_results = {result.request_id: result for result in run.model_results}
        usage_complete = (
            not run.model_request_id
            and len(model_results) + len(run.undispatched_model_request_ids) == run.steps
            and not unknown_tools
        )
        metrics = Metrics(
            confirmed_model_calls=len(model_results),
            unconfirmed_model_calls=max(
                0, run.steps - len(model_results) - len(run.undispatched_model_request_ids)
            ),
            tokens=sum(
                r.usage.input_tokens + r.usage.output_tokens for r in model_results.values()
            ),
            cost_microusd=sum(r.usage.estimated_cost_microusd for r in model_results.values()),
            tool_attempts=len(run.receipts),
            failed_tools=sum(r.outcome == "failed" for r in run.receipts),
            unknown_tools=unknown_tools,
            extra_model_calls=max(
                0, len(model_results) - (2 if run.command.acceptance.kind == "file" else 1)
            ),
            usage_complete=usage_complete,
            model_latency_ms=sum(r.latency_ms for r in model_results.values()),
        )
        if not usage_complete:
            reasons.append("usage_or_operation_evidence_incomplete")
        if run.source == "test":
            reasons.append("synthetic_runtime_not_release_evidence")
        if split != "test":
            reasons.append("not_protected_final_test")
        if case and case.source == "test_fixture":
            reasons.append("synthetic_case_not_release_evidence")
        identities = {
            (r.model_id, r.reported_model, r.system_fingerprint) for r in run.model_results
        }
        if len(identities) > 1:
            reasons.append("executor_changed_during_run")
        if not run.model_results or any(not r.system_fingerprint for r in run.model_results):
            reasons.append("executor_provenance_incomplete")
        eligible = (
            outcome == "pass"
            and not critical
            and usage_complete
            and environment_verified
            and run.source == "runtime"
            and split == "test"
            and case is not None
            and case.source != "test_fixture"
            and bool(run.model_results)
            and all(r.system_fingerprint for r in run.model_results)
            and len(identities) == 1
        )
        report = EvalReport(
            id=identity,
            request_id=command.request_id,
            project_id=run.command.project_id,
            run_id=run.id,
            checkpoint_event_id=source.event.event_id,
            checkpoint_digest=source.event.digest(),
            checkpoint_version=run.version,
            goal_revision=run.goal_revision,
            config_digest=self.config.digest,
            rubric_revision=self.config.rubric_revision,
            case_id=case.id if case else None,
            bank_revision=command.bank_revision,
            split=split,
            family=case.family if case else run.command.acceptance.kind,
            groups=required_groups,
            split_digest=await self.store.split_digest(
                principal.owner, command.bank_revision, split
            )
            if command.bank_revision
            else None,
            source=run.source,
            status="complete",
            outcome=outcome,
            semantic_verdict=semantic,
            signals=tuple(signals),
            judges=tuple(judges),
            metrics=metrics,
            candidate_revision=candidate_revision(run),
            evaluation_cost_microusd=None
            if any(j.cost_microusd is None for j in judges)
            else sum(j.cost_microusd or 0 for j in judges),
            evaluation_unknown_calls=sum(j.dispatch_outcome == "unknown" for j in judges),
            conditions_digest=signature,
            environment_verified=environment_verified,
            quality_release_eligible=eligible,
            reasons=tuple(dict.fromkeys(reasons)),
        )
        await self.store.put("report", principal.owner, identity, report.model_dump(mode="json"))
        return EvalJob(
            id=identity,
            command=command,
            status="complete",
            reason="assessment_completed_not_a_release",
            report=report,
        )

    async def windows(self, principal: Principal) -> tuple[WindowView, ...]:
        self.user(principal)
        bank = await self.store.bank(principal)
        result = []
        for value in await self.store.list("window", principal.owner):
            window = BlindWindow.model_validate(value)
            current = window.split_digest == await self.store.split_digest(
                principal.owner, bank.revision, window.split
            )
            result.append(
                WindowView(
                    window=window,
                    used=await self.store.window_usage(principal.owner, window.id),
                    current=current,
                )
            )
        return tuple(result)

    async def _window(
        self, owner: str, identity: str | None, revision: str, split: str
    ) -> BlindWindow:
        value = await self.store.get("window", owner, identity or "")
        if value is None:
            raise ApplicationError(
                403, "blind_window_required", "Open an explicit protected window"
            )
        window = BlindWindow.model_validate(value)
        if window.bank_revision != revision or window.split != split:
            raise ApplicationError(409, "blind_window_scope", "Window scope mismatch")
        return window

    async def job(self, principal: Principal, identity: str) -> EvalJob:
        self.user(principal)
        plan = await self.store.get("plan", principal.owner, identity)
        if plan is None:
            raise ApplicationError(404, "assessment_job_missing", "No owned assessment job")
        report = await self.store.get("report", principal.owner, identity)
        running = (
            key(
                principal.owner, "run:" + EvaluateCommand.model_validate(plan["command"]).request_id
            )
            in self.active
        )
        return EvalJob(
            id=identity,
            command=EvaluateCommand.model_validate(plan["command"]),
            status="complete" if report else "running" if running else "blocked",
            reason="immutable_report"
            if report
            else "in_progress"
            if running
            else "interrupted_requires_explicit_retry_with_same_request_id",
            report=await self.report(principal, identity) if report else None,
        )

    async def reports(self, principal: Principal, project: str) -> tuple[EvalReport, ...]:
        self.user(principal)
        # Agent page is also the authoritative project ownership proof, even for an empty history.
        await self.deps.agent.page(principal, project, 0, 1, "")
        values = [
            EvalReport.model_validate(value)
            for value in await self.store.list("report", principal.owner)
        ]
        return tuple(
            [
                await self.report(principal, report.id)
                for report in values
                if report.project_id == project
            ]
        )

    async def report(self, principal: Principal, identity: str) -> EvalReport:
        self.user(principal)
        value = await self.store.get("report", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "assessment_report_missing", "No owned assessment report")
        report = EvalReport.model_validate(value)
        fresh_reasons = []
        if report.config_digest != self.config.digest:
            fresh_reasons.append("assessment_configuration_changed")
        try:
            run, source = await self._subject(
                principal,
                EvaluateCommand(
                    request_id=report.request_id,
                    project_id=report.project_id,
                    run_id=report.run_id,
                    expected_version=report.checkpoint_version,
                ),
            )
            if (
                source.event.digest() != report.checkpoint_digest
                or candidate_revision(run) != report.candidate_revision
            ):
                fresh_reasons.append("assessment_subject_changed")
            case = None
            if report.case_id and report.bank_revision:
                bank = await self.store.bank(principal)
                if (
                    await self.store.split_digest(principal.owner, bank.revision, report.split)
                    != report.split_digest
                ):
                    fresh_reasons.append("protected_bank_changed")
                case = await self.store.protected_case(
                    principal.owner, report.case_id, report.bank_revision
                )
            current_signals = await self.checker.check(principal, run, source, case)
            if report.outcome == "pass" and any(
                signal.source == "deterministic" and signal.verdict != "pass"
                for signal in current_signals
                if signal.name in {"tool_protocol", "business", "citation_structure"}
            ):
                # For semantic research, business is unknown by construction.
                if run.command.acceptance.kind == "file" or any(
                    signal.name != "business" and signal.verdict != "pass"
                    for signal in current_signals
                    if signal.source == "deterministic"
                ):
                    fresh_reasons.append("deterministic_evidence_no_longer_available")
            if (
                report.judges
                and report.semantic_verdict != "unknown"
                and not await self._calibrated(principal, report.judges, report.groups)
            ):
                fresh_reasons.append("judge_calibration_no_longer_valid")
        except ApplicationError as error:
            fresh_reasons.append("source_unavailable:" + error.code)
        return report.model_copy(
            update={
                "quality_release_eligible": report.quality_release_eligible and not fresh_reasons,
                "reasons": tuple(dict.fromkeys((*report.reasons, *fresh_reasons))),
            }
        )

    async def aggregate(self, principal: Principal, project: str) -> Aggregate:
        return aggregate(await self.reports(principal, project))

    async def compare(self, principal: Principal, baseline: str, candidate: str) -> Comparison:
        self.user(principal)
        a, b = (
            await self.store.get("report", principal.owner, baseline),
            await self.store.get("report", principal.owner, candidate),
        )
        if a is None or b is None:
            raise ApplicationError(404, "assessment_report_missing", "No owned comparison reports")
        left = await self.report(principal, baseline)
        right = await self.report(principal, candidate)
        reasons = []
        if (
            left.checkpoint_event_id == right.checkpoint_event_id
            or left.candidate_revision == right.candidate_revision
        ):
            reasons.append("same_candidate_or_subject_not_independent")
        if left.conditions_digest != right.conditions_digest:
            reasons.append("task_input_budget_or_environment_differs")
        if not left.environment_verified or not right.environment_verified:
            reasons.append("environment_not_verified")
        if (
            left.config_digest != right.config_digest
            or left.rubric_revision != right.rubric_revision
            or left.split_digest != right.split_digest
            or left.case_id != right.case_id
        ):
            reasons.append("assessment_protocol_differs")
        if not left.metrics.usage_complete or not right.metrics.usage_complete:
            reasons.append("usage_incomplete")
        if left.source != right.source:
            reasons.append("synthetic_and_runtime_not_comparable")
        return Comparison(
            baseline=baseline,
            candidate=candidate,
            comparable=not reasons,
            reasons=tuple(reasons),
            token_delta=right.metrics.tokens - left.metrics.tokens,
            cost_delta_microusd=right.metrics.cost_microusd - left.metrics.cost_microusd,
            outcome_changed=left.outcome != right.outcome,
        )

    async def batch(self, principal: Principal, command: BatchEvaluation) -> BatchResult:
        return await self.execute(
            principal,
            "batch:" + command.request_id,
            command.model_dump(mode="json"),
            lambda: self._batch(principal, command),
        )

    async def _batch(self, principal: Principal, command: BatchEvaluation) -> BatchResult:
        identity = key(principal.owner, "batch:" + command.request_id)
        plan: dict[str, object] = {
            "command": command.model_dump(mode="json"),
            "configuration": self.config.digest,
        }
        old = await self.store.get("batch-plan", principal.owner, identity)
        if old and old != plan:
            raise ApplicationError(
                409, "assessment_batch_conflict", "Batch has different frozen input"
            )
        saved = await self.store.get("batch-report", principal.owner, identity)
        if saved:
            prior = BatchResult.model_validate(saved)
            refreshed = tuple([await self.report(principal, r.id) for r in prior.reports])
            return prior.model_copy(
                update={"reports": refreshed, "aggregate": aggregate(refreshed)}
            )
        bank = await self.store.bank(principal)
        # The immutable window/consume step checks protected content, not unrelated train additions.
        expected = {case.id for case in bank.cases if case.split == "test"}
        selected = {binding.case_id for binding in command.runs}
        if (
            selected != expected
            or len(selected) != len(command.runs)
            or len({r.run_id for r in command.runs}) != len(command.runs)
        ):
            raise ApplicationError(
                409,
                "assessment_batch_incomplete",
                "A blind batch binds every protected case once, before observing results",
            )
        window = await self._window(
            principal.owner, command.window_id, command.bank_revision, "test"
        )
        child_commands = []
        for binding in command.runs:
            child = EvaluateCommand(
                request_id="b" + key(identity, binding.case_id),
                project_id=command.project_id,
                run_id=binding.run_id,
                expected_version=binding.expected_version,
                case_id=binding.case_id,
                bank_revision=command.bank_revision,
                window_id=window.id,
                semantic=command.semantic,
                repeats=command.repeats,
            )
            child_commands.append(child)
            run, _ = await self._subject(principal, child)
            case = await self.store.protected_case(
                principal.owner, binding.case_id, command.bank_revision
            )
            if run.command.goal != case.prompt or run.command.acceptance.kind != case.kind:
                raise ApplicationError(
                    409, "assessment_case_binding", "Run input does not match the fixed case"
                )
            if candidate_revision(run) != window.candidate_revision:
                raise ApplicationError(
                    409,
                    "assessment_candidate_changed",
                    "All runs must match the declared candidate",
                )
        await self.store.put("batch-plan", principal.owner, identity, plan)
        await self.store.consume_window(
            principal.owner, window.id, command.bank_revision, "test", identity
        )
        reports = []
        blocked = []
        for child in child_commands:
            try:
                job = await self._evaluate(principal, child, identity)
                if job.report:
                    reports.append(job.report)
            except ApplicationError as error:
                blocked.append((child.case_id or "") + ":" + error.code)
        summary = aggregate(tuple(reports))
        if blocked:
            summary = summary.model_copy(
                update={
                    "total": summary.total + len(blocked),
                    "incomplete": summary.incomplete + len(blocked),
                }
            )
        result = BatchResult(
            id=identity,
            bank_revision=command.bank_revision,
            window_id=window.id,
            reports=tuple(reports),
            aggregate=summary,
            expected_cases=len(expected),
            complete=not blocked,
            blocked_cases=tuple(blocked),
        )
        await self.store.put(
            "batch-report", principal.owner, identity, result.model_dump(mode="json")
        )
        return result

    async def calibrations(self, principal: Principal) -> tuple[CalibrationReport, ...]:
        self.user(principal)
        bank = await self.store.bank(principal)
        meta_digest = await self.store.split_digest(principal.owner, bank.revision, "meta")
        reports = [
            CalibrationReport.model_validate(value)
            for value in await self.store.list("calibration-report", principal.owner)
        ]
        return tuple(
            report
            if report.meta_digest == meta_digest
            and report.configuration_digest == self.config.digest
            else report.model_copy(
                update={
                    "passed": False,
                    "reasons": tuple(
                        dict.fromkeys((*report.reasons, "calibration_no_longer_current"))
                    ),
                }
            )
            for report in reports
        )

    async def _calibrated(
        self,
        principal: Principal,
        observations: tuple[JudgeObservation, ...],
        required_groups: tuple[str, ...] = (),
    ) -> bool:
        identities = {judge_identity(observation, self.config) for observation in observations}
        if (
            None in identities
            or len(identities) != 1
            or any(j.source != "remote" or j.self_eval_bias for j in observations)
        ):
            return False
        bank = await self.store.bank(principal)
        meta_digest = await self.store.split_digest(principal.owner, bank.revision, "meta")
        return any(
            report.passed
            and report.source_qualified
            and report.configuration_digest == self.config.digest
            and report.rubric_revision == self.config.rubric_revision
            and report.meta_digest == meta_digest
            and set(required_groups).issubset(report.supported_groups)
            and report.judge_identity in identities
            for report in await self.calibrations(principal)
        )

    async def calibrate(
        self, principal: Principal, command: CalibrationCommand
    ) -> CalibrationReport:
        return await self.execute(
            principal,
            "calibration:" + command.request_id,
            command.model_dump(mode="json"),
            lambda: self._calibrate(principal, command),
        )

    async def _calibrate(
        self, principal: Principal, command: CalibrationCommand
    ) -> CalibrationReport:
        if not self.deps.judge_journal_isolated:
            raise ApplicationError(
                503,
                "private_judge_journal_required",
                "Meta inputs must never enter the execution journal",
            )
        identity = key(principal.owner, "calibration:" + command.request_id)
        plan: dict[str, object] = {
            "command": command.model_dump(mode="json"),
            "configuration": self.config.digest,
        }
        old = await self.store.get("calibration-plan", principal.owner, identity)
        if old and old != plan:
            raise ApplicationError(
                409, "calibration_request_conflict", "Calibration request/configuration changed"
            )
        existing = await self.store.get("calibration-report", principal.owner, identity)
        if existing:
            return CalibrationReport.model_validate(existing)
        bank = await self.store.bank(principal)
        # A protected-split digest permits independent train growth without invalidating meta.
        window = await self._window(
            principal.owner, command.window_id, command.bank_revision, "meta"
        )
        if window.candidate_revision != self.config.digest:
            raise ApplicationError(
                409,
                "calibration_config_changed",
                "Meta window must bind the protected judge configuration digest",
            )
        cases = [
            await self.store.protected_case(principal.owner, case.id, command.bank_revision)
            for case in bank.cases
            if case.split == "meta"
        ]
        if not cases or len(cases) * command.repeats > self.config.max_calibration_calls:
            raise ApplicationError(
                409,
                "calibration_case_limit",
                "Calibration case/repeat count exceeds the protected call budget",
            )
        await self.store.put("calibration-plan", principal.owner, identity, plan)
        await self.store.consume_window(
            principal.owner, window.id, command.bank_revision, "meta", identity
        )
        gold: list[str] = []
        predicted: list[str] = []
        families: dict[str, list[bool]] = {}
        group_rows: dict[str, list[tuple[str, bool, bool]]] = {}
        unique_samples: set[str] = set()
        identities: set[str | None] = set()
        source_qualified = any(
            model.id == self.config.judge_model and model.provider != "mock"
            for model in self.deps.models.catalog()
        )
        samples, positive, negative, disagreements, critical_errors, critical_missing = (
            0,
            0,
            0,
            0,
            0,
            0,
        )
        critical_samples = 0
        judge_calls = unknown_judge_calls = confirmed_judge_tokens = confirmed_judge_cost = 0
        parents: dict[str, str] = {}

        def root(value: str) -> str:
            parents.setdefault(value, value)
            while parents[value] != value:
                parents[value] = parents[parents[value]]
                value = parents[value]
            return value

        for case in cases:
            groups = (
                "family:" + case.family,
                "origin:" + case.origin_group,
                "prompt:" + normalized(case.prompt),
            )
            base = root(groups[0])
            for group in groups[1:]:
                parents[root(group)] = base
        for case in cases:
            canonical = digest(
                {
                    "prompt": case.prompt.casefold(),
                    "answer": case.human_answer,
                    "gold": case.human_verdict,
                }
            )
            if canonical in unique_samples:
                continue
            unique_samples.add(canonical)
            samples += 1
            positive += case.human_verdict == "pass"
            negative += case.human_verdict == "fail"
            observations = []
            for trial in range(command.repeats):
                observation = await self.judge.evaluate(
                    principal,
                    f"{identity}.{case.id}-{trial}",
                    case.prompt,
                    case.human_answer or "",
                    command.confirm_public and case.data_domain == "public",
                    tuple(case.evidence_text),
                    (),
                    (),
                    case.evidence_text,
                )
                observations.append(observation)
                judge_calls += 1
                unknown_judge_calls += observation.dispatch_outcome == "unknown"
                confirmed_judge_tokens += observation.tokens or 0
                confirmed_judge_cost += observation.cost_microusd or 0
                await self.store.put(
                    "calibration-observation",
                    principal.owner,
                    key(identity, case.id + ":" + str(trial)),
                    observation.model_dump(mode="json"),
                )
            identities.update(
                judge_identity(observation, self.config) for observation in observations
            )
            source_qualified = (
                source_qualified
                and case.source == "human_seed"
                and all(o.source == "remote" for o in observations)
            )
            verdicts = {observation.verdict for observation in observations}
            agreed = len(verdicts) == 1
            disagreements += not agreed
            prediction = observations[0].verdict if agreed else "unknown"
            correct = prediction == case.human_verdict
            family_root = root("family:" + case.family)
            families.setdefault(family_root, []).append(correct)
            for group in scope_groups(
                case.prompt,
                case.human_answer or "",
                case.kind,
                case.domain,
                case.tags,
                case.critical,
                bool(case.evidence_text),
            ):
                group_rows.setdefault(group, []).append(
                    (family_root, correct, prediction != "unknown")
                )
            if prediction != "unknown":
                gold.append(case.human_verdict)
                predicted.append(prediction)
            if case.critical:
                critical_samples += 1
                critical_errors += prediction != "unknown" and not correct
                critical_missing += prediction == "unknown"
        known = len(gold)
        agreement = (
            sum(a == b for a, b in zip(gold, predicted, strict=True)) / known if known else None
        )
        # Treat family clusters as independent units rather than counting correlated rewrites.
        lower, _ = wilson(sum(all(values) for values in families.values()), len(families))
        coefficient = kappa(gold, predicted)
        coverage = known / samples if samples else 0
        reasons = []
        if len(families) < self.config.min_calibration_samples:
            reasons.append("insufficient_independent_families")
        if positive < 5 or negative < 5:
            reasons.append("missing_positive_or_negative_gold_coverage")
        if lower is None or lower < self.config.min_calibration_lower:
            reasons.append("agreement_lower_bound_too_low")
        if coefficient is None or coefficient < 0.6:
            reasons.append("kappa_below_threshold")
        if coverage < 0.9:
            reasons.append("abstention_coverage_too_low")
        if critical_samples < 5:
            reasons.append("critical_meta_coverage_missing")
        if critical_errors or critical_missing:
            reasons.append("critical_meta_failure_or_missing_coverage")
        if disagreements:
            reasons.append("repeat_instability")
        if None in identities or len(identities) != 1:
            reasons.append("judge_identity_missing_or_drifted")
        if not source_qualified:
            reasons.append("synthetic_or_nonhuman_meta_provenance")
        group_metrics = {}
        for group, rows in group_rows.items():
            clusters: dict[str, list[bool]] = {}
            for family, correct, _ in rows:
                clusters.setdefault(family, []).append(correct)
            group_lower, _ = wilson(sum(all(values) for values in clusters.values()), len(clusters))
            qualified = (
                len(clusters) >= 10
                and group_lower is not None
                and group_lower >= self.config.min_calibration_lower
                and all(known for _, _, known in rows)
            )
            group_metrics[group] = GroupCalibration(
                samples=len(rows),
                families=len(clusters),
                known=sum(known for _, _, known in rows),
                correct=sum(correct for _, correct, _ in rows),
                wilson_lower=group_lower,
                qualified=qualified,
            )
        report = CalibrationReport(
            id=identity,
            bank_revision=command.bank_revision,
            groups=group_metrics,
            supported_groups=tuple(
                sorted(group for group, metric in group_metrics.items() if metric.qualified)
            ),
            judge_calls=judge_calls,
            unknown_judge_calls=unknown_judge_calls,
            confirmed_judge_tokens=confirmed_judge_tokens,
            confirmed_judge_cost_microusd=confirmed_judge_cost,
            meta_digest=await self.store.split_digest(
                principal.owner, command.bank_revision, "meta"
            ),
            judge_identity=next(iter(identities)) if len(identities) == 1 else None,
            rubric_revision=self.config.rubric_revision,
            configuration_digest=self.config.digest,
            samples=samples,
            known=known,
            families=len(families),
            positive_gold=positive,
            negative_gold=negative,
            agreement=agreement,
            kappa=coefficient,
            wilson_lower=lower,
            coverage=coverage,
            repeat_disagreements=disagreements,
            critical_samples=critical_samples,
            critical_errors=critical_errors,
            critical_missing=critical_missing,
            source_qualified=source_qualified,
            passed=not reasons,
            reasons=tuple(reasons),
        )
        await self.store.put(
            "calibration-report", principal.owner, identity, report.model_dump(mode="json")
        )
        return report
