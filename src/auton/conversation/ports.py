from typing import Protocol

from auton.agent.contracts import AgentRun
from auton.constitution.config import Principal
from auton.conversation.contracts import (
    ConversationCreate,
    ConversationTurn,
    ConversationView,
    WorkspaceConversation,
)
from auton.kernel.ports import LifecycleHandle


class WorkspaceConversationPort(LifecycleHandle, Protocol):
    async def create(
        self, principal: Principal, command: ConversationCreate
    ) -> WorkspaceConversation: ...
    async def list(self, principal: Principal) -> list[WorkspaceConversation]: ...
    async def view(self, principal: Principal, identity: str) -> ConversationView: ...
    async def send(
        self, principal: Principal, identity: str, command: ConversationTurn
    ) -> AgentRun: ...
