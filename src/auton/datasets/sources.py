import hashlib
import json
from dataclasses import dataclass

from auton.agent.contracts import AgentRun, checkpoint_event_id
from auton.agent.lineage import conversation_ancestors
from auton.assess.contracts import EvalReport, normalize_protected_input
from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.datasets.contracts import DataGrant, DatasetBuild, SourceProof, SubjectRef
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.store import digest, key
from auton.genome.contracts import Snapshot
from auton.kernel.events import EventScope
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest, ModelResult


@dataclass(frozen=True)
class ModelFrame:
    request: ModelRequest
    result: ModelResult
    request_event: str
    result_event: str


@dataclass(frozen=True)
class SourceSubject:
    ref: SubjectRef
    run: AgentRun
    assets: Snapshot
    report: EvalReport | None
    frames: tuple[ModelFrame, ...]
    proof: SourceProof
    fingerprints: tuple[str, ...]
    group_tokens: tuple[str, ...]
    grant: DataGrant


class DatasetSourceReader:
    def __init__(self, deps: DatasetDependencies) -> None:
        self.deps = deps

    async def protect(
        self, principal: Principal, project: str, run: AgentRun, texts: tuple[str, ...]
    ) -> tuple[str, ...]:
        if run.command.request_id in await self.deps.optimization.optimization_request_ids(
            principal, project
        ):
            raise ApplicationError(
                403,
                "dataset_optimization_input",
                "All optimization variants, including the baseline, are excluded",
            )
        hashes = []
        protected = {
            p.normalized_state_sha256 for p in await self.deps.reviews.protected_inputs(principal)
        }
        for text in dict.fromkeys(texts):
            normalized = normalize_protected_input(text)
            fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
            if fingerprint in protected:
                raise ApplicationError(
                    403, "dataset_reviewer_meta", "Reviewer meta cannot enter any training dataset"
                )
            if await self.deps.events.lookup(
                "assess-protected:" + key(principal.owner, normalized)
            ):
                raise ApplicationError(
                    403,
                    "dataset_protected_holdout",
                    "Protected test/meta prompts and normalized variants cannot be repurposed",
                )
            hashes.append(fingerprint)
        return tuple(dict.fromkeys(hashes))

    async def read(
        self, principal: Principal, command: DatasetBuild, ref: SubjectRef, grant: DataGrant
    ) -> SourceSubject:
        run = await self.deps.agent.get(principal, ref.run_id)
        if (
            run.command.project_id != command.project_id
            or command.project_id != grant.command.project_id
        ):
            raise ApplicationError(404, "dataset_source_scope", "No owned project source")
        if ref.run_id not in grant.command.run_ids or command.kind not in grant.command.purposes:
            raise ApplicationError(
                403,
                "dataset_grant_scope",
                "The explicit local-training grant does not cover this source/purpose",
            )
        if grant.revoked or not grant.command.local_training_authorized:
            raise ApplicationError(
                403, "dataset_training_not_authorized", "Review the concrete local-training grant"
            )
        if run.command.data_domain == "local-only" and not grant.command.allow_local_only_data:
            raise ApplicationError(
                403,
                "dataset_private_scope",
                "Secret data is excluded; local-only data requires an explicit local grant",
            )
        if run.version != ref.expected_version:
            raise ApplicationError(
                409, "dataset_checkpoint_changed", "Freeze the exact original source checkpoint"
            )
        if run.status != "succeeded" or run.model_request_id or run.pending_calls:
            raise ApplicationError(
                409,
                "dataset_source_not_complete",
                "Only completed, independently checked source runs qualify",
            )
        if run.steps != len(run.model_results) + len(run.undispatched_model_request_ids):
            raise ApplicationError(
                409, "dataset_usage_unknown", "Unresolved calls cannot be silently omitted"
            )
        if run.steps != len(run.model_results) + len(run.undispatched_model_request_ids) or any(
            r.outcome == "unknown" for r in run.receipts
        ):
            raise ApplicationError(
                409,
                "dataset_source_effect_unknown",
                "Unknown calls or effects are not supervised as success",
            )
        snapshot_id = run.input_asset_snapshot_id or run.command.asset_snapshot_id
        if snapshot_id is None:
            raise ApplicationError(
                409, "dataset_input_provenance_missing", "Original asset configuration is missing"
            )
        assets = await self.deps.assets.snapshot(principal, command.project_id, snapshot_id)
        if assets.purpose != "runtime":
            raise ApplicationError(
                403,
                "dataset_optimization_input",
                "Optimization arena assets cannot be used as operational training",
            )
        for asset in assets.assets:
            if asset.origin == "inferred":
                raise ApplicationError(
                    403,
                    "dataset_inferred_lineage_unknown",
                    "Automatic assets need independently verified upstream data lineage",
                )
            if asset.origin != "user_explicit" and not any(
                a.asset_id == asset.id
                and a.content_sha256 == hashlib.sha256(asset.content.encode()).hexdigest()
                and a.training_use_confirmed_by_user
                for a in grant.command.external_asset_uses
            ):
                raise ApplicationError(
                    403,
                    "dataset_asset_license_unknown",
                    "External/inferred input content needs exact-blob training permission",
                )
        checkpoint = await self.deps.events.lookup(
            checkpoint_event_id(principal.owner, run.id, run.version)
        )
        seed = await self.deps.events.lookup(checkpoint_event_id(principal.owner, run.id, 0))
        if checkpoint is None or seed is None:
            raise ApplicationError(
                409, "dataset_source_event_missing", "Missing owned source events"
            )
        initial = AgentRun.model_validate(seed.event.payload["run"])
        source_events = await self.deps.events.read(
            limit=1000, scope=EventScope.model_validate({"run_id": run.id})
        )
        if len(source_events) == 1000:
            raise ApplicationError(
                429,
                "dataset_source_event_limit",
                "Segment oversized trajectories before processing",
            )
        feedback = [
            e
            for e in source_events
            if e.event.kind == "agent.user_feedback"
            and e.event.scope.goal_revision == run.goal_revision
        ]
        for event in feedback:
            annotation = event.event.payload.get("command")
            if isinstance(annotation, dict) and annotation.get("rating") == "unhelpful":
                raise ApplicationError(
                    409,
                    "dataset_human_correction_pending",
                    "Negative feedback requires re-evaluation before training",
                )
        ancestors = await conversation_ancestors(principal, run, self.deps.agent)
        for prior in ancestors:
            if not any(
                t.model_id == (prior.resolved_model_id or prior.command.model_id)
                and t.declared_revision == str(prior.executor_spec.get("declared_revision", ""))
                and t.training_use_confirmed_by_user
                for t in grant.command.teacher_uses
            ):
                raise ApplicationError(
                    403,
                    "dataset_history_teacher_terms_unknown",
                    "Historical assistant teachers also need permission",
                )
        texts = [
            initial.command.goal,
            run.command.goal,
            *(m.content for m in run.command.prior_messages if m.role == "user" and m.content),
        ]
        frames = []
        event_refs = [checkpoint.event.event_id, seed.event.event_id]
        for result in run.model_results:
            identity = key(principal.owner, result.request_id)
            started = await self.deps.events.lookup("model:" + identity + ":started")
            completed = await self.deps.events.lookup("model:" + identity + ":completed")
            if started is None or completed is None:
                raise ApplicationError(
                    409,
                    "dataset_model_journal_missing",
                    "Original dispatched request and received output are required",
                )
            request = ModelRequest.model_validate(started.event.payload["request"])
            received = ModelResult.model_validate(completed.event.payload["result"])
            if (
                received != result
                or request.digest != started.event.payload.get("request_digest")
                or request.digest != completed.event.payload.get("request_digest")
                or request.model_id != (run.resolved_model_id or run.command.model_id)
                or request.principal.owner != principal.owner
                or request.goal_id != "agent-goal-" + run.id
                or request.model_id != result.model_id
                or started.cursor >= completed.cursor
                or completed.cursor > checkpoint.cursor
            ):
                raise ApplicationError(
                    409,
                    "dataset_model_provenance_mismatch",
                    "Actor output does not match the actual original model call",
                )
            if result.redacted or result.finish_reason == "length":
                raise ApplicationError(
                    403,
                    "dataset_incomplete_target",
                    "Redacted or truncated teacher output is excluded",
                )
            for message in request.messages:
                if message.content:
                    try:
                        value = json.loads(message.content)
                    except ValueError:
                        value = None
                    if (
                        isinstance(value, dict)
                        and value.get("source") == "host-task-state"
                        and isinstance(value.get("state"), dict)
                        and isinstance(value["state"].get("goal"), str)
                    ):
                        texts.append(value["state"]["goal"])
            if request.goal_revision != run.goal_revision:
                continue
            if request.data_domain == "secret":
                raise ApplicationError(
                    403, "dataset_secret_input", "Secret model inputs are excluded"
                )
            payload = request.model_dump_json() + result.model_dump_json()
            if Redactor().text(payload) != payload:
                raise ApplicationError(
                    403,
                    "dataset_credentials_detected",
                    "Credential-like content is never exported for training",
                )
            if command.kind != "decision" and not any(
                t.model_id == request.model_id
                and t.declared_revision == str(run.executor_spec.get("declared_revision", ""))
                and t.training_use_confirmed_by_user
                for t in grant.command.teacher_uses
            ):
                raise ApplicationError(
                    403,
                    "dataset_teacher_terms_unknown",
                    "Teacher training-use terms require a concrete version-scoped attestation",
                )
            frames.append(
                ModelFrame(request, result, started.event.event_id, completed.event.event_id)
            )
            event_refs.extend((started.event.event_id, completed.event.event_id))
        if run.source == "runtime" and (
            any(not frame.result.system_fingerprint for frame in frames)
            or len(
                {(frame.result.reported_model, frame.result.system_fingerprint) for frame in frames}
            )
            != 1
        ):
            raise ApplicationError(
                409,
                "dataset_teacher_version_unknown",
                "Teacher identity must be observed and stable within the source",
            )
        fingerprints = await self.protect(principal, command.project_id, run, tuple(texts))
        # Check targets for protected gold, without merging unrelated short acknowledgments.
        await self.protect(
            principal,
            command.project_id,
            run,
            (
                run.final_text,
                *(
                    m.content
                    for m in run.command.prior_messages
                    if m.role == "assistant" and m.content
                ),
            ),
        )
        report = None
        if ref.assessment_report_id:
            report = await self.deps.assess.report(principal, ref.assessment_report_id)
            if (
                report.project_id != command.project_id
                or report.run_id != run.id
                or report.checkpoint_version != run.version
            ):
                raise ApplicationError(
                    409,
                    "dataset_assessment_scope",
                    "Independent acceptance belongs to another source checkpoint",
                )
            if report.split in {"test", "meta"}:
                raise ApplicationError(
                    403,
                    "dataset_protected_holdout",
                    "Protected evaluator output is not training data",
                )
            if report.split == "development" and ref.split != "validation":
                raise ApplicationError(
                    403,
                    "dataset_split_locked",
                    "Development evidence cannot be relabeled for gradient training",
                )
            if (
                not report.current_evidence_valid
                or not report.environment_verified
                or report.outcome != "pass"
                or any(s.critical and s.verdict != "pass" for s in report.signals)
            ):
                raise ApplicationError(
                    409,
                    "dataset_acceptance_unqualified",
                    "A final actor claim cannot replace current independent checks",
                )
        elif command.kind != "decision":
            raise ApplicationError(
                409,
                "dataset_independent_acceptance_missing",
                "Provide independent acceptance for the source checkpoint",
            )
        groups = [
            "run:" + run.id,
            "family:" + ref.family,
            "origin:" + ref.origin_group,
            *("run:" + prior.id for prior in ancestors),
        ]
        for prior in ancestors:
            prior_event = await self.deps.events.lookup(
                checkpoint_event_id(principal.owner, prior.id, prior.version)
            )
            if prior_event is None or prior_event.cursor >= seed.cursor:
                raise ApplicationError(
                    409,
                    "dataset_history_checkpoint_missing",
                    "Predecessor evidence must predate the turn",
                )
            event_refs.append(prior_event.event.event_id)
        if report is not None and report.case_id is not None:
            if not report.bank_revision or report.split not in {"train", "development"}:
                raise ApplicationError(
                    409, "dataset_case_lineage_missing", "Case lineage is incomplete"
                )
            task = await self.deps.assess.optimization_task(
                principal,
                report.case_id,
                report.bank_revision,
                "train" if report.split == "train" else "development",
            )
            groups.extend(("family:" + task.family, "origin:" + task.origin_group))
        # EvalReport.groups are language/risk/domain calibration buckets, not
        # shared data ancestry. Operational report.family is just file/research.

        for parent in await self.deps.delegation.list(principal, command.project_id):
            if any(c.run_id == run.id for c in parent.children):
                groups.append("dag:" + parent.id)
        for context_id in run.context_ids:
            context = await self.deps.context.snapshot(
                principal.model_copy(update={"role": "runtime"}), command.project_id, context_id
            )
            if context.asset_snapshot_id != snapshot_id:
                raise ApplicationError(
                    409,
                    "dataset_mixed_input_versions",
                    "Mixed input versions require a separately defined training segment",
                )
        proof = SourceProof(
            run_id=run.id,
            version=run.version,
            goal_revision=run.goal_revision,
            checkpoint_id=checkpoint.event.event_id,
            checkpoint_digest=checkpoint.event.digest(),
            input_snapshot_id=snapshot_id,
            source_digest=digest(
                {
                    "checkpoint": checkpoint.event.digest(),
                    "asset": assets.model_dump(mode="json", exclude_unset=True),
                    "report": report.model_dump(mode="json") if report else None,
                    "events": event_refs,
                    "feedback": [(e.event.event_id, e.event.digest()) for e in feedback],
                    "frames": [
                        (f.request.digest, digest(f.result.model_dump(mode="json"))) for f in frames
                    ],
                }
            ),
            assessment_report_id=ref.assessment_report_id,
            event_refs=tuple(event_refs),
            declared_model=run.executor_spec,
            source="test" if self.deps.test_source or run.source == "test" else "runtime",
        )
        return SourceSubject(
            ref, run, assets, report, tuple(frames), proof, fingerprints, tuple(groups), grant
        )


class DatasetSourceFactory:
    def create(self, deps: DatasetDependencies) -> DatasetSourceReader:
        return DatasetSourceReader(deps)
