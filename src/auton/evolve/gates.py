"""Fixed evaluation rules; candidate text never supplies gate logic or gold labels."""

import hashlib
import math
from collections import defaultdict

from auton.assess.contracts import OptimizationTask, normalize_protected_input
from auton.evolve.contracts import ArenaTrial, ArenaView, EvolutionConfig, GateSignal, Proposal


def sign_probability(wins: int, losses: int) -> float:
    n = wins + losses
    return sum(math.comb(n, k) for k in range(wins, n + 1)) / (2**n) if n else 1.0


def independence_groups(tasks: tuple[OptimizationTask, ...]) -> dict[str, str]:
    parents = {task.case_id: task.case_id for task in tasks}

    def root(identity: str) -> str:
        while parents[identity] != identity:
            parents[identity] = parents[parents[identity]]
            identity = parents[identity]
        return identity

    seen: dict[tuple[str, str], str] = {}
    for task in tasks:
        for kind, value in (
            ("family", task.family),
            ("origin", task.origin_group),
            ("prompt", normalize_protected_input(task.prompt)),
        ):
            token = (kind, value)
            if token in seen:
                parents[root(task.case_id)] = root(seen[token])
            else:
                seen[token] = task.case_id
    members: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        members[root(task.case_id)].append(task.case_id)
    return {
        task.case_id: hashlib.sha256(
            "\0".join(sorted(members[root(task.case_id)])).encode()
        ).hexdigest()
        for task in tasks
    }


class EvolutionGate:
    def evaluate(
        self,
        proposal: Proposal,
        arena: ArenaView,
        config: EvolutionConfig,
        direction_reviewed: bool = False,
    ) -> tuple[GateSignal, ...]:
        result = [gate for gate in proposal.gates if gate.name in {"G1_structure", "G4_playbook"}]
        if not any(gate.name == "G1_structure" for gate in result):
            result.insert(
                0,
                GateSignal(
                    name="G1_structure", verdict="hold", reasons=("structural_gate_missing",)
                ),
            )
        protocol_reasons = []
        executors = {v.executor_signature for v in arena.trials}
        if None in executors or len(executors) != 1:
            protocol_reasons.append("executor_identity_or_pricing_changed_or_unknown")
        if proposal.config_digest != config.digest or arena.config_digest != config.digest:
            protocol_reasons.append("fixed_configuration_changed")
        if arena.status != "complete":
            protocol_reasons.append("arena_not_complete")
        expected = (
            (len(arena.command.train_cases) + len(arena.command.development_cases))
            * 3
            * arena.command.repeats
        )
        if len(arena.trials) != expected:
            protocol_reasons.append("trial_plan_incomplete")
        planned = {
            (case, repeat, variant)
            for case in (*arena.command.train_cases, *arena.command.development_cases)
            for repeat in range(arena.command.repeats)
            for variant in ("baseline", "candidate", "ablation")
        }
        observed = {(v.case_id, v.repeat, v.variant) for v in arena.trials}
        if observed != planned or len(observed) != len(arena.trials):
            protocol_reasons.append("trial_binding_missing_duplicated_or_changed")
        groups: dict[tuple[str, int], list[ArenaTrial]] = defaultdict(list)
        for trial in arena.trials:
            if trial.split != (
                "train" if trial.case_id in arena.command.train_cases else "development"
            ):
                protocol_reasons.append("case_split_binding_changed")
            groups[(trial.case_id, trial.repeat)].append(trial)
        for values in groups.values():
            if (
                len(values) != 3
                or {v.variant for v in values} != {"baseline", "candidate", "ablation"}
                or None in {v.comparison_signature for v in values}
                or len({v.comparison_signature for v in values}) != 1
                or len({v.family for v in values}) != 1
                or len({v.independence_group for v in values}) != 1
            ):
                protocol_reasons.append("task_budget_model_or_uncontrolled_inputs_differ")
            if any(not v.environment_verified or v.unknown_calls for v in values):
                protocol_reasons.append("environment_or_usage_unverified")
        result.append(
            GateSignal(
                name="G2_protocol",
                verdict="fail" if protocol_reasons else "pass",
                reasons=tuple(dict.fromkeys(protocol_reasons)),
            )
        )
        candidates = [v for v in arena.trials if v.variant == "candidate"]
        regression = []
        if not candidates or any(v.outcome != "pass" for v in candidates if v.split == "train"):
            regression.append("core_regression_or_missing_result")
        if any(v.critical and v.outcome == "fail" for v in candidates):
            regression.append("critical_case_failed")
        if any(not v.checkpoints_followed for v in candidates):
            regression.append("required_execution_checkpoint_missing")
        result.append(
            GateSignal(
                name="G2_regression",
                verdict="fail" if regression else "pass",
                reasons=tuple(regression),
                evidence=tuple(v.report_id for v in candidates if v.report_id),
            )
        )
        validation = [v for v in arena.trials if v.split == "development"]
        unknown = any(v.outcome not in {"pass", "fail"} for v in validation)
        families = {v.independence_group for v in validation if v.independence_group}
        repeated = []
        if any(v.independence_group is None for v in validation):
            repeated.append("independence_groups_missing")
        if len(families) < config.min_development_families:
            repeated.append("insufficient_independent_development_families")
        if arena.command.repeats < config.min_repeats:
            repeated.append("insufficient_repeated_trials")
        if unknown:
            repeated.append("unknown_validation_results_not_accuracy_evidence")
        if (
            arena.source != "runtime"
            or proposal.source == "test"
            or any(v.source != "runtime" or v.case_source == "test_fixture" for v in arena.trials)
        ):
            repeated.append("synthetic_evidence_not_release_qualification")
        family_scores: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        for trial in validation:
            if trial.outcome in {"pass", "fail"} and trial.independence_group:
                family_scores[trial.independence_group][trial.variant].append(
                    int(trial.outcome == "pass")
                )
        wins, losses, ablation_wins = 0, 0, 0
        for family, scores in family_scores.items():
            candidate = scores.get("candidate", [])
            baseline = scores.get("baseline", [])
            ablation = scores.get("ablation", [])
            expected_family_trials = (
                len({v.case_id for v in validation if v.independence_group == family})
                * arena.command.repeats
            )
            if (
                len(candidate) != expected_family_trials
                or len(baseline) != len(candidate)
                or len(ablation) != len(candidate)
            ):
                repeated.append("family_coverage_incomplete")
                continue
            delta = sum(candidate) - sum(baseline)
            wins += delta > 0
            losses += delta < 0
            ablation_wins += sum(candidate) > sum(ablation)
        if not wins or sign_probability(wins, losses) > 0.05:
            repeated.append("paired_family_improvement_not_established")
        if any(v.outcome == "fail" for v in candidates if v.split == "development"):
            repeated.append("candidate_validation_failure")
        costs = {
            name: sum(v.cost_microusd for v in validation if v.variant == name)
            for name in ("candidate", "baseline")
        }
        if costs["candidate"] > 1.05 * costs["baseline"]:
            repeated.append("candidate_cost_increase_exceeds_fixed_tolerance")
        result.append(
            GateSignal(
                name="G3_repeated_validation",
                verdict="hold" if repeated else "pass",
                reasons=tuple(dict.fromkeys(repeated)),
            )
        )
        utility = []
        if not ablation_wins or unknown:
            utility.append("no_skill_ablation_does_not_establish_incremental_utility")
        if any(not v.target_retained for v in candidates):
            utility.append("skill_not_retained_in_actual_model_input")
        result.append(
            GateSignal(
                name="G4_skill_utility",
                verdict="hold" if utility else "pass",
                reasons=tuple(utility),
            )
        )
        result.append(
            GateSignal(
                name="G5_direction_review",
                verdict="pass" if direction_reviewed else "hold",
                reasons=()
                if direction_reviewed
                else ("independent_user_direction_review_required",),
            )
        )
        return tuple(result)


class GateFactory:
    def create(self) -> EvolutionGate:
        return EvolutionGate()
