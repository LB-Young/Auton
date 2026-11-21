from dataclasses import dataclass

from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.context.ports import ContextEnginePort
from auton.decision_review.ports import DecisionReviewPort
from auton.delegation.ports import DelegationPort
from auton.evolve.ports import OptimizationInputPort
from auton.genome.ports import AssetReadPort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class DatasetDependencies:
    agent: AgentRuntimePort
    assess: AssessPort
    assets: AssetReadPort
    context: ContextEnginePort
    reviews: DecisionReviewPort
    optimization: OptimizationInputPort
    delegation: DelegationPort
    events: EventLogPort
    runtime: RuntimeDependencies
    test_source: bool = False
