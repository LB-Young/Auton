import math
from collections import Counter

from auton.assess.contracts import Aggregate, EvalReport


def wilson(successes: int, total: int) -> tuple[float | None, float | None]:
    if total == 0:
        return None, None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0, centre - radius), min(1, centre + radius)


def aggregate(reports: tuple[EvalReport, ...]) -> Aggregate:
    # Repeating an immutable report or re-running the same subject is not a new sample.
    unique = {
        (r.checkpoint_event_id, r.case_id, r.split_digest, r.rubric_revision): r for r in reports
    }
    values = tuple(unique.values())
    # Accuracy deduplicates subjects; repeated paid judge trials still cost money.
    judge_calls = {j.request_id: j for r in reports for j in r.judges}
    counts = Counter(r.outcome for r in values)
    known = counts["pass"] + counts["fail"]
    low, high = wilson(counts["pass"], known)
    groups: dict[str, dict[str, int]] = {}
    for report in values:
        for label in ("family:" + report.family, *report.groups):
            group = groups.setdefault(
                label,
                {
                    key: 0
                    for key in (
                        "pass",
                        "fail",
                        "unknown",
                        "environment_error",
                        "incomplete",
                        "tokens",
                        "cost_microusd",
                        "tool_failures",
                        "evaluation_unknown_calls",
                    )
                },
            )
            group[report.outcome] += 1
            group["tokens"] += report.metrics.tokens
            group["cost_microusd"] += report.metrics.cost_microusd
            group["tool_failures"] += report.metrics.failed_tools
            group["evaluation_unknown_calls"] += report.evaluation_unknown_calls
    return Aggregate(
        source_counts=dict(Counter(report.source for report in values)),
        split_counts=dict(Counter(report.split for report in values)),
        release_eligible=sum(report.quality_release_eligible for report in values),
        evaluation_cost_microusd=sum(j.cost_microusd or 0 for j in judge_calls.values()),
        evaluation_unknown_calls=sum(j.cost_microusd is None for j in judge_calls.values()),
        total=len(values),
        passed=counts["pass"],
        failed=counts["fail"],
        unknown=counts["unknown"],
        environment_errors=counts["environment_error"],
        incomplete=counts["incomplete"],
        known_denominator=known,
        pass_rate=counts["pass"] / known if known else None,
        wilson_lower=low,
        wilson_upper=high,
        critical_failures=sum(
            any(s.critical and s.verdict == "fail" for s in r.signals) for r in values
        ),
        tokens=sum(r.metrics.tokens for r in values),
        cost_microusd=sum(r.metrics.cost_microusd for r in values),
        groups=groups,
    )


def kappa(gold: list[str], predicted: list[str]) -> float | None:
    if not gold or len(gold) != len(predicted):
        return None
    n = len(gold)
    observed = sum(a == b for a, b in zip(gold, predicted, strict=True)) / n
    a, b = Counter(gold), Counter(predicted)
    chance = sum(a[key] * b[key] for key in set(a) | set(b)) / (n * n)
    return (observed - chance) / (1 - chance) if chance < 1 else None
