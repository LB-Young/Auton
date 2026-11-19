from dataclasses import dataclass

from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.datasets.ports import DatasetPort
from auton.decision_review.ports import DecisionReviewPort
from auton.genome.ports import AssetReadPort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.training.ports import DecisionTrainingPort, ExecutorTrainingPort


@dataclass(frozen=True)
class OperationsDependencies:
    assets: AssetReadPort
    agent: AgentRuntimePort
    assess: AssessPort
    review: DecisionReviewPort
    datasets: DatasetPort
    executor_training: ExecutorTrainingPort
    decision_training: DecisionTrainingPort
    events: EventLogPort
    runtime: RuntimeDependencies
    review_cost_reservation: int
    test_source: bool = False
