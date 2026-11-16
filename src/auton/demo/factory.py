from auton.demo.config import DemoConfig
from auton.demo.ports import ConversationPort, Responder
from auton.demo.service import DemoConversationService, EchoResponder, ScriptedResponder
from auton.kernel.ports import RuntimeDependencies


class DemoConversationFactory:
    def create(self, config: DemoConfig, deps: RuntimeDependencies) -> ConversationPort:
        implementations: dict[str, type[Responder]] = {
            "echo": EchoResponder,
            "scripted": ScriptedResponder,
        }
        responder = implementations.get(config.implementation)
        if responder is None:
            raise ValueError(f"Unknown demo implementation: {config.implementation}")
        return DemoConversationService(config, deps, responder())
