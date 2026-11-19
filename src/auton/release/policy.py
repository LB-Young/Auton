from auton.constitution.config import Principal
from auton.kernel.documents import digest
from auton.model.publication_contracts import input_language
from auton.release.contracts import ReleaseConfig, ReleaseEvidence, ReleasePlanCommand
from auton.release.dependencies import ReleaseDependencies
from auton.release.sources import ReleaseSource


class RolloutPolicy:
    def __init__(self, config: ReleaseConfig, deps: ReleaseDependencies) -> None:
        self.config, self.deps = config, deps

    async def evaluate(
        self, principal: Principal, command: ReleasePlanCommand, source: ReleaseSource
    ) -> ReleaseEvidence:
        blockers = list(source.blockers)
        if command.mode == "canary" and command.percentage > self.config.max_initial_percentage:
            blockers.append("initial_canary_percentage_exceeds_grant")
        if command.mode == "active" and command.percentage != 100:
            blockers.append("active_requires_full_percentage")
        records = []
        candidate_reports = []
        families = set()
        windows = {w.window.id: w for w in await self.deps.assess.windows(principal)}
        bank = await self.deps.assess.bank(principal)
        # Union actual case family AND origin ancestry; connected descendants count once.
        parent = {case.id: case.id for case in bank.cases}

        def root(identity: str) -> str:
            while parent[identity] != identity:
                parent[identity] = parent[parent[identity]]
                identity = parent[identity]
            return identity

        labels: dict[str, str] = {}
        for case in bank.cases:
            if not case.origin_group:
                blockers.append("release_case_origin_missing")
            for label in ("family:" + case.family, "origin:" + case.origin_group):
                if label in labels:
                    parent[root(case.id)] = root(labels[label])
                else:
                    labels[label] = case.id
        components = {case.id: root(case.id) for case in bank.cases}
        cases = set()
        if len(set(command.report_ids)) != len(command.report_ids) or len(
            set(command.baseline_report_ids)
        ) != len(command.baseline_report_ids):
            blockers.append("duplicate_release_evidence")
        if command.mode != "offline" and command.scope.domains != ("general",):
            blockers.append("runtime_domain_classifier_not_configured")
        covered: set[str] = set()
        for identity in command.report_ids:
            report = await self.deps.assess.report(principal, identity)
            job = await self.deps.assess.job(principal, identity)
            window = windows.get(job.command.window_id or "")
            run = await self.deps.agent.get(principal, report.run_id)
            if (
                report.project_id != command.project_id
                or report.split != "test"
                or report.source != "runtime"
                or not report.current_evidence_valid
                or not report.quality_release_eligible
                or not report.environment_verified
                or report.outcome != "pass"
                or not report.metrics.usage_complete
                or any(s.critical and s.verdict != "pass" for s in report.signals)
            ):
                blockers.append("independent_protected_quality_not_passed")
            if (
                window is None
                or not window.current
                or window.used != 1
                or window.window.purpose != "release"
                or window.window.candidate_revision != report.candidate_revision
                or report.bank_revision != bank.revision
            ):
                blockers.append("fresh_bound_release_window_required")
            if command.kind == "executor_model" and (
                run.executor_spec.get("declared_revision") != command.source_id
                or source.model is None
                or not run.model_results
                or run.executor_spec.get("template_revision") != source.model.template_revision
                or run.executor_spec.get("runtime_revision") != source.model.runtime_revision
                or any(
                    r.system_fingerprint != source.model.expected_fingerprint
                    for r in run.model_results
                )
            ):
                blockers.append("evaluated_deployment_does_not_match_bundle")
            if command.kind == "genome":
                if not run.input_asset_snapshot_id:
                    blockers.append("evaluated_asset_snapshot_missing")
                else:
                    snapshot = await self.deps.assets.snapshot(
                        principal, command.project_id, run.input_asset_snapshot_id
                    )
                    asset = next(
                        (
                            a
                            for a in snapshot.assets
                            if a.id == (source.metadata or {}).get("asset_id")
                        ),
                        None,
                    )
                    import hashlib

                    if asset is None or hashlib.sha256(asset.content.encode()).hexdigest() != (
                        source.metadata or {}
                    ).get("candidate_sha256"):
                        blockers.append("evaluated_asset_does_not_match_patch")
            families.add(components.get(report.case_id or "", "missing:" + str(report.case_id)))
            cases.add(report.case_id)
            covered.update(group for group in report.groups if not group.startswith("language:"))
            covered.add("language:" + input_language(run.command.goal))
            covered.add("data_domain:" + run.command.data_domain)
            records.append(report.model_dump(mode="json"))
            candidate_reports.append(report)
        live = command.mode != "offline"
        if live:
            if len(families) < self.config.min_independent_families:
                blockers.append("insufficient_independent_release_families")
            expected = {c.id for c in bank.cases if c.split == "test"}
            if not expected or cases != expected:
                blockers.append("whole_protected_test_batch_required")
            if (
                any("domain:" + d not in covered for d in command.scope.domains)
                or any(
                    "language:" + language not in covered for language in command.scope.languages
                )
                or any("data_domain:" + d not in covered for d in command.scope.data_domains)
            ):
                blockers.append("release_scope_not_covered")
            if command.kind == "executor_model":
                baseline = [
                    await self.deps.assess.report(principal, identity)
                    for identity in command.baseline_report_ids
                ]
                mapping = {report.case_id: report for report in baseline}
                if len(mapping) != len(candidate_reports) or len(baseline) != len(
                    candidate_reports
                ):
                    blockers.append("complete_paired_model_baseline_required")
                improved: dict[str, list[bool]] = {}
                for candidate in candidate_reports:
                    reference = mapping.get(candidate.case_id)
                    if reference is None:
                        continue
                    original = await self.deps.agent.get(principal, reference.run_id)
                    trial = await self.deps.agent.get(principal, candidate.run_id)
                    baseline_job = await self.deps.assess.job(principal, reference.id)
                    baseline_window = windows.get(baseline_job.command.window_id or "")
                    if (
                        reference.project_id != command.project_id
                        or reference.split != "test"
                        or reference.source != "runtime"
                        or not reference.current_evidence_valid
                        or not reference.environment_verified
                        or not reference.metrics.usage_complete
                        or reference.bank_revision != candidate.bank_revision
                        or baseline_window is None
                        or not baseline_window.current
                        or baseline_window.used != 1
                        or baseline_window.window.purpose != "release"
                        or baseline_window.window.candidate_revision != reference.candidate_revision
                    ):
                        blockers.append("paired_baseline_source_invalid")
                    if (
                        original.command.goal != trial.command.goal
                        or original.command.data_domain != trial.command.data_domain
                        or original.command.allowed_tools != trial.command.allowed_tools
                        or original.command.acceptance != trial.command.acceptance
                        or original.command.boundaries != trial.command.boundaries
                        or original.input_asset_snapshot_id != trial.input_asset_snapshot_id
                        or original.budget_limits != trial.budget_limits
                        or original.executor_spec.get("id") != command.baseline_model_id
                    ):
                        blockers.append("paired_model_conditions_changed")
                    if any(
                        receipt.outcome == "unknown"
                        for receipt in (*original.receipts, *trial.receipts)
                    ):
                        blockers.append("paired_model_effect_unknown")
                    improved.setdefault(
                        components.get(
                            candidate.case_id or "", "missing:" + str(candidate.case_id)
                        ),
                        [],
                    ).append(
                        candidate.metrics.model_latency_ms < reference.metrics.model_latency_ms
                    )
                    records.append(reference.model_dump(mode="json"))
                count = len(improved)
                if count:
                    wins = sum(all(values) for values in improved.values())
                    fraction = wins / count
                    z = 1.959963984540054
                    denominator = 1 + z * z / count
                    benefit_lower = (
                        fraction
                        + z * z / (2 * count)
                        - z
                        * (fraction * (1 - fraction) / count + z * z / (4 * count * count)) ** 0.5
                    ) / denominator
                    if (
                        count < self.config.min_independent_families
                        or benefit_lower < self.config.min_quality_lower
                    ):
                        blockers.append("paired_latency_benefit_not_established")
                else:
                    blockers.append("independent_paired_model_benefit_required")
        n = len(families)
        # Conservative all-pass family lower bound, not per-decision IID counting.
        lower = 1 / (1 + 1.959963984540054**2 / n) if n else None
        if live and (lower is None or lower < self.config.min_quality_lower):
            blockers.append("quality_interval_below_predeclared_floor")
        return ReleaseEvidence(
            source_digest=source.digest,
            target_digest=source.target_digest,
            evidence_digest=digest(
                {
                    "source": source.digest,
                    "target": source.target_digest,
                    "reports": records,
                    "policy": self.config.digest,
                    "scope": command.scope.model_dump(mode="json"),
                }
            ),
            eligible=not blockers,
            blockers=tuple(dict.fromkeys(blockers)),
            independent_families=n,
            quality_lower=lower,
            report_ids=command.report_ids,
        )


class RolloutPolicyFactory:
    def create(self, config: ReleaseConfig, deps: ReleaseDependencies) -> RolloutPolicy:
        return RolloutPolicy(config, deps)
