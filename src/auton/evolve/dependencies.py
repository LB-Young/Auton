from dataclasses import dataclass

from auton.agent.contracts import RunLimits
from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.context.ports import ContextEnginePort
from auton.genome.ports import AssetArenaPort, AssetProposalPort, AssetReadPort
from auton.kernel.ports import RuntimeDependencies
from auton.model.ports import ModelGatewayPort
from auton.tools.ports import ToolHostPort


@dataclass(frozen=True)
class EvolutionDependencies:
    assets: AssetReadPort
    arena_assets: AssetArenaPort
    proposals: AssetProposalPort
    assess: AssessPort
    models: ModelGatewayPort
    agent: AgentRuntimePort
    tools: ToolHostPort
    context: ContextEnginePort
    runtime: RuntimeDependencies
    host_limits: RunLimits
    test_source: bool = False
