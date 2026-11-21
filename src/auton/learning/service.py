"""Durable, owner-scoped discovery and qualification; never trains or publishes models."""

import asyncio
import logging

from auton.agent.contracts import AgentRun
from auton.assess.contracts import EvalReport, EvaluateCommand
from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.datasets.contracts import (
    DataGrantCommand,
    DatasetBuild,
    DatasetKind,
    ExportCommand,
    SubjectRef,
)
from auton.decision_review.contracts import ReviewCommand
from auton.kernel.documents import digest, key
from auton.kernel.ports import ApplicationError
from auton.learning.contracts import (
    LearningCase,
    LearningConfig,
    LearningManifest,
    LearningPolicy,
    LearningPolicyCommand,
    LearningRetry,
    LearningStatus,
)
from auton.learning.dependencies import LearningDependencies
from auton.learning.store import LearningStore

LOG = logging.getLogger(__name__)


class ConversationLearning:
    def __init__(self, config: LearningConfig, deps: LearningDependencies, store: LearningStore):
        self.config, self.deps, self.store = config, deps, store
        self.lock = asyncio.Lock()
        self.observer_lock = asyncio.Lock()
        self.stop = asyncio.Event()
        self.worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.store.start()
        self.stop.clear()
        if self.config.background:
            self.worker = asyncio.create_task(self.run())

    async def close(self) -> None:
        self.stop.set()
        if self.worker:
            # Finish the current immutable operation before dependencies close.
            await self.worker
            self.worker = None
        await self.store.close()

    @staticmethod
    def user(principal: Principal) -> None:
        if principal.role != "user":
            raise ApplicationError(403, "learning_user_required", "User control required")

    async def observe(self, principal: Principal, conversation_id: str) -> None:
        self.user(principal)
        async with self.observer_lock:
            if await self.store.get("conversation", principal.owner, conversation_id) is None:
                await self.store.put(
                    "conversation", principal.owner, conversation_id, {"id": conversation_id}, None
                )

    async def policy(self, principal: Principal) -> LearningPolicy | None:
        raw = await self.store.get("policy", principal.owner, "current")
        return LearningPolicy.model_validate(raw) if raw else None

    async def configure(
        self, principal: Principal, command: LearningPolicyCommand
    ) -> LearningPolicy:
        self.user(principal)
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(403, "learning_credentials_detected", "Do not store credentials")
        async with self.lock:
            old = await self.policy(principal)
            if (old.version if old else None) != command.expected_version:
                raise ApplicationError(409, "learning_policy_changed", "Refresh the policy version")
            value = LearningPolicy(version=old.version + 1 if old else 0, command=command)
            await self.store.put(
                "policy",
                principal.owner,
                "current",
                value.model_dump(mode="json"),
                old.version if old else None,
            )
            return value

    async def cases(self, principal: Principal) -> tuple[LearningCase, ...]:
        return tuple(
            LearningCase.model_validate(raw)
            for raw in await self.store.list("case", principal.owner)
        )

    async def save(
        self, principal: Principal, old: LearningCase, **changes: object
    ) -> LearningCase:
        value = LearningCase.model_validate(
            {**old.model_dump(), **changes, "version": old.version + 1}
        )
        await self.store.put(
            "case", principal.owner, old.id, value.model_dump(mode="json"), old.version
        )
        return value

    async def status(self, principal: Principal) -> LearningStatus:
        self.user(principal)
        cases = await self.cases(principal)
        # Revalidate on read: revocation, checkpoint changes and judge drift must not appear ready.
        current = []
        for case in cases:
            reasons = list(case.reasons)
            if case.stage == "ready":
                for identity in case.dataset_ids:
                    try:
                        snapshot = await self.deps.datasets.get(principal, identity)
                        if not snapshot.current_evidence_valid or not snapshot.training_ready:
                            reasons.extend(
                                snapshot.invalidation_reasons or ("dataset_no_longer_qualified",)
                            )
                    except ApplicationError as error:
                        reasons.append("dataset_unavailable:" + error.code)
            current.append(
                case.model_copy(update={"stage": "hold", "reasons": tuple(dict.fromkeys(reasons))})
                if reasons and case.stage == "ready"
                else case
            )
        return LearningStatus(
            policy=await self.policy(principal),
            reserved_review_calls=sum(c.reserved_review_calls for c in cases),
            cases=tuple(current),
        )

    async def manifest(self, principal: Principal) -> LearningManifest:
        state = await self.status(principal)
        values: dict[str, list[str]] = {}
        for case in state.cases:
            if case.stage != "ready":
                continue
            for identity in case.artifact_ids:
                artifact, _ = await self.deps.datasets.read_artifact(principal, identity)
                snapshot = await self.deps.datasets.get(principal, artifact.snapshot_id)
                field = snapshot.command.kind + "_" + artifact.command.split + "_artifact_ids"
                values.setdefault(field, [])
                if identity not in values[field]:
                    values[field].append(identity)
                if len(values[field]) > 200:
                    raise ApplicationError(
                        429, "learning_manifest_capacity", "Select a bounded training cohort"
                    )
        return LearningManifest.model_validate(values)

    async def retry(
        self, principal: Principal, case_id: str, command: LearningRetry
    ) -> LearningCase:
        self.user(principal)
        async with self.lock:
            raw = await self.store.get("case", principal.owner, case_id)
            if raw is None:
                raise ApplicationError(404, "learning_case_missing", "No owned learning case")
            case = LearningCase.model_validate(raw)
            visible = next(c for c in (await self.status(principal)).cases if c.id == case.id)
            if case.version != command.expected_version or visible.stage not in {
                "hold",
                "rejected",
            }:
                raise ApplicationError(
                    409, "learning_retry_conflict", "Retry an unchanged held case"
                )
            return await self.save(
                principal,
                case,
                stage="collected",
                reasons=(),
                attempt=case.attempt + 1,
                run_version=None,
                decision_outcomes={},
                assessment_id=None,
                review_ids=(),
                dataset_ids=(),
                artifact_ids=(),
                example_keys=(),
            )

    async def run(self) -> None:
        while not self.stop.is_set():
            for owner in await self.store.owners():
                if self.stop.is_set():
                    break
                try:
                    await self.tick(Principal(owner=owner, role="user"))
                except Exception:
                    # One owner's failure cannot starve others. Do not log source text.
                    LOG.error("Conversation learning tick failed; durable cases retained")
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.config.poll_seconds)
            except TimeoutError:
                pass

    async def tick(self, principal: Principal) -> LearningStatus:
        self.user(principal)
        async with self.lock:
            for raw in await self.store.list("conversation", principal.owner):
                view = await self.deps.conversations.view(principal, str(raw["id"]))
                for run in view.turns:
                    identity = key(principal.owner, "learning:" + run.id)
                    if await self.store.get("case", principal.owner, identity) is None:
                        group = key(principal.owner, view.conversation.id)
                        case = LearningCase(
                            id=identity,
                            conversation_id=view.conversation.id,
                            project_id=run.command.project_id,
                            run_id=run.id,
                            split="validation" if int(group[:8], 16) % 10 == 0 else "train",
                        )
                        await self.store.put(
                            "case", principal.owner, identity, case.model_dump(mode="json"), None
                        )
            policy = await self.policy(principal)
            if policy and policy.command.enabled:
                count = 0
                for case in await self.cases(principal):
                    if case.stage not in {"collected", "assessing", "reviewing", "building"}:
                        continue
                    if count >= self.config.max_cases_per_tick:
                        break
                    run = await self.deps.agent.get(principal, case.run_id)
                    if run.status not in {"succeeded", "failed", "cancelled"}:
                        continue
                    count += 1
                    try:
                        await self.process(principal, policy, case, run)
                    except ApplicationError as error:
                        latest = await self.store.get("case", principal.owner, case.id)
                        if latest:
                            await self.save(
                                principal,
                                LearningCase.model_validate(latest),
                                stage="hold",
                                reasons=(error.code,),
                            )
            return await self.status(principal)

    async def reserve(
        self,
        principal: Principal,
        policy: LearningPolicy,
        case: LearningCase,
        count: int,
        stage: str,
        **changes: object,
    ) -> LearningCase:
        used = sum(c.reserved_review_calls for c in await self.cases(principal))
        if used + count > policy.command.max_review_calls:
            raise ApplicationError(
                409, "learning_review_call_budget", "Lifetime review call allowance exhausted"
            )
        return await self.save(
            principal,
            case,
            stage=stage,
            policy_version=policy.version,
            reserved_review_calls=case.reserved_review_calls + count,
            **changes,
        )

    async def process(
        self, principal: Principal, policy: LearningPolicy, case: LearningCase, run: AgentRun
    ) -> None:
        command = policy.command
        if case.stage != "collected" and case.policy_version != policy.version:
            raise ApplicationError(409, "learning_policy_changed", "Retry under the current policy")
        if case.run_version is not None and case.run_version != run.version:
            raise ApplicationError(
                409, "learning_source_changed", "Retry with the current frozen checkpoint"
            )
        if run.command.data_domain != "public" and not command.allow_local_only_data:
            raise ApplicationError(
                403,
                "learning_local_data_not_authorized",
                "Local-only data needs explicit permission",
            )
        if not any(
            t.model_id == (run.resolved_model_id or run.command.model_id)
            and t.declared_revision == str(run.executor_spec.get("declared_revision", ""))
            and t.training_use_confirmed_by_user
            for t in command.teacher_uses
        ):
            raise ApplicationError(
                403, "learning_teacher_terms_unknown", "Attest the concrete teacher revision"
            )
        if case.run_version is None:
            case = await self.save(
                principal, case, run_version=run.version, policy_version=policy.version
            )
        request = "auto-" + digest({"case": case.id, "attempt": case.attempt})[:60]
        report: EvalReport | None = None
        if case.stage == "assessing":
            # A crash around dispatch is ambiguous; never replay a paid request.
            try:
                job = await self.deps.assess.job(principal, key(principal.owner, "run:" + request))
            except ApplicationError as error:
                raise ApplicationError(
                    409,
                    "learning_assessment_dispatch_uncertain",
                    "Inspect interrupted dispatch before explicit retry",
                ) from error
            if job.report is None:
                raise ApplicationError(
                    409, "learning_assessment_dispatch_uncertain", "Inspect before retrying"
                )
            report = job.report
        elif case.assessment_id:
            report = await self.deps.assess.report(principal, case.assessment_id)
        else:
            if not command.allow_remote_review:
                raise ApplicationError(
                    403,
                    "learning_review_transfer_not_authorized",
                    "Enable independent review explicitly",
                )
            case = await self.reserve(principal, policy, case, 2, "assessing")
            job = await self.deps.assess.evaluate(
                principal,
                EvaluateCommand(
                    request_id=request,
                    project_id=case.project_id,
                    run_id=run.id,
                    expected_version=run.version,
                    semantic=True,
                    repeats=2,
                ),
            )
            report = job.report
            if report is None:
                raise ApplicationError(
                    409, "learning_assessment_pending", "Review has no final report"
                )
        case = await self.save(principal, case, assessment_id=report.id, stage="reviewing")
        outcomes = dict(case.decision_outcomes)
        reviews = list(case.review_ids)
        if command.review_decisions:
            for decision in run.judgments:
                for answer in decision.answers:
                    label = decision.request_id + ":" + answer.question_id
                    if label in outcomes:
                        continue
                    if not decision.adopted:
                        outcomes[label] = "HOLD:shadow_answer_not_eligible"
                        continue
                    if not command.allow_remote_review:
                        raise ApplicationError(
                            403,
                            "learning_review_transfer_not_authorized",
                            "Review transfer not authorized",
                        )
                    review_request = (
                        "auto-"
                        + digest({"case": case.id, "attempt": case.attempt, "decision": label})[:60]
                    )
                    # Persist intent and call allowance together. Recover by reading only.
                    marker = "pending:" + review_request
                    if outcomes.get(marker) == "reserved":
                        reviewed = await self.deps.reviews.get(
                            principal, key(principal.owner, "review:" + review_request)
                        )
                    else:
                        outcomes[marker] = "reserved"
                        case = await self.reserve(
                            principal, policy, case, 2, "reviewing", decision_outcomes=outcomes
                        )
                        reviewed = await self.deps.reviews.review(
                            principal,
                            ReviewCommand(
                                request_id=review_request,
                                project_id=case.project_id,
                                run_id=run.id,
                                expected_run_version=run.version,
                                judgment_id=decision.request_id,
                                question_id=answer.question_id,
                                assessment_report_id=report.id,
                                public=run.command.data_domain == "public",
                            ),
                        )
                    outcomes.pop(marker, None)
                    outcomes[label] = reviewed.verdict + ":" + ",".join(reviewed.reason_codes)
                    if reviewed.positive_training_eligible and reviewed.id not in reviews:
                        reviews.append(reviewed.id)
                    case = await self.save(
                        principal, case, decision_outcomes=outcomes, review_ids=tuple(reviews)
                    )
        case = await self.save(principal, case, decision_outcomes=outcomes, stage="building")
        if run.status != "succeeded":
            await self.save(
                principal, case, stage="rejected", reasons=("executor_run_" + run.status,)
            )
            return
        if (
            report.outcome != "pass"
            or not report.current_evidence_valid
            or not report.environment_verified
            or report.semantic_verdict != "pass"
            or report.evaluation_unknown_calls
        ):
            await self.save(
                principal,
                case,
                stage="hold",
                reasons=("independent_assessment_not_qualified", *report.reasons),
            )
            return
        grant = await self.deps.datasets.grant(
            principal,
            DataGrantCommand(
                request_id=request,
                project_id=case.project_id,
                run_ids=(run.id,),
                purposes=("executor", "decision"),
                data_license_reference=command.data_license_reference,
                local_training_authorized=command.local_training_authorized,
                teacher_uses=command.teacher_uses,
                external_asset_uses=command.external_asset_uses,
                allow_local_only_data=command.allow_local_only_data,
            ),
        )
        group = "conversation-" + key(principal.owner, case.conversation_id)[:50]
        dataset_ids, artifacts, example_keys = (
            list(case.dataset_ids),
            list(case.artifact_ids),
            list(case.example_keys),
        )
        failures: list[str] = []
        # Multiple decision answers produce separate snapshots, each with its own causal proof.
        builds: list[tuple[DatasetKind, str | None]] = [("executor", None)]
        builds.extend(("decision", identity) for identity in reviews)
        for kind, review_id in builds:
            build_id = "auto-" + digest({"case": request, "kind": kind, "review": review_id})[:60]
            snapshot = await self.deps.datasets.build(
                principal,
                DatasetBuild(
                    request_id=build_id,
                    project_id=case.project_id,
                    kind=kind,
                    grant_id=grant.id,
                    subjects=(
                        SubjectRef(
                            run_id=run.id,
                            expected_version=run.version,
                            assessment_report_id=report.id,
                            review_id=review_id,
                            family=group,
                            origin_group=group,
                            split=case.split,
                        ),
                    ),
                ),
            )
            if snapshot.id not in dataset_ids:
                dataset_ids.append(snapshot.id)
            if not snapshot.training_ready:
                failures.extend(
                    reason for rejected in snapshot.rejected for reason in rejected.reasons
                )
                if snapshot.status == "engineering_only":
                    failures.append("synthetic_data_not_training_qualified")
                continue
            keys = tuple(
                digest({"kind": e.kind, "input": e.normalized_input, "target": e.normalized_target})
                for e in snapshot.examples
            )
            other_keys = {
                k
                for other in await self.cases(principal)
                if other.id != case.id
                for k in other.example_keys
            }
            if any(k in other_keys for k in keys):
                failures.append("duplicate_qualified_example")
                continue
            artifact = await self.deps.datasets.export(
                principal,
                snapshot.id,
                ExportCommand(
                    request_id=build_id,
                    expected_content_digest=snapshot.content_digest,
                    split=case.split,
                    purpose="local_training" if case.split == "train" else "local_validation",
                ),
            )
            if artifact.id not in artifacts:
                artifacts.append(artifact.id)
            example_keys.extend(k for k in keys if k not in example_keys)
            # Commit each export before moving to the next kind; replays use immutable request ids.
            case = await self.save(
                principal,
                case,
                dataset_ids=tuple(dataset_ids),
                artifact_ids=tuple(artifacts),
                example_keys=tuple(example_keys),
            )
        await self.save(
            principal,
            case,
            stage="ready" if artifacts and not failures else "hold",
            dataset_ids=tuple(dataset_ids),
            artifact_ids=tuple(artifacts),
            example_keys=tuple(example_keys),
            reasons=tuple(dict.fromkeys(failures))
            if artifacts
            else tuple(dict.fromkeys(failures or ["no_qualified_examples"])),
        )
