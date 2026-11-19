from auton.assess.contracts import EvalReport
from auton.evolve.contracts import DiagnoseCommand, Diagnosis


class Diagnoser:
    def diagnose(
        self, identity: str, command: DiagnoseCommand, reports: tuple[EvalReport, ...]
    ) -> Diagnosis:
        categories: set[str] = set()
        reasons: list[str] = []
        usable = []
        for report in reports:
            if not report.current_evidence_valid:
                categories.add("tool_environment")
                reasons.append("stale_evidence_requires_revalidation")
                continue
            if report.split == "train":
                usable.append(report.id)
            if report.outcome == "environment_error" or any(
                "unavailable" in reason for reason in report.reasons
            ):
                categories.add("tool_environment")
            elif any(
                s.source == "deterministic"
                and s.verdict == "fail"
                and s.name in {"model_protocol", "tool_protocol", "budget_completion"}
                for s in report.signals
            ):
                categories.add("execution_capability")
            elif report.outcome in {"unknown", "incomplete"}:
                categories.add("missing_information")
            elif report.outcome == "fail":
                categories.add("asset_hypothesis")
                reasons.append("wrong_delivery_does_not_prove_asset_causation")
            else:
                reasons.append("passing_task_is_not_an_improvement_diagnosis")
        category = (
            next(iter(categories)) if len(categories) == 1 else "mixed" if categories else "unknown"
        )
        action = {
            "tool_environment": "inspect_tools",
            "execution_capability": "inspect_executor",
            "asset_hypothesis": "review_local_patch",
        }.get(category, "collect_evidence")
        if not usable:
            reasons.append("no_train_evidence_for_generation")
            action = "collect_evidence"
        reasons.append("diagnosis_is_a_hypothesis_pending_independent_ablation")
        return Diagnosis.model_validate(
            {
                "id": identity,
                "project_id": command.project_id,
                "asset_id": command.asset_id,
                "report_ids": command.report_ids,
                "category": category,
                "reasons": tuple(dict.fromkeys(reasons)),
                "suggested_action": action,
                "usable_train_reports": tuple(usable),
            }
        )


class DiagnoserFactory:
    def create(self) -> Diagnoser:
        return Diagnoser()
