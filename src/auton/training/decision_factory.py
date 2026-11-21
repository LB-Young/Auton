from auton.training.backend import TrainingBackendFactory
from auton.training.contracts import DecisionTrainingConfig
from auton.training.decision import DecisionTraining
from auton.training.decision_data import DecisionDataReader
from auton.training.decision_evaluation import (
    DecisionEvaluationDependencies,
    DecisionEvaluationPolicyFactory,
)
from auton.training.dependencies import TrainingDependencies
from auton.training.ports import DecisionTrainingPort, TrainingBackendPort
from auton.training.store import TrainingStore


class DecisionBackendFactory:
    def create(self, config: DecisionTrainingConfig) -> TrainingBackendPort:
        return TrainingBackendFactory().create(config)


class DecisionTrainingFactory:
    def create(
        self,
        config: DecisionTrainingConfig,
        deps: TrainingDependencies,
        evaluation: DecisionEvaluationDependencies,
    ) -> DecisionTrainingPort:
        service = DecisionTraining(
            config,
            deps,
            TrainingStore(config, deps.events, deps.runtime, deps.test_source, "decision_training"),
            DecisionDataReader(deps),
            DecisionBackendFactory().create(config),
        )
        service.evaluation_policy = DecisionEvaluationPolicyFactory().create(evaluation)
        return service
