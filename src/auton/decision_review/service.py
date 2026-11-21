import asyncio
import hashlib

from auton.assess.contracts import normalize_protected_input
from auton.constitution.config import Principal
from auton.decision_review.calibration import calibrate
from auton.decision_review.contracts import (
    CalibrationView,
    DecisionReviewConfig,
    HumanRevision,
    MetaCase,
    MetaCaseCommand,
    ProtectedReviewInput,
    ReviewCommand,
    ReviewExport,
    ReviewRecord,
    ReviewStatus,
)
from auton.decision_review.dependencies import ReviewDependencies
from auton.decision_review.policy import AttributionPolicy, reviewer_signature
from auton.decision_review.reviewer import ModelReviewer
from auton.decision_review.sources import DecisionSourceReader
from auton.decision_review.store import ReviewStore, digest, key
from auton.kernel.ports import ApplicationError


class DecisionReview:
    async def protected_inputs(self, principal: Principal) -> tuple[ProtectedReviewInput, ...]:
        self.user(principal)
        output = []
        for case in await self.meta_records(principal):
            record = await self.load(principal, case.command.review_id)
            output.append(
                ProtectedReviewInput(
                    run_id=record.command.run_id,
                    project_id=record.command.project_id,
                    normalized_state_sha256=hashlib.sha256(
                        normalize_protected_input(record.subject.request.state).encode()
                    ).hexdigest(),
                )
            )
        return tuple(output)

    def __init__(
        self,
        config: DecisionReviewConfig,
        deps: ReviewDependencies,
        store: ReviewStore,
        reader: DecisionSourceReader,
        reviewer: ModelReviewer,
        policy: AttributionPolicy,
    ) -> None:
        self.config, self.deps, self.store, self.reader, self.reviewer, self.policy = (
            config,
            deps,
            store,
            reader,
            reviewer,
            policy,
        )
        self.lock = asyncio.Lock()
        self.jobs: dict[str, asyncio.Task[ReviewRecord]] = {}

    async def start(self) -> None:
        await self.store.start()

    async def close(self) -> None:
        await asyncio.gather(*list(self.jobs.values()), return_exceptions=True)
        await self.store.close()

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "decision_review_user_required", "Only users control offline review"
            )

    def status(self) -> ReviewStatus:
        return ReviewStatus(
            config_digest=self.config.digest,
            reviewer_model=self.config.reviewer_model,
            rubric_revision=self.config.rubric_revision,
        )

    async def load(self, principal: Principal, identity: str) -> ReviewRecord:
        value = await self.store.get("review", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "decision_review_not_found", "No owned decision review")
        return ReviewRecord.model_validate(value)

    async def save(
        self, principal: Principal, old: ReviewRecord, **changes: object
    ) -> ReviewRecord:
        new = ReviewRecord.model_validate(
            {**old.model_dump(), **changes, "version": old.version + 1}
        )
        await self.store.put(
            "review", principal.owner, old.id, new.model_dump(mode="json"), old.version
        )
        return new

    async def current(self, principal: Principal, record: ReviewRecord) -> bool:
        if record.config_digest != self.config.digest:
            return False
        spec = next(
            (m for m in self.deps.models.catalog() if m.id == self.config.reviewer_model), None
        )
        if spec is None or any(
            stage
            and stage.model_declaration_digest
            and stage.model_declaration_digest
            != digest(spec.model_dump(mode="json", exclude={"health"}))
            for stage in (record.stage_a, record.stage_b)
        ):
            return False
        try:
            source = await self.reader.read(principal, record.command)
            return source.source_digest == record.subject.source_digest
        except ApplicationError:
            return False

    async def meta_records(self, principal: Principal) -> tuple[MetaCase, ...]:
        return tuple(
            MetaCase.model_validate(v) for v in await self.store.list("meta", principal.owner)
        )

    async def calibration(self, principal: Principal, signature: str | None) -> CalibrationView:
        metas = await self.meta_records(principal)
        selected = tuple(c for c in metas if c.reviewer_signature == signature)
        records = []
        for c in selected:
            value = await self.load(principal, c.command.review_id)
            if (
                value.subject.source_digest == c.subject_digest
                and value.version == c.observed_at_version
                and c.source == "runtime"
                and await self.current(principal, value)
            ):
                records.append(c)
        views = tuple(c for c in records if c.active)
        return calibrate(
            self.config,
            signature,
            views,
            {c.command.review_id: await self.load(principal, c.command.review_id) for c in views},
        )

    async def get(self, principal: Principal, identity: str) -> ReviewRecord:
        self.user(principal)
        record = await self.load(principal, identity)
        fresh = await self.current(principal, record)
        protected = any(c.command.review_id == identity for c in await self.meta_records(principal))
        calibration = await self.calibration(principal, reviewer_signature(record))
        verdict, reasons = self.policy.assess(record, calibration.eligible, protected)
        if record.human_revisions:
            # Human corrections can always exclude a sample. Human KEEP is an
            # annotation and cannot bypass source, attribution or calibration gates.
            if record.human_revisions[-1].proposed_verdict in {"DROP", "HOLD"}:
                verdict = record.human_revisions[-1].proposed_verdict
                reasons = (*reasons, "user_corrected_exclusion")
        if not fresh:
            verdict = "HOLD"
            reasons = (*reasons, "source_or_reviewer_configuration_changed")
        if record.status != "complete" and verdict != "DROP":
            verdict = "HOLD"
            reasons = (*reasons, "review_incomplete")
        return record.model_copy(
            update={
                "verdict": verdict,
                "reason_codes": tuple(dict.fromkeys(reasons)),
                "evidence_current": fresh,
                "positive_training_eligible": verdict == "KEEP" and fresh and not protected,
                "qualification_signature": reviewer_signature(record)
                if verdict == "KEEP"
                else None,
            }
        )

    async def list(self, principal: Principal, project: str) -> tuple[ReviewRecord, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            [
                await self.get(principal, str(v["id"]))
                for v in await self.store.list("review", principal.owner)
                if v["command"]["project_id"] == project
            ]
        )

    async def review(self, principal: Principal, command: ReviewCommand) -> ReviewRecord:
        self.user(principal)
        identity = key(principal.owner, "review:" + command.request_id)
        async with self.lock:
            old = await self.store.get("review", principal.owner, identity)
            if old:
                record = ReviewRecord.model_validate(old)
                if record.command != command or record.config_digest != self.config.digest:
                    raise ApplicationError(
                        409,
                        "decision_review_request_conflict",
                        "Request has different frozen input",
                    )
                if record.status in {"complete", "blocked"}:
                    return await self.get(principal, identity)
            else:
                subject = await self.reader.read(principal, command)
                all_records = await self.store.list("review", principal.owner)
                if (
                    sum(
                        v["command"]["run_id"] == command.run_id
                        and v["command"]["judgment_id"] == command.judgment_id
                        and v["command"]["question_id"] == command.question_id
                        for v in all_records
                    )
                    >= 3
                ):
                    raise ApplicationError(
                        429,
                        "decision_review_attempt_limit",
                        "Inspect previous reviews before another paid run",
                    )
                record = ReviewRecord(
                    id=identity, command=command, config_digest=self.config.digest, subject=subject
                )
                await self.store.capacity(principal.owner, 8)
                await self.store.put(
                    "review", principal.owner, identity, record.model_dump(mode="json"), None
                )
            if identity not in self.jobs:
                if len(self.jobs) >= self.config.max_active_jobs:
                    raise ApplicationError(
                        429, "decision_review_busy", "Offline reviewer concurrency full"
                    )
                task = asyncio.create_task(self.drive(principal, identity))
                task.add_done_callback(
                    lambda done: done.exception() if not done.cancelled() else None
                )
                self.jobs[identity] = task
            task = self.jobs[identity]
        await asyncio.shield(task)
        return await self.get(principal, identity)

    async def drive(self, principal: Principal, identity: str) -> ReviewRecord:
        try:
            record = await self.load(principal, identity)
            if not await self.current(principal, record):
                return await self.save(
                    principal,
                    record,
                    status="blocked",
                    reason_codes=("source_changed_before_review",),
                )
            if record.stage_a is None:
                record = await self.save(principal, record, status="stage_a")
                receipt = await self.reviewer.review(
                    principal,
                    "dr-a-" + identity[:64],
                    record.subject,
                    "before",
                    record.command.public,
                )
                # Persist A and its spend before building B or validating later effects.
                record = await self.save(principal, record, stage_a=receipt)
            if record.stage_a is None or record.stage_a.verdict is None:
                return await self.save(
                    principal,
                    record,
                    status="blocked",
                    reason_codes=("reasonableness_evidence_missing",),
                )
            if not await self.current(principal, record):
                return await self.save(
                    principal,
                    record,
                    status="blocked",
                    reason_codes=("source_changed_between_stages",),
                )
            if record.stage_b is None:
                record = await self.save(principal, record, status="stage_b")
                receipt = await self.reviewer.review(
                    principal,
                    "dr-b-" + identity[:64],
                    record.subject,
                    "after",
                    record.command.public,
                    record.stage_a,
                )
                record = await self.save(principal, record, stage_b=receipt)
            raw, _ = self.policy.assess(record, True)
            return await self.save(
                principal,
                record,
                status="complete" if record.stage_b and record.stage_b.verdict else "blocked",
                proposed_verdict=raw,
            )
        finally:
            self.jobs.pop(identity, None)

    async def revise(
        self, principal: Principal, identity: str, command: HumanRevision
    ) -> ReviewRecord:
        self.user(principal)
        async with self.lock:
            record = await self.load(principal, identity)
            receipt = "human:" + command.request_id
            if await self.store.receipt(
                principal.owner, receipt, "review", identity, command.model_dump(mode="json")
            ):
                return await self.get(principal, identity)
            if record.version != command.expected_version or identity in self.jobs:
                raise ApplicationError(
                    409, "decision_review_changed", "Review the exact completed checkpoint"
                )
            refs = {f.id for f in (*record.subject.before_evidence, *record.subject.after_evidence)}
            if any(r not in refs for r in command.evidence_refs):
                raise ApplicationError(
                    422,
                    "decision_review_forged_reference",
                    "Reference is not owned frozen evidence",
                )
            result = record.model_copy(
                update={
                    "version": record.version + 1,
                    "human_revisions": (*record.human_revisions, command),
                    "verdict": "HOLD",
                    "positive_training_eligible": False,
                    "qualification_signature": None,
                }
            )
            await self.store.put(
                "review",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                record.version,
                receipt,
                command.model_dump(mode="json"),
            )
            return await self.get(principal, identity)

    async def annotate_meta(
        self, principal: Principal, command: MetaCaseCommand
    ) -> CalibrationView:
        self.user(principal)
        async with self.lock:
            record = await self.load(principal, command.review_id)
            identity = key(principal.owner, "meta:" + command.request_id)
            old = await self.store.get("meta", principal.owner, identity)
            if old:
                if MetaCase.model_validate(old).command != command:
                    raise ApplicationError(
                        409, "decision_meta_request_conflict", "Meta label has different input"
                    )
                return await self.calibration(principal, reviewer_signature(record))
            if (
                not command.confirm_independent_human_annotation
                or command.expected_review_version != record.version
                or record.status != "complete"
                or not await self.current(principal, record)
            ):
                raise ApplicationError(
                    409,
                    "decision_meta_human_required",
                    "Provide an independent human label of the exact current complete review",
                )
            related = [
                c for c in await self.meta_records(principal) if c.command.review_id == record.id
            ]
            if any(c.observed_at_version == record.version for c in related):
                raise ApplicationError(
                    409,
                    "decision_meta_duplicate",
                    "A subject cannot increase calibration votes by repeated labels",
                )
            if any(
                (c.command.family, c.command.origin_group) != (command.family, command.origin_group)
                for c in related
            ):
                raise ApplicationError(
                    409,
                    "decision_meta_family_locked",
                    "Corrections retain the original independence group",
                )
            refs = {f.id for f in (*record.subject.before_evidence, *record.subject.after_evidence)}
            if any(r not in refs for r in command.evidence_refs):
                raise ApplicationError(
                    422, "decision_review_forged_reference", "Use actual frozen evidence references"
                )
            case = MetaCase(
                id=identity,
                command=command,
                reviewer_signature=reviewer_signature(record),
                subject_digest=record.subject.source_digest,
                source=record.subject.source,
                recommended=record.proposed_verdict,
                observed_at_version=record.version,
            )
            await self.store.put(
                "meta", principal.owner, identity, case.model_dump(mode="json"), None
            )
            return await self.calibration(principal, case.reviewer_signature)

    async def calibrations(self, principal: Principal) -> tuple[CalibrationView, ...]:
        self.user(principal)
        signatures = {c.reviewer_signature for c in await self.meta_records(principal)}
        return tuple(
            [
                await self.calibration(principal, s)
                for s in sorted(signatures, key=lambda s: s or "")
            ]
        ) or (await self.calibration(principal, None),)

    async def eligible(self, principal: Principal, project: str) -> tuple[ReviewExport, ...]:
        self.user(principal)
        output = []
        for record in await self.list(principal, project):
            if not record.positive_training_eligible or record.qualification_signature is None:
                continue
            s = record.subject
            question = next(q for q in s.request.questions if q.id == record.command.question_id)
            output.append(
                ReviewExport(
                    id=record.id,
                    version=record.version,
                    source_digest=s.source_digest,
                    input={"state": s.request.state, "question": question.model_dump(mode="json")},
                    target=s.answer.model_dump(mode="json"),
                    qualification_signature=record.qualification_signature,
                )
            )
        return tuple(output)
