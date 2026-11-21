"""Descriptive metrics over observed predictions; not an independent quality admission gate."""

import math
from typing import Any


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0, "coverage": 0.0, "selective_accuracy": None}
    correct = answered = severe = 0
    brier = nll = 0.0
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(10)]
    labels: set[str] = set()
    confusion: dict[str, dict[str, int]] = {}
    independent: dict[str, list[bool]] = {}
    for row in rows:
        options = row["options"]
        probabilities = row["probabilities"]
        gold, selected = row["gold"], row["selected_id"]
        if (
            set(options) != set(probabilities)
            or gold not in options
            or selected not in {*options, None}
        ):
            raise ValueError("evaluation_option_scope")
        if (
            any(not math.isfinite(p) or p < 0 or p > 1 for p in probabilities.values())
            or abs(sum(probabilities.values()) - 1) > 1e-5
        ):
            raise ValueError("evaluation_probability_schema")
        hit = selected == gold
        correct += hit
        answered += selected is not None
        confidence = max(probabilities.values())
        bins[min(int(confidence * 10), 9)].append(
            (confidence, max(probabilities, key=probabilities.get) == gold)
        )
        severe += bool(row.get("critical") and selected is not None and not hit)
        brier += sum((p - int(identity == gold)) ** 2 for identity, p in probabilities.items())
        nll -= math.log(max(probabilities[gold], 1e-12))
        point = row["point"]
        true_label = point + ":" + gold
        predicted = point + ":" + (selected or "__abstain__")
        labels.add(true_label)
        labels.update(point + ":" + identity for identity in options)
        confusion.setdefault(true_label, {})[predicted] = (
            confusion.get(true_label, {}).get(predicted, 0) + 1
        )
        independent.setdefault(row["group_id"], []).append(hit)
    f1 = []
    for label in sorted(labels):
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(v.get(label, 0) for actual, v in confusion.items() if actual != label)
        fn = sum(v for predicted, v in confusion.get(label, {}).items() if predicted != label)
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    ece = sum(
        len(bucket)
        / len(rows)
        * abs(sum(c for c, _ in bucket) / len(bucket) - sum(ok for _, ok in bucket) / len(bucket))
        for bucket in bins
        if bucket
    )
    group_successes = sum(all(v) for v in independent.values())
    count = len(independent)
    z = 1.959963984540054
    proportion = group_successes / count
    center = (proportion + z * z / (2 * count)) / (1 + z * z / count)
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / count + z * z / (4 * count * count))
        / (1 + z * z / count)
    )
    return {
        "count": len(rows),
        "independent_groups": count,
        "accuracy": correct / len(rows),
        "macro_f1": sum(f1) / len(f1),
        "coverage": answered / len(rows),
        "selective_accuracy": correct / answered if answered else None,
        "critical_labeled_count": sum("critical" in row for row in rows),
        "severe_errors": severe if any("critical" in row for row in rows) else None,
        "brier": brier / len(rows),
        "nll": nll / len(rows),
        "ece_10_bins": ece,
        "all_correct_group_wilson95": [max(0.0, center - margin), min(1.0, center + margin)],
        "interval_basis": "descriptive_group_all_correct_not_paired_causal_benefit",
        "confusion": confusion,
        "label_basis": "qualified_KEEP_teacher_targets_not_independent_gold",
    }
