from dataclasses import dataclass

from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.conversation.ports import WorkspaceConversationPort
from auton.datasets.ports import DatasetPort
from auton.decision_review.ports import DecisionReviewPort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class LearningDependencies:
    conversations: WorkspaceConversationPort
    agent: AgentRuntimePort
    assess: AssessPort
    reviews: DecisionReviewPort
    datasets: DatasetPort
    events: EventLogPort
    runtime: RuntimeDependencies
    test_source: bool = False
