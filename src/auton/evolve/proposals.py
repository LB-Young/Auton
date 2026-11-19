import asyncio
import difflib
import hashlib

from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.evolve.contracts import (
    DiagnoseCommand,
    Diagnosis,
    EvolutionConfig,
    GateSignal,
    GenerationReceipt,
    GenerationRecord,
    PlaybookEntry,
    Proposal,
    ProposalCommand,
    ReflectCommand,
    SectionPatch,
)
from auton.evolve.dependencies import EvolutionDependencies
from auton.evolve.diagnosis import Diagnoser
from auton.evolve.fields import TextSectionField
from auton.evolve.jobs import EvolutionJobs
from auton.evolve.mutation import ReflectionStrategy, TrainSummary
from auton.evolve.store import EvolutionStore, key
from auton.genome.contracts import Asset, Snapshot
from auton.kernel.ports import ApplicationError


class ProposalService:
    def __init__(
        self,
        config: EvolutionConfig,
        deps: EvolutionDependencies,
        store: EvolutionStore,
        field: TextSectionField,
        diagnoser: Diagnoser,
        mutator: ReflectionStrategy,
        lock: asyncio.Lock,
        slots: EvolutionJobs,
    ) -> None:
        self.config, self.deps, self.store = config, deps, store
        self.field, self.diagnoser, self.mutator = field, diagnoser, mutator
        self.lock, self.slots = lock, slots
        self.jobs: dict[str, asyncio.Task[Proposal]] = {}

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(403, "evolution_user_required", "Only users control evolution")

    async def parent(
        self, principal: Principal, project: str, snapshot_id: str, asset_id: str, expected: str
    ) -> tuple[Snapshot, Asset]:
        base = await self.deps.assets.snapshot(principal, project, snapshot_id)
        if base.purpose != "runtime":
            raise ApplicationError(
                422, "evolution_parent_scope", "Choose an ordinary parent snapshot"
            )
        target = next((a for a in base.assets if a.id == asset_id and a.kind == "skill"), None)
        if target is None or hashlib.sha256(target.content.encode()).hexdigest() != expected:
            raise ApplicationError(
                409, "evolution_parent_changed", "Choose the exact parent Skill content"
            )
        return base, target

    async def diagnose(self, principal: Principal, command: DiagnoseCommand) -> Diagnosis:
        self.user(principal)
        identity = key(principal.owner, "diagnosis:" + command.request_id)
        payload = command.model_dump(mode="json")
        async with self.lock:
            await self.deps.assets.resolve(principal, command.project_id)
            if await self.store.receipt(
                principal.owner, "diagnosis:" + command.request_id, "diagnosis", identity, payload
            ):
                saved = await self.store.get("diagnosis", principal.owner, identity)
                assert saved
                return Diagnosis.model_validate(saved)
            reports = tuple(
                [
                    await self.deps.assess.report(principal, item)
                    for item in dict.fromkeys(command.report_ids)
                ]
            )
            if any(r.project_id != command.project_id for r in reports):
                raise ApplicationError(404, "evolution_evidence_scope", "No owned project evidence")
            result = self.diagnoser.diagnose(identity, command, reports)
            await self.store.put(
                "diagnosis",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                None,
                "diagnosis:" + command.request_id,
                payload,
            )
            return result

    async def diagnosis(
        self, principal: Principal, identity: str, project: str, asset_id: str
    ) -> Diagnosis:
        value = await self.store.get("diagnosis", principal.owner, identity)
        if value is None:
            raise ApplicationError(
                404, "evolution_diagnosis_missing", "Select owned diagnostic evidence"
            )
        result = Diagnosis.model_validate(value)
        if result.project_id != project or result.asset_id != asset_id:
            raise ApplicationError(
                404, "evolution_diagnosis_scope", "Diagnosis has a different target"
            )
        return result

    async def proposal(self, principal: Principal, identity: str) -> Proposal:
        self.user(principal)
        value = await self.store.get("proposal", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "evolution_proposal_missing", "No owned proposal")
        result = Proposal.model_validate(value)
        if result.config_digest != self.config.digest and result.status != "rejected":
            return result.model_copy(
                update={
                    "status": "blocked",
                    "reasons": tuple(
                        dict.fromkeys((*result.reasons, "fixed_configuration_changed"))
                    ),
                }
            )
        return result

    async def proposals(self, principal: Principal, project: str) -> tuple[Proposal, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        values = await self.store.list("proposal", principal.owner)
        return tuple(
            [
                await self.proposal(principal, str(v["id"]))
                for v in values
                if v["command"]["project_id"] == project
            ]
        )

    async def playbook(self, principal: Principal, project: str) -> tuple[PlaybookEntry, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            PlaybookEntry.model_validate(v)
            for v in await self.store.list("playbook", principal.owner)
            if v["project_id"] == project
        )

    async def write_playbook(self, principal: Principal, proposal: Proposal) -> None:
        old = await self.store.get("playbook", principal.owner, proposal.id)
        version = int(old["version"]) + 1 if old else 0
        outcome = (
            proposal.status
            if proposal.status in {"rejected", "blocked", "review_queue", "ready_for_release"}
            else "proposed"
        )
        value = PlaybookEntry.model_validate(
            {
                "id": proposal.id,
                "version": version,
                "proposal_id": proposal.id,
                "project_id": proposal.command.project_id,
                "asset_id": proposal.command.asset_id,
                "parent_sha256": proposal.parent_blob_sha256,
                "direction": proposal.command.direction,
                "outcome": outcome,
                "reasons": proposal.reasons,
                "evidence": tuple(
                    dict.fromkeys(ref for gate in proposal.gates for ref in gate.evidence)
                ),
            }
        )
        # Avoid creating new facts just because a caller repeats a read/receipt.
        if old and {k: v for k, v in old.items() if k != "version"} == {
            k: v for k, v in value.model_dump(mode="json").items() if k != "version"
        }:
            return
        await self.store.put(
            "playbook",
            principal.owner,
            proposal.id,
            value.model_dump(mode="json"),
            version - 1 if old else None,
        )

    async def attempt_reasons(
        self,
        principal: Principal,
        command: ProposalCommand | ReflectCommand,
        candidate_digest: str | None = None,
        candidate_text: str | None = None,
    ) -> tuple[str, ...]:
        values = [
            Proposal.model_validate(v) for v in await self.store.list("proposal", principal.owner)
        ]
        related = [
            v
            for v in values
            if v.command.asset_id == command.asset_id
            and v.command.project_id == command.project_id
            and v.parent_blob_sha256 == command.expected_content_sha256
        ]
        reasons = []
        # Conservative parent-level cap also prevents resetting the counter with a new diagnosis id.
        if (
            sum(v.status in {"rejected", "blocked"} for v in related)
            >= self.config.max_failed_attempts
        ):
            reasons.append("parent_iteration_limit_inspect_non_asset_causes")
        if candidate_digest and any(v.candidate_sha256 == candidate_digest for v in related):
            reasons.append("duplicate_candidate_content")
        if candidate_text:
            for value in related[-100:]:
                if value.status not in {"rejected", "blocked"}:
                    continue
                # Lexical heuristic only; this does not claim semantic equivalence.
                if (
                    difflib.SequenceMatcher(
                        a=value.command.direction.casefold(), b=command.direction.casefold()
                    ).ratio()
                    >= 0.95
                    and value.command.patch.after.strip() == candidate_text.strip()
                ):
                    reasons.append("repeated_failed_direction_and_patch")
                    break
        return tuple(reasons)

    async def build(
        self,
        principal: Principal,
        command: ProposalCommand,
        generation: GenerationReceipt | None = None,
    ) -> Proposal:
        _, target = await self.parent(
            principal,
            command.project_id,
            command.base_snapshot_id,
            command.asset_id,
            command.expected_content_sha256,
        )
        diagnosis = await self.diagnosis(
            principal, command.diagnosis_id, command.project_id, command.asset_id
        )
        if Redactor().text(command.model_dump_json()) != command.model_dump_json():
            raise ApplicationError(
                403, "credential_in_proposal", "Credentials cannot enter Skill proposals"
            )
        candidate, diff, gates = self.field.apply(
            target.content, command.expected_content_sha256, command.patch, self.config
        )
        candidate_digest = hashlib.sha256(candidate.encode()).hexdigest()
        reasons = list(
            await self.attempt_reasons(principal, command, candidate_digest, command.patch.after)
        )
        reasons.extend(reason for gate in gates for reason in gate.reasons)
        if generation and generation.reason != "reflection_observed":
            reasons.append(generation.reason)
        if diagnosis.suggested_action != "review_local_patch":
            reasons.append("manual_hypothesis_requires_non_asset_cause_review")
        fatal = any(g.verdict == "fail" for g in gates) or any(
            r != "manual_hypothesis_requires_non_asset_cause_review" for r in reasons
        )
        proposal = Proposal(
            id=key(principal.owner, "proposal:" + command.request_id),
            command=command,
            parent_blob_sha256=command.expected_content_sha256,
            candidate_content=candidate,
            candidate_sha256=candidate_digest,
            diff=diff,
            config_digest=self.config.digest,
            status="blocked"
            if generation
            and (generation.dispatch == "unknown" or generation.source == "unavailable")
            else "rejected"
            if fatal
            else "proposed",
            reasons=tuple(dict.fromkeys(reasons)),
            generation=generation,
            gates=(
                *gates,
                GateSignal(
                    name="G4_playbook",
                    verdict="fail"
                    if any(
                        "duplicate" in r or "iteration_limit" in r or "repeated_failed" in r
                        for r in reasons
                    )
                    else "pass",
                    reasons=tuple(
                        r
                        for r in reasons
                        if "duplicate" in r or "iteration_limit" in r or "repeated_failed" in r
                    ),
                ),
            ),
            source="test"
            if self.deps.test_source
            else "model-proposal"
            if generation
            else "human-proposal",
        )
        return proposal

    async def propose(self, principal: Principal, command: ProposalCommand) -> Proposal:
        self.user(principal)
        identity = key(principal.owner, "proposal:" + command.request_id)
        payload = command.model_dump(mode="json")
        async with self.lock:
            if await self.store.receipt(
                principal.owner, "proposal:" + command.request_id, "proposal", identity, payload
            ):
                result = await self.proposal(principal, identity)
                await self.write_playbook(principal, result)
                return result
            result = await self.build(principal, command)
            await self.store.put(
                "proposal",
                principal.owner,
                identity,
                result.model_dump(mode="json"),
                None,
                "proposal:" + command.request_id,
                payload,
            )
            await self.write_playbook(principal, result)
            return result

    async def reflect(self, principal: Principal, command: ReflectCommand) -> Proposal:
        self.user(principal)
        identity = key(principal.owner, "reflect:" + command.request_id)
        async with self.lock:
            saved = await self.store.get("generation", principal.owner, identity)
            if saved:
                record = GenerationRecord.model_validate(saved)
                if record.command != command or record.config_digest != self.config.digest:
                    raise ApplicationError(
                        409,
                        "evolution_reflection_conflict",
                        "Reflection has different frozen input",
                    )
                if record.proposal_id:
                    return await self.proposal(principal, record.proposal_id)
                prior = await self.store.get(
                    "proposal",
                    principal.owner,
                    key(principal.owner, "proposal:" + command.request_id),
                )
                if prior:
                    proposal = Proposal.model_validate(prior)
                    if (
                        proposal.generation is None
                        or proposal.generation.request_id != "evo-reflect-" + identity[:64]
                    ):
                        raise ApplicationError(
                            409,
                            "evolution_reflection_conflict",
                            "Proposal belongs to another mutation source",
                        )
                    await self.write_playbook(principal, proposal)
                    record = record.model_copy(
                        update={
                            "version": record.version + 1,
                            "proposal_id": proposal.id,
                            "receipt": proposal.generation,
                            "status": "complete"
                            if proposal.status == "proposed"
                            else "blocked"
                            if proposal.status == "blocked"
                            else "rejected",
                            "reason": "proposal_acknowledgement_reconciled",
                        }
                    )
                    await self.store.put(
                        "generation",
                        principal.owner,
                        identity,
                        record.model_dump(mode="json"),
                        record.version - 1,
                    )
                    return proposal
            if identity in self.jobs:
                task = self.jobs[identity]
            else:
                self.slots.acquire("generation:" + identity)
                try:
                    if saved is None:
                        record = GenerationRecord(
                            id=identity,
                            command=command,
                            config_digest=self.config.digest,
                            status="running",
                            reason="user_requested_reflection",
                        )
                        await self.store.put(
                            "generation",
                            principal.owner,
                            identity,
                            record.model_dump(mode="json"),
                            None,
                        )
                    await self.store.capacity(principal.owner, 8)
                    task = asyncio.create_task(self.run_reflection(principal, identity))
                    task.add_done_callback(
                        lambda done: done.exception() if not done.cancelled() else None
                    )
                    self.jobs[identity] = task
                except BaseException:
                    self.slots.release("generation:" + identity)
                    raise
        return await asyncio.shield(task)

    async def run_reflection(self, principal: Principal, identity: str) -> Proposal:
        try:
            saved = await self.store.get("generation", principal.owner, identity)
            assert saved
            record = GenerationRecord.model_validate(saved)
            command = record.command
            _, target = await self.parent(
                principal,
                command.project_id,
                command.base_snapshot_id,
                command.asset_id,
                command.expected_content_sha256,
            )
            diagnosis = await self.diagnosis(
                principal, command.diagnosis_id, command.project_id, command.asset_id
            )
            if diagnosis.suggested_action != "review_local_patch":
                raise ApplicationError(
                    409,
                    "evolution_diagnosis_redirect",
                    "Inspect tools/execution or collect evidence before model reflection",
                )
            if await self.attempt_reasons(principal, command):
                raise ApplicationError(
                    409,
                    "evolution_iteration_limit",
                    "Parent has exhausted bounded failed mutation attempts",
                )
            section = self.field.locate(target.content, command.heading)
            summaries = []
            for report_id in diagnosis.usable_train_reports:
                report = await self.deps.assess.report(principal, report_id)
                if (
                    report.split != "train"
                    or not report.current_evidence_valid
                    or report.config_digest != self.deps.assess.status().config_digest
                ):
                    continue
                is_public = False
                if report.case_id and report.bank_revision:
                    case = await self.deps.assess.optimization_task(
                        principal.model_copy(update={"role": "evolution"}),
                        report.case_id,
                        report.bank_revision,
                        "train",
                    )
                    is_public = case.data_domain == "public"
                summaries.append(
                    TrainSummary(
                        report_id=report.id,
                        public=is_public,
                        reasons=tuple(
                            s.reason[:300]
                            for s in report.signals
                            if s.source == "deterministic" and s.verdict == "fail"
                        )[:12],
                    )
                )
            history = tuple(
                entry.direction
                for entry in await self.playbook(principal, command.project_id)
                if entry.asset_id == command.asset_id
                and entry.parent_sha256 == command.expected_content_sha256
            )[-12:]
            outcome = await self.mutator.generate(
                principal,
                "evo-reflect-" + identity[:64],
                section.body,
                command.heading,
                command.direction,
                tuple(summaries),
                history,
                command.public,
            )
            # Persist spend before source revalidation; a withdrawal cannot erase a paid call.
            async with self.lock:
                record = record.model_copy(
                    update={
                        "version": record.version + 1,
                        "receipt": outcome.receipt,
                        "status": "running",
                        "reason": outcome.receipt.reason,
                    }
                )
                await self.store.put(
                    "generation",
                    principal.owner,
                    identity,
                    record.model_dump(mode="json"),
                    record.version - 1,
                )
                proposal_command = ProposalCommand(
                    request_id=command.request_id,
                    project_id=command.project_id,
                    diagnosis_id=command.diagnosis_id,
                    base_snapshot_id=command.base_snapshot_id,
                    asset_id=command.asset_id,
                    expected_content_sha256=command.expected_content_sha256,
                    patch=SectionPatch(
                        heading=command.heading,
                        before=section.body,
                        after=outcome.patch.new_body if outcome.patch else section.body,
                    ),
                    rationale=outcome.patch.rationale
                    if outcome.patch
                    else "No usable reflected patch was produced.",
                    direction=command.direction,
                )
                proposal = await self.build(principal, proposal_command, outcome.receipt)
                await self.store.put(
                    "proposal", principal.owner, proposal.id, proposal.model_dump(mode="json"), None
                )
                await self.write_playbook(principal, proposal)
                final = record.model_copy(
                    update={
                        "version": record.version + 1,
                        "proposal_id": proposal.id,
                        "status": "blocked"
                        if proposal.status == "blocked"
                        else "rejected"
                        if proposal.status == "rejected"
                        else "complete",
                        "reason": "proposal_saved_no_activation",
                    }
                )
                await self.store.put(
                    "generation",
                    principal.owner,
                    identity,
                    final.model_dump(mode="json"),
                    record.version,
                )
                return proposal
        except ApplicationError as error:
            async with self.lock:
                saved = await self.store.get("generation", principal.owner, identity)
                if saved:
                    record = GenerationRecord.model_validate(saved)
                    final = record.model_copy(
                        update={
                            "version": record.version + 1,
                            "status": "blocked",
                            "reason": error.code,
                        }
                    )
                    await self.store.put(
                        "generation",
                        principal.owner,
                        identity,
                        final.model_dump(mode="json"),
                        record.version,
                    )
            raise
        finally:
            self.jobs.pop(identity, None)
            self.slots.release("generation:" + identity)

    async def generations(self, principal: Principal, project: str) -> tuple[GenerationRecord, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            GenerationRecord.model_validate(v)
            for v in await self.store.list("generation", principal.owner)
            if v["command"]["project_id"] == project
        )
