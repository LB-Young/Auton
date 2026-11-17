from collections.abc import Callable

import httpx

from auton.constitution.secrets import SecretStorePort
from auton.model.config import ModelConfig
from auton.model.gateway import GatewayDependencies, ModelGateway
from auton.model.ports import ModelGatewayPort, ProviderPort
from auton.model.provider import DeepSeekProvider, MockProvider
from auton.model.registry import ModelRegistryFactory


class ProviderFactory:
    def create(
        self,
        config: ModelConfig,
        secrets: SecretStorePort,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> ProviderPort:
        if config.backend == "mock":
            return MockProvider()
        return DeepSeekProvider(
            config,
            secrets,
            client_factory
            or (
                lambda: httpx.AsyncClient(
                    timeout=httpx.Timeout(config.timeout_seconds, connect=10),
                    follow_redirects=False,
                )
            ),
        )


class ModelGatewayFactory:
    def create(self, config: ModelConfig, deps: GatewayDependencies) -> ModelGatewayPort:
        return ModelGateway(
            config,
            ModelRegistryFactory().create(config),
            ProviderFactory().create(config, deps.secrets),
            deps,
        )
