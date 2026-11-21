from dataclasses import dataclass
from typing import Any

from auton.constitution.config import Principal
from auton.genome.contracts import AssetReleaseCommand
from auton.kernel.documents import digest
from auton.kernel.ports import ApplicationError
from auton.model.config import ModelSpec
from auton.release.contracts import ReleasePlanCommand
from auton.release.dependencies import ReleaseDependencies


@dataclass(frozen=True)
class ReleaseSource:
    digest: str
    target_digest: str
    blockers: tuple[str, ...]
    asset_command: AssetReleaseCommand | None = None
    model: ModelSpec | None = None
    metadata: dict[str, Any] | None = None
    artifact_identity: str = ""


class ReleaseSourceReader:
    def __init__(self, deps: ReleaseDependencies) -> None:
        self.deps = deps

    async def read(self, principal: Principal, command: ReleasePlanCommand) -> ReleaseSource:
        await self.deps.assets.resolve(principal, command.project_id)
        blockers = []
        if command.kind == "genome":
            proposal = await self.deps.evolve.proposal(principal, command.source_id)
            if proposal.command.project_id != command.project_id:
                raise ApplicationError(404, "release_source_scope", "No owned proposal")
            arena = (
                await self.deps.evolve.arena(principal, proposal.current_arena_id)
                if proposal.current_arena_id
                else None
            )
            if proposal.source == "test" or (arena is not None and arena.source != "runtime"):
                blockers.append("fixture_not_release_evidence")
            if (
                proposal.status != "ready_for_release"
                or arena is None
                or not arena.ready_for_release
                or not proposal.gates
                or any(
                    g.verdict != "pass" for g in (*proposal.gates, *(arena.gates if arena else ()))
                )
            ):
                blockers.append("evolution_gates_not_passed")
            view = await self.deps.assets.view(principal, command.project_id)
            candidate = next(
                (
                    r.asset
                    for r in view.candidates
                    if r.asset.source == "evolution-proposal:" + proposal.id
                ),
                None,
            )
            import hashlib

            if (
                candidate is None
                or not proposal.learning_revision
                or proposal.learning_revision != view.candidates_revision
                or hashlib.sha256(candidate.content.encode()).hexdigest()
                != proposal.candidate_sha256
            ):
                blockers.append("reviewed_learning_candidate_missing")
            base = await self.deps.assets.snapshot(
                principal, command.project_id, proposal.command.base_snapshot_id
            )
            asset_target = {
                "candidate_sha256": proposal.candidate_sha256,
                "asset_id": proposal.command.asset_id,
            }
            asset = AssetReleaseCommand(
                release_id="pending",
                project_id=command.project_id,
                asset_id=proposal.command.asset_id,
                candidate_id=candidate.id if candidate else "missing",
                candidates_revision=view.candidates_revision or "missing",
                expected_revision=base.revision,
                content_sha256=proposal.candidate_sha256,
                percentage=command.percentage,
                approval_event_id="pending",
                languages=command.scope.languages,
                data_domains=command.scope.data_domains,
            )
            frozen = {
                "proposal": proposal.model_dump(mode="json"),
                "arena": arena.model_dump(mode="json") if arena else None,
                "parent": base.id,
                "learning": view.candidates_revision,
            }
            return ReleaseSource(
                digest(frozen),
                digest(asset_target),
                tuple(blockers),
                asset_command=asset,
                metadata=asset_target,
                artifact_identity=digest(
                    {"asset": proposal.candidate_sha256, "parent": proposal.parent_blob_sha256}
                ),
            )
        service = (
            self.deps.decision_training
            if command.kind == "decision_model"
            else self.deps.executor_training
        )
        bundles = await service.bundles(principal, command.project_id)
        bundle = next((b for b in bundles if b.id == command.source_id), None)
        if bundle is None:
            raise ApplicationError(
                404, "release_model_missing", "No owned immutable training candidate"
            )
        plans = await service.plans(principal, command.project_id)
        plan = next((p for p in plans if p.id == bundle.plan_id), None)
        if plan is None:
            blockers.append("training_manifest_missing")
        elif command.mode != "offline" and plan.command.engineering_probe:
            blockers.append("engineering_probe_not_publishable")
        if not bundle.source_current:
            blockers.append("training_sources_withdrawn_or_changed")
        if bundle.source != "runtime":
            blockers.append("fixture_not_release_evidence")
        if command.kind == "decision_model":
            if command.mode != "offline":
                blockers.append("decision_online_or_live_shadow_not_authorized")
            return ReleaseSource(
                digest(bundle.model_dump(mode="json")),
                digest({"bundle": bundle.id, "mode": "offline"}),
                tuple(blockers),
                metadata={"bundle_id": bundle.id, "kind": "decision"},
            )
        target = next((m for m in self.deps.local_targets if m.id == command.target_model_id), None)
        if target is None or target.provider != "local":
            blockers.append("local_deployment_binding_missing")
        elif (
            target.declared_revision != bundle.id
            or target.adapter_revision != bundle.files.get("adapter.safetensors")
            or plan is None
            or target.base_manifest_digest != plan.base_manifest_digest
            or target.local_lora_rank != plan.command.rank
        ):
            blockers.append("model_bundle_binding_mismatch")
        frozen = {
            "bundle": bundle.model_dump(mode="json"),
            "deployment": target.model_dump(mode="json") if target else None,
        }
        return ReleaseSource(
            digest(frozen),
            digest(target.model_dump(mode="json") if target else {"missing": True}),
            tuple(blockers),
            model=target,
            metadata={"bundle_id": bundle.id, "kind": "executor"},
            artifact_identity=digest(
                {
                    "base": plan.base_manifest_digest if plan else None,
                    "adapter": bundle.files.get("adapter.safetensors"),
                    "runtime": target.runtime_revision if target else None,
                    "quantization": target.quantization if target else None,
                    "template": target.template_revision if target else None,
                }
            ),
        )
