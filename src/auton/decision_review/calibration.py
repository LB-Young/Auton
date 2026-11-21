"""Human meta labels measure admission quality; repeated/correlated cases count once."""

from collections import Counter

from auton.assess.contracts import normalize_protected_input
from auton.assess.statistics import kappa, wilson
from auton.decision_review.contracts import (
    CalibrationView,
    DecisionReviewConfig,
    MetaCase,
    ReviewRecord,
)
from auton.decision_review.policy import reviewer_signature


def calibrate(
    config: DecisionReviewConfig,
    signature: str | None,
    cases: tuple[MetaCase, ...],
    records: dict[str, ReviewRecord],
) -> CalibrationView:
    reasons = []
    selected = []
    for case in cases:
        record = records.get(case.command.review_id)
        if (
            not case.active
            or record is None
            or not record.evidence_current
            or record.config_digest != config.digest
            or case.source != "runtime"
            or case.reviewer_signature != signature
            or signature is None
            or reviewer_signature(record) != signature
            or case.subject_digest != record.subject.source_digest
            or record.version != case.observed_at_version
        ):
            continue
        selected.append((case, record))
    # DSU clusters family/origin/exact subject/normalized state; different labels
    # in the same cluster are a disagreement rather than extra independent votes.
    parents = list(range(len(selected)))

    def root(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    seen: dict[tuple[str, str], int] = {}
    for i, (case, record) in enumerate(selected):
        for token in (
            ("family", case.command.family),
            ("origin", case.command.origin_group),
            ("state", normalize_protected_input(record.subject.request.state)),
        ):
            if token in seen:
                parents[root(i)] = root(seen[token])
            else:
                seen[token] = i
    clusters: dict[int, list[tuple[MetaCase, ReviewRecord]]] = {}
    for i, value in enumerate(selected):
        clusters.setdefault(root(i), []).append(value)
    observations = []
    for values in clusters.values():
        labels = {(c.command.gold, c.recommended) for c, _ in values}
        if len(labels) != 1:
            reasons.append("correlated_meta_disagreement")
            continue
        observations.append(next(iter(labels)))
    per: Counter[str] = Counter(str(gold) for gold, _ in observations)
    n = len(observations)
    covered = sum(predicted != "HOLD" or gold == "HOLD" for gold, predicted in observations)
    predicted_keep = sum(p == "KEEP" for _, p in observations)
    errors = sum(g != "KEEP" and p == "KEEP" for g, p in observations)
    _, upper = wilson(errors, predicted_keep)
    agreement = (
        kappa([g for g, _ in observations], [p for _, p in observations]) if observations else None
    )
    if n < config.min_meta_families:
        reasons.append("insufficient_independent_human_meta_families")
    if any(per[label] < config.min_meta_per_verdict for label in ("KEEP", "DROP", "HOLD")):
        reasons.append("human_meta_class_coverage_missing")
    if n == 0 or covered / n < config.min_meta_coverage:
        reasons.append("reviewer_meta_coverage_low")
    if agreement is None or agreement < config.min_meta_kappa:
        reasons.append("reviewer_meta_agreement_low")
    if upper is None or upper > config.max_keep_contamination_upper:
        reasons.append("KEEP_contamination_upper_not_qualified")
    if signature is None:
        reasons.append("reviewer_signature_unverified")
    return CalibrationView(
        config_digest=config.digest,
        reviewer_signature=signature,
        eligible=not reasons,
        independent_families=n,
        coverage=covered / n if n else 0,
        kappa=agreement,
        predicted_keep=predicted_keep,
        keep_errors=errors,
        keep_contamination_upper=upper,
        per_verdict=dict(per),
        reasons=tuple(dict.fromkeys(reasons)),
        protected_review_ids=tuple(c.command.review_id for c in cases),
    )
