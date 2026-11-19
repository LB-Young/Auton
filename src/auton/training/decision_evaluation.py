"""Independent provenance checks; teacher agreement and static replay cannot certify adoption."""

from dataclasses import dataclass

from auton.agent.contracts import AgentRun
from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.constitution.config import Principal
from auton.kernel.documents import digest, key
from auton.kernel.ports import ApplicationError
from auton.training.contracts import TrainingBundle
from auton.training.decision_contracts import (
    DecisionEvaluation,
    DecisionEvaluationCommand,
    ShadowEvaluation,
    ShadowPrediction,
)


@dataclass(frozen=True)
class DecisionEvaluationDependencies:
    agent: AgentRuntimePort
    assess: AssessPort


class FourLayerEvaluationPolicy:
    def __init__(self, deps: DecisionEvaluationDependencies) -> None:
        self.deps = deps

    async def evaluate(
        self,
        principal: Principal,
        command: DecisionEvaluationCommand,
        candidate: TrainingBundle,
        champion: TrainingBundle | None,
    ) -> DecisionEvaluation:
        blockers = [
            "independent_decision_gold_required",
            "fresh_live_shadow_required",
            "exact_deployment_resource_evaluation_required",
        ]
        layers = {
            "judgment": "descriptive_only",
            "continual_learning": "missing",
            "agent": "missing",
            "deployment": "missing",
        }
        if not candidate.source_current:
            blockers.append("candidate_sources_stale")
        if candidate.source == "test":
            blockers.append("fixture_candidate_not_quality_evidence")
        if champion is None:
            blockers.append("approved_champion_comparison_missing")
        elif champion.kind != "decision" or not champion.source_current:
            blockers.append("champion_scope_or_sources_invalid")
        else:
            layers["continual_learning"] = "descriptive_only"
            blockers.append("paired_champion_regression_evidence_required")
        references = []
        families = set()
        paired = 0
        for pair in command.agent_pairs:
            left = await self.deps.assess.report(principal, pair.reference_report_id)
            right = await self.deps.assess.report(principal, pair.candidate_report_id)
            a = await self.deps.agent.get(principal, left.run_id)
            b = await self.deps.agent.get(principal, right.run_id)
            if left.project_id != command.project_id or right.project_id != command.project_id:
                raise ApplicationError(
                    404, "decision_evaluation_scope", "No owned project evidence"
                )
            if (
                not left.current_evidence_valid
                or not right.current_evidence_valid
                or left.checkpoint_version != a.version
                or right.checkpoint_version != b.version
                or not left.environment_verified
                or not right.environment_verified
            ):
                raise ApplicationError(
                    409,
                    "decision_evaluation_stale",
                    "Independent checks must bind current checkpoints",
                )

            def conditions(run: AgentRun) -> str:
                return digest(
                    {
                        "goal": run.command.goal,
                        "tools": run.command.allowed_tools,
                        "acceptance": run.command.acceptance.model_dump(mode="json"),
                        "executor": run.executor_spec,
                        "limits": run.budget_limits,
                        "assets": run.input_asset_snapshot_id,
                        "domain": run.command.data_domain,
                        "boundaries": run.command.boundaries,
                    }
                )

            if conditions(a) != conditions(b) or a.id == b.id:
                raise ApplicationError(
                    409,
                    "decision_evaluation_uncontrolled_pair",
                    "Only judgment may differ between paired isolated runs",
                )
            if not any(j.adopted and j.source.revision == candidate.id for j in b.judgments):
                blockers.append("candidate_not_actually_adopted_in_agent_pair")
            else:
                paired += 1
                families.add(right.family)
            references.append((left.model_dump(mode="json"), right.model_dump(mode="json")))
        if paired:
            layers["agent"] = "observed"
            blockers.append("predeclared_paired_statistics_and_safety_gates_required")
        else:
            blockers.append("complete_isolated_agent_comparison_missing")
        # Positive KEEP selection is a training source, not a balanced independent
        # benchmark or proof of live task benefits. This policy never launders it.
        return DecisionEvaluation.model_validate(
            {
                "id": key(principal.owner, "decision-evaluation:" + command.request_id),
                "command": command,
                "bundle_digest": digest(candidate.model_dump(mode="json")),
                "evidence_digest": digest(
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "champion": champion.model_dump(mode="json") if champion else None,
                        "pairs": references,
                    }
                ),
                "layers": layers,
                "blockers": tuple(dict.fromkeys(blockers)),
                "current_evidence_valid": candidate.source_current,
                "actual_agent_pairs": paired,
                "independent_agent_families": len(families),
            }
        )


class ShadowEvaluator:
    """Read actual committed offline predictions; never accepts posted model answers."""

    def evaluate(self, records: list[dict[str, object]]) -> ShadowEvaluation:
        predictions = tuple(ShadowPrediction.model_validate(record) for record in records)
        return ShadowEvaluation(predictions=predictions)


class ShadowEvaluatorFactory:
    def create(self) -> ShadowEvaluator:
        return ShadowEvaluator()


class DecisionEvaluationPolicyFactory:
    def create(self, deps: DecisionEvaluationDependencies) -> FourLayerEvaluationPolicy:
        return FourLayerEvaluationPolicy(deps)
