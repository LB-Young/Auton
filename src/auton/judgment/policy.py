import math

from pydantic import JsonValue

from auton.constitution.config import PublicPolicy
from auton.judgment.contracts import Answer, JudgmentRequest, Question, RouteDecision
from auton.model.contracts import ModelInfo


def decode(question: Question, raw: JsonValue) -> Answer:
    try:
        if not isinstance(raw, dict):
            raise ValueError("missing_answer")
        if raw.get("error"):
            return Answer(
                question_id=question.id,
                type=question.type,
                status="abstained",
                reason=str(raw["error"]),
            )
        if raw.get("type") != ("noul" if question.type == "boolean" else question.type):
            raise ValueError("answer_type_mismatch")
        confidence = raw.get("answer_confidence")
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, (float, int))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ValueError("invalid_confidence")
        if question.type == "boolean":
            yes = raw["noul"]
            if (
                isinstance(yes, bool)
                or not isinstance(yes, (float, int))
                or not math.isfinite(yes)
                or not 0 <= yes <= 1
            ):
                raise ValueError("invalid_boolean_probability")
            probs = {"no": 1 - float(yes), "yes": float(yes)}
            ids = ["no", "yes"]
        else:
            probs_raw = raw["probabilities"]
            ids = [o.id for o in question.options]
            keys = ids if question.type == "choice" else [str(i) for i in range(len(ids))]
            if not isinstance(probs_raw, dict) or set(probs_raw) != set(keys):
                raise ValueError("option_identity_mismatch")
            probs = {}
            for key, option in zip(keys, ids, strict=True):
                p = probs_raw[key]
                if (
                    isinstance(p, bool)
                    or not isinstance(p, (float, int))
                    or not math.isfinite(p)
                    or not 0 <= p <= 1
                ):
                    raise ValueError("invalid_probability")
                probs[option] = float(p)
            if abs(sum(probs.values()) - 1) > 0.005:
                raise ValueError("invalid_distribution")
        highest = max(probs.values())
        winners = [key for key in ids if probs[key] == highest]
        if len(winners) != 1:
            return Answer(
                question_id=question.id,
                type=question.type,
                status="abstained",
                probabilities=probs,
                reason="tied_options",
            )
        selected = winners[0]
        if question.type == "choice" and raw.get("choice") != selected:
            raise ValueError("choice_probability_mismatch")
        expected = (
            sum(i * probs[key] for i, key in enumerate(ids)) if question.type == "score" else None
        )
        if expected is not None:
            score = raw.get("score")
            if not isinstance(score, (int, float)) or abs(score - expected) > 0.01:
                raise ValueError("score_probability_mismatch")
        return Answer(
            question_id=question.id,
            type=question.type,
            status="answered",
            selected_id=selected,
            probabilities=probs,
            confidence=confidence,
            expected_score=expected,
        )
    except (KeyError, ValueError, TypeError):
        return Answer(
            question_id=question.id,
            type=question.type,
            status="failed",
            reason="invalid_provider_answer",
        )


class RoutePolicy:
    def select(
        self,
        request: JudgmentRequest,
        answers: tuple[Answer, ...],
        candidates: list[ModelInfo],
        policy: PublicPolicy,
    ) -> RouteDecision:
        excluded: dict[str, str] = {}
        eligible = []
        for model in candidates:
            reason = None
            if model.health in {"credential_missing", "unavailable"}:
                reason = "model_unavailable"
            elif model.location == "remote" and request.data_domain != "public":
                reason = "data_egress_denied"
            elif model.location == "remote" and model.provider not in policy.remote_providers:
                reason = "provider_not_allowed"
            elif not set(request.required_capabilities).issubset(model.capabilities):
                reason = "capability_missing"
            elif model.context_tokens < request.required_context_tokens:
                reason = "context_limit"
            if reason:
                excluded[model.id] = reason
            else:
                eligible.append(model)
        by_id = {a.question_id: a for a in answers}
        for q in request.questions:
            a = by_id[q.id]
            if q.point == "information_sufficiency" and (
                a.status != "answered" or (q.type == "boolean" and a.selected_id != "yes")
            ):
                return RouteDecision(
                    status="blocked",
                    reason_codes=("insufficient_information",),
                    policy_version=policy.version,
                    excluded=excluded,
                )
        tier_question = next((q for q in request.questions if q.point == "executor_tier"), None)
        if tier_question is None:
            return RouteDecision(
                status="not_requested", policy_version=policy.version, excluded=excluded
            )
        answer = by_id[tier_question.id]
        if answer.status != "answered":
            return RouteDecision(
                status="blocked",
                reason_codes=("tier_unknown",),
                policy_version=policy.version,
                excluded=excluded,
            )
        ranks = {"small_2b": 0, "small_7b": 1, "strong": 2, "test_fixture": 2}
        required_rank = ranks.get(answer.selected_id or "", 2)
        for model in eligible[:]:
            if ranks[model.executor_tier] < required_rank:
                excluded[model.id] = "insufficient_tier"
                eligible.remove(model)
        if not eligible:
            return RouteDecision(
                status="blocked",
                requested_tier=answer.selected_id,
                reason_codes=("no_eligible_executor",),
                excluded=excluded,
                policy_version=policy.version,
            )
        selected = min(
            eligible, key=lambda m: (ranks[m.executor_tier], m.output_microusd_per_million, m.id)
        )
        return RouteDecision(
            status="proposed",
            model_id=selected.id,
            requested_tier=answer.selected_id,
            reason_codes=("eligible_requested_tier",)
            if selected.executor_tier == answer.selected_id
            else ("local_executor_not_registered", "eligible_stronger_executor"),
            excluded=excluded,
            policy_version=policy.version,
        )


class RoutePolicyFactory:
    def create(self) -> RoutePolicy:
        return RoutePolicy()
