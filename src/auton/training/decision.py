import json

from auton.constitution.config import Principal
from auton.kernel.documents import digest
from auton.kernel.ports import ApplicationError
from auton.training.data import file_digest
from auton.training.decision_contracts import (
    DecisionEvaluation,
    DecisionEvaluationCommand,
    ShadowEvaluation,
)
from auton.training.decision_evaluation import FourLayerEvaluationPolicy, ShadowEvaluatorFactory
from auton.training.service import ExecutorTraining


class DecisionTraining(ExecutorTraining):
    evaluation_policy: FourLayerEvaluationPolicy

    async def evaluate(
        self, principal: Principal, command: DecisionEvaluationCommand
    ) -> DecisionEvaluation:
        self.user(principal)
        async with self.lock:
            bundles = {b.id: b for b in await self.bundles(principal, command.project_id)}
            candidate = bundles.get(command.bundle_id)
            if candidate is None or candidate.kind != "decision":
                raise ApplicationError(
                    404, "decision_candidate_missing", "No owned decision candidate"
                )
            champion = bundles.get(command.champion_bundle_id or "")
            report = await self.evaluation_policy.evaluate(principal, command, candidate, champion)
            old = await self.store.get("evaluation", principal.owner, report.id)
            if old:
                saved = DecisionEvaluation.model_validate(old)
                if saved.command != command:
                    raise ApplicationError(
                        409, "decision_evaluation_conflict", "Evaluation request is immutable"
                    )
                if digest(saved.model_dump(mode="json")) != digest(report.model_dump(mode="json")):
                    return report.model_copy(
                        update={
                            "blockers": (*report.blockers, "evaluation_sources_changed"),
                            "current_evidence_valid": False,
                        }
                    )
                return saved
            await self.store.put(
                "evaluation", principal.owner, report.id, report.model_dump(mode="json"), None
            )
            return report

    async def evaluations(
        self, principal: Principal, project: str
    ) -> tuple[DecisionEvaluation, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        values = await self.store.list("evaluation", principal.owner)
        reports = []
        for value in values:
            if value["command"]["project_id"] != project:
                continue
            saved = DecisionEvaluation.model_validate(value)
            try:
                reports.append(await self.evaluate(principal, saved.command))
            except ApplicationError as error:
                reports.append(
                    saved.model_copy(
                        update={
                            "current_evidence_valid": False,
                            "blockers": (
                                *saved.blockers,
                                "evaluation_source_unavailable:" + error.code,
                            ),
                        }
                    )
                )
        return tuple(reports)

    async def shadow_replay(
        self, principal: Principal, project: str, bundle_id: str
    ) -> ShadowEvaluation:
        self.user(principal)
        bundle = next(
            (b for b in await self.bundles(principal, project) if b.id == bundle_id), None
        )
        if bundle is None or bundle.kind != "decision" or not bundle.source_current:
            raise ApplicationError(
                409, "decision_shadow_source_invalid", "Current owned decision candidate required"
            )
        job = await self.load(principal, bundle.job_id)
        path = self.directory(job) / "output/predictions-validation.json"
        expected = bundle.auxiliary_files.get(path.name)
        if (
            not expected
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 1000000
            or file_digest(path) != expected
        ):
            raise ApplicationError(
                409, "decision_shadow_evidence_missing", "No immutable held-out prediction evidence"
            )
        return ShadowEvaluatorFactory().create().evaluate(json.loads(path.read_text()))
