from auton.training.backend import TrainingBackendFactory
from auton.training.contracts import TrainingConfig
from auton.training.data import TrainingDataReader
from auton.training.dependencies import TrainingDependencies
from auton.training.ports import ExecutorTrainingPort
from auton.training.service import ExecutorTraining
from auton.training.store import TrainingStore


class TrainingJobFactory:
    def create(self, config: TrainingConfig, deps: TrainingDependencies) -> TrainingStore:
        return TrainingStore(config, deps.events, deps.runtime, deps.test_source, "training")


class ExecutorTrainingFactory:
    def create(self, config: TrainingConfig, deps: TrainingDependencies) -> ExecutorTrainingPort:
        return ExecutorTraining(
            config,
            deps,
            TrainingJobFactory().create(config, deps),
            TrainingDataReader(deps),
            TrainingBackendFactory().create(config),
        )
