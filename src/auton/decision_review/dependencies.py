from dataclasses import dataclass

from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.delegation.ports import DelegationPort
from auton.experience.ports import ExperiencePort
from auton.genome.ports import AssetReadPort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.ports import ModelGatewayPort


@dataclass(frozen=True)
class ReviewDependencies:
    agent: AgentRuntimePort
    assess: AssessPort
    experience: ExperiencePort
    assets: AssetReadPort
    models: ModelGatewayPort
    events: EventLogPort
    runtime: RuntimeDependencies
    test_source: bool = False
    delegation: DelegationPort | None = None
