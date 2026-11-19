import asyncio

from auton.constitution.config import Principal
from auton.evolve.arena import ArenaRunner
from auton.evolve.contracts import (
    ArenaCommand,
    ArenaControl,
    ArenaView,
    EvolutionStatus,
    Proposal,
    SubmitProposal,
)
from auton.evolve.proposals import ProposalService
from auton.kernel.ports import ApplicationError


class Evolution(ProposalService):
    runner: ArenaRunner

    async def start(self) -> None:
        await self.store.start()
        self.runner.accepting = True

    async def close(self) -> None:
        # Stop orchestration without replaying any actor, model or approval on shutdown.
        self.runner.accepting = False
        await asyncio.gather(*list(self.runner.tasks.values()), return_exceptions=True)
        await asyncio.gather(*list(self.jobs.values()), return_exceptions=True)
        await self.store.close()

    def status(self) -> EvolutionStatus:
        return EvolutionStatus(
            config_digest=self.config.digest,
            reflection_model=self.config.reflection_model,
            gate_revision=self.config.gate_revision,
            min_development_families=self.config.min_development_families,
            min_repeats=self.config.min_repeats,
            max_arena_model_calls=self.config.max_arena_model_calls,
        )

    async def create_arena(self, principal: Principal, command: ArenaCommand) -> ArenaView:
        return await self.runner.create(principal, command)

    async def arena(self, principal: Principal, identity: str) -> ArenaView:
        return await self.runner.get(principal, identity)

    async def arenas(self, principal: Principal, project: str) -> tuple[ArenaView, ...]:
        return await self.runner.list(principal, project)

    async def control_arena(
        self, principal: Principal, identity: str, command: ArenaControl
    ) -> ArenaView:
        return await self.runner.control(principal, identity, command)

    async def submit(
        self, principal: Principal, proposal: str, command: SubmitProposal
    ) -> Proposal:
        self.user(principal)
        async with self.lock:
            payload = command.model_dump(mode="json")
            receipt = "submit:" + command.request_id
            if await self.store.receipt(principal.owner, receipt, "proposal", proposal, payload):
                saved = await self.proposal(principal, proposal)
                await self.write_playbook(principal, saved)
                return saved
            candidate = await self.proposal(principal, proposal)
            if candidate.version != command.expected_version or not command.direction_reviewed:
                raise ApplicationError(
                    409,
                    "evolution_direction_review_required",
                    "Review the exact current patch and direction",
                )
            arena = await self.runner.load(principal, command.arena_id)
            if (
                candidate.current_arena_id != arena.id
                or arena.command.proposal_id != candidate.id
                or arena.status != "complete"
                or candidate.config_digest != self.config.digest
                or arena.config_digest != self.config.digest
                or arena.assessment_config_digest != self.deps.assess.status().config_digest
                or (await self.deps.assess.bank(principal)).revision != arena.command.bank_revision
            ):
                raise ApplicationError(
                    409,
                    "evolution_evidence_changed",
                    "Repeat evaluation under the current frozen sources",
                )
            base, target = await self.parent(
                principal,
                candidate.command.project_id,
                candidate.command.base_snapshot_id,
                candidate.command.asset_id,
                candidate.parent_blob_sha256,
            )
            current = await self.deps.assets.view(principal, candidate.command.project_id)
            if current.revision != base.revision:
                raise ApplicationError(
                    409, "evolution_parent_changed", "Formal assets changed after evaluation"
                )
            # Re-read evidence; historical pass records do not establish present validity.
            for trial in arena.trials:
                if trial.run_id is None or trial.report_id is None:
                    raise ApplicationError(
                        409, "evolution_evidence_missing", "Complete every fixed trial"
                    )
                run = await self.deps.agent.get(principal, trial.run_id)
                report = await self.deps.assess.report(principal, trial.report_id)
                await self.deps.assets.snapshot(principal, arena.project_id, trial.snapshot_id)
                if (
                    run.version != trial.run_version
                    or run.goal_revision != 1
                    or not report.current_evidence_valid
                ):
                    raise ApplicationError(
                        409,
                        "evolution_evidence_changed",
                        "A trial or its delivery changed after evaluation",
                    )
            gates = self.runner.gate.evaluate(candidate, arena, self.config, True)
            if any(g.verdict == "fail" for g in gates):
                raise ApplicationError(
                    409,
                    "evolution_gate_failed",
                    "Failed structural, protocol or regression gates cannot enter learning",
                )
            source = "evolution-proposal:" + candidate.id
            asset = target.model_copy(
                update={
                    "content": candidate.candidate_content,
                    "origin": "inferred",
                    "source": source,
                }
            )
            pending = next((r.asset for r in current.candidates if r.asset.id == asset.id), None)
            # Recover a committed learning write whose acknowledgement was lost, without
            # overwriting another proposal or adding a second Git revision.
            if pending != asset:
                if pending is not None:
                    raise ApplicationError(
                        409,
                        "evolution_learning_occupied",
                        "Review the existing learning candidate first",
                    )
                if current.candidates_revision != command.expected_learning_revision:
                    raise ApplicationError(
                        409, "evolution_learning_changed", "Refresh the learning branch"
                    )
                current = await self.deps.proposals.propose(
                    principal.model_copy(update={"role": "evolution"}),
                    candidate.command.project_id,
                    asset,
                    command.expected_learning_revision,
                )
            updated = candidate.model_copy(
                update={
                    "version": candidate.version + 1,
                    "status": "ready_for_release"
                    if all(g.verdict == "pass" for g in gates)
                    else "review_queue",
                    "gates": gates,
                    "reasons": tuple(dict.fromkeys(r for g in gates for r in g.reasons)),
                    "learning_revision": current.candidates_revision,
                }
            )
            await self.store.put(
                "proposal",
                principal.owner,
                proposal,
                updated.model_dump(mode="json"),
                candidate.version,
                receipt,
                payload,
            )
            await self.write_playbook(principal, updated)
            return updated
