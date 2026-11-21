from auton.agent.contracts import AgentConfig, AgentRun, CreateRun
from auton.agent.ports import AgentRuntimePort
from auton.agent.repository import RunRepositoryFactory, key
from auton.agent.service import AgentDependencies, AgentRuntime
from auton.model.contracts import ModelMessage


class SessionFactory:
    def create(self, owner: str, project_id: str) -> str:
        return key(owner, project_id)


class RunFactory:
    def create(self, owner: str, command: CreateRun, source: str) -> AgentRun:
        return AgentRun.model_validate(
            {
                "id": key(owner, command.request_id),
                "command": command,
                "history": (
                    *command.prior_messages,
                    ModelMessage(role="user", content=command.goal),
                ),
                "source": source,
            }
        )


class AgentRuntimeFactory:
    def create(self, config: AgentConfig, deps: AgentDependencies) -> AgentRuntimePort:
        return AgentRuntime(
            config,
            deps,
            RunRepositoryFactory().create(deps.events, deps.runtime),
            RunFactory(),
            SessionFactory(),
        )
