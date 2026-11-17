from typing import Literal

from auton.constitution.config import ActionRequest, ConstitutionConfig, PolicyDecision

ROLE_ACTIONS = {
    "runtime": frozenset(
        {
            "demo.start",
            "demo.stop",
            "model.generate",
            "judgment.evaluate",
            "tool.read",
            "tool.write",
        }
    ),
    "training": frozenset({"model.train", "dataset.read"}),
    "evolution": frozenset({"asset.propose", "model.generate", "tool.read"}),
}
PROTECTED = frozenset({"constitution.modify", "checker.modify", "holdout.read", "secret.read"})


class PolicyEvaluator:
    def __init__(self, config: ConstitutionConfig) -> None:
        self.config = config

    def evaluate(self, request: ActionRequest) -> PolicyDecision:
        reasons = []
        if request.action in PROTECTED:
            reasons.append("protected_control")
        if (
            request.principal.role != "user"
            and request.action not in ROLE_ACTIONS[request.principal.role]
        ):
            reasons.append("role_denied")
        if request.action not in self.config.allowed_actions:
            reasons.append("action_denied")
        if request.destination == "remote":
            if request.data_domain != "public":
                reasons.append("data_egress_denied")
            if request.provider not in self.config.remote_providers:
                reasons.append("provider_denied")
        if request.autonomy > self.config.autonomy_max:
            reasons.append("autonomy_exceeded")
        outcome: Literal["allow", "deny", "approval_required"] = (
            "deny"
            if reasons
            else (
                "approval_required" if request.action in self.config.approval_actions else "allow"
            )
        )
        return PolicyDecision(
            outcome=outcome,
            reason_codes=tuple(reasons or [outcome]),
            policy_version=self.config.version,
        )


class PolicyEvaluatorFactory:
    def create(self, config: ConstitutionConfig) -> PolicyEvaluator:
        return PolicyEvaluator(config)
