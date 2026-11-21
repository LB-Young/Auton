from auton.learning.contracts import LearningConfig
from auton.learning.dependencies import LearningDependencies
from auton.learning.ports import LearningPort
from auton.learning.service import ConversationLearning
from auton.learning.store import LearningStore


class ConversationLearningFactory:
    def create(self, config: LearningConfig, deps: LearningDependencies) -> LearningPort:
        return ConversationLearning(
            config,
            deps,
            LearningStore(config, deps.events, deps.runtime, deps.test_source, "learning"),
        )
