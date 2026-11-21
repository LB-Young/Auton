from pathlib import Path

from auton.conversation.history import HistoryExporter
from auton.conversation.ports import WorkspaceConversationPort
from auton.conversation.service import ConversationDependencies, WorkspaceConversations


class WorkspaceConversationFactory:
    def create(self, deps: ConversationDependencies, directory: Path) -> WorkspaceConversationPort:
        return WorkspaceConversations(deps, HistoryExporter(directory))
