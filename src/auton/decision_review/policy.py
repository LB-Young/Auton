from auton.decision_review.contracts import (
    Contribution,
    Reasonableness,
    ReviewRecord,
    Verdict,
)
from auton.decision_review.store import digest


def reviewer_signature(record: ReviewRecord) -> str | None:
    a, b = record.stage_a, record.stage_b
    if not a or not b or not a.verdict or not b.verdict:
        return None
    if (
        a.source != "runtime"
        or b.source != "runtime"
        or not a.fingerprint
        or not a.reported_model
        or a.fingerprint != b.fingerprint
        or a.reported_model != b.reported_model
        or not a.model_declaration_digest
        or a.model_declaration_digest != b.model_declaration_digest
    ):
        return None
    question = next(
        q for q in record.subject.request.questions if q.id == record.command.question_id
    )
    return digest(
        {
            "model": a.reported_model,
            "declaration": a.model_declaration_digest,
            "fingerprint": a.fingerprint,
            "config": record.config_digest,
            "question": question.model_dump(mode="json"),
            "teacher": record.subject.decision.source.model_dump(mode="json"),
            "domain": record.subject.request.data_domain,
            "language_bucket": "contains_cjk"
            if any("\u4e00" <= c <= "\u9fff" for c in record.subject.request.state)
            else "other",
            "state_character_bucket": "short"
            if len(record.subject.request.state) <= 1000
            else "medium"
            if len(record.subject.request.state) <= 6000
            else "long",
        }
    )


class AttributionPolicy:
    def assess(
        self, record: ReviewRecord, calibrated: bool, protected: bool = False
    ) -> tuple[Verdict, tuple[str, ...]]:
        s = record.subject
        reasons = list(s.blockers)
        a, b = record.stage_a, record.stage_b
        if not s.decision.adopted:
            return "HOLD", tuple(dict.fromkeys((*reasons, "shadow_answer_not_eligible")))
        if s.goal_changed:
            return "HOLD", tuple(dict.fromkeys((*reasons, "new_goal_cannot_label_old_decision")))
        if s.interaction_group:
            reasons.append("interaction_attribution_not_separable")
        if s.source != "runtime":
            reasons.append("synthetic_decision_not_training_evidence")
        if protected:
            reasons.append("protected_reviewer_meta_never_training")
        if (
            not a
            or not isinstance(a.verdict, Reasonableness)
            or not b
            or not isinstance(b.verdict, Contribution)
        ):
            return "HOLD", tuple(dict.fromkeys((*reasons, "two_stage_evidence_missing")))
        if (
            a.dispatch != "confirmed"
            or b.dispatch != "confirmed"
            or a.cost_microusd is None
            or b.cost_microusd is None
        ):
            reasons.append("reviewer_usage_unknown")
        if reviewer_signature(record) is None:
            reasons.append("reviewer_identity_unverified")
        if s.environment_failure or b.verdict.verdict == "environment_only":
            return "HOLD", tuple(
                dict.fromkeys((*reasons, "environment_failure_not_decision_blame"))
            )
        if not s.causal_link_verified or b.verdict.causal_support not in {
            "controlled",
            "corrective_chain",
        }:
            reasons.append("causal_attribution_insufficient")
        if not calibrated:
            reasons.append("independent_reviewer_meta_gate_closed")
        if a.verdict.verdict == "unreasonable" and b.verdict.verdict == "harmful":
            # Later success does not erase a proven earlier avoidable mistake.
            if not reasons:
                return "DROP", ("supported_bad_decision_with_verified_harm",)
        if (
            a.verdict.verdict == "supported"
            and a.verdict.knowledge_at_time == "sufficient"
            and b.verdict.verdict == "beneficial"
        ):
            if not s.assessment_passed or not s.assessment_current:
                reasons.append("current_independent_acceptance_required")
            if not s.efficiency_comparison_verified or b.verdict.efficiency not in {
                "beneficial",
                "necessary_exploration",
            }:
                reasons.append("efficiency_benefit_not_established")
            if not reasons:
                return "KEEP", ("adopted_supported_verified_beneficial",)
        else:
            reasons.append("reasonableness_or_contribution_unresolved")
        return "HOLD", tuple(dict.fromkeys(reasons))


class AttributionPolicyFactory:
    def create(self) -> AttributionPolicy:
        return AttributionPolicy()
