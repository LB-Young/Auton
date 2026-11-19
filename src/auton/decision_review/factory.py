from auton.decision_review.contracts import DecisionReviewConfig
from auton.decision_review.dependencies import ReviewDependencies
from auton.decision_review.policy import AttributionPolicyFactory
from auton.decision_review.ports import DecisionReviewPort
from auton.decision_review.reviewer import ReviewerAdapterFactory
from auton.decision_review.service import DecisionReview
from auton.decision_review.sources import DecisionSourceFactory
from auton.decision_review.store import ReviewStore


class DecisionReviewFactory:
    def create(self, config: DecisionReviewConfig, deps: ReviewDependencies) -> DecisionReviewPort:
        return DecisionReview(
            config,
            deps,
            ReviewStore(config, deps.events, deps.runtime, deps.test_source),
            DecisionSourceFactory().create(deps),
            ReviewerAdapterFactory().create(
                deps.models,
                config.reviewer_model,
                config.max_stage_cost_microusd,
                config.max_input_bytes,
            ),
            AttributionPolicyFactory().create(),
        )
