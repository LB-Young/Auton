from dataclasses import dataclass
from typing import Protocol

from auton.agent.ports import AgentRuntimePort
from auton.assess.ports import AssessPort
from auton.constitution.config import Principal
from auton.constitution.secrets import SecretStorePort
from auton.evolve.ports import EvolutionPort
from auton.genome.ports import AssetReadPort, AssetReleasePort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.config import ModelSpec
from auton.model.ports import ModelPublicationPort
from auton.tools.contracts import ToolWorkspace
from auton.training.ports import DecisionTrainingPort, ExecutorTrainingPort


class ValidationWorkspacePort(Protocol):
    async def create_workspace(
        self, principal: Principal, workspace_id: str, title: str, read_only: bool
    ) -> ToolWorkspace: ...
    async def workspace(self, principal: Principal, identity: str) -> ToolWorkspace: ...


@dataclass(frozen=True)
class ReleaseDependencies:
    assets: AssetReadPort
    genome_writer: AssetReleasePort
    models_writer: ModelPublicationPort
    agent: AgentRuntimePort
    assess: AssessPort
    evolve: EvolutionPort
    executor_training: ExecutorTrainingPort
    decision_training: DecisionTrainingPort
    events: EventLogPort
    runtime: RuntimeDependencies
    workspaces: ValidationWorkspacePort
    local_runtime_secrets: SecretStorePort
    local_targets: tuple[ModelSpec, ...] = ()
    test_source: bool = False
