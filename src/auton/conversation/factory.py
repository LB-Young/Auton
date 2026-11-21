from auton.conversation.ports import WorkspaceConversationPort
from auton.conversation.service import ConversationDependencies, WorkspaceConversations


class WorkspaceConversationFactory:
    def create(self, deps: ConversationDependencies) -> WorkspaceConversationPort:
        return WorkspaceConversations(deps)
