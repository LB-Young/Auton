from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from auton.bootstrap.config import ApplicationConfig, load_config
from auton.bootstrap.registry import module_catalog
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import LoggerFactory, Redactor, SecretStoreFactory
from auton.demo.config import DemoConfig
from auton.demo.factory import DemoConversationFactory
from auton.demo.ports import ConversationPort
from auton.kernel.factory import ClockFactory, IdentifierFactory, KernelFactory
from auton.kernel.modules import resolve_modules
from auton.kernel.ports import LifecycleHandle, ModuleFactory, RuntimeDependencies
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies
from auton.server.config import ServerConfig
from auton.server.factory import ServerFactory
from auton.server.ports import ServerDependencies


class ApplicationRuntime:
    def __init__(self, resources: list[LifecycleHandle]) -> None:
        self.resources = resources
        self.ready = False

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            try:
                for resource in self.resources:
                    # Register cleanup before start to handle partially started resources.
                    stack.push_async_callback(resource.close)
                    await resource.start()
                self.ready = True
                yield
            finally:
                self.ready = False


class ApplicationFactory:
    def create(self, config: ApplicationConfig, deps: RuntimeDependencies) -> FastAPI:
        enabled = config.profile in {"demo", "test"}
        modules = module_catalog(enabled)
        resolve_modules(modules)
        kernel = KernelFactory().create(config.kernel, deps)
        control = ConstitutionFactory().create(
            config.constitution, ConstitutionDependencies(kernel.events, deps)
        )
        models = ModelGatewayFactory().create(
            config.models,
            GatewayDependencies(control, kernel.events, deps, SecretStoreFactory().create()),
        )
        conversation: ConversationPort | None = None
        factory: ModuleFactory[DemoConfig, RuntimeDependencies, ConversationPort]
        factory = DemoConversationFactory()
        if enabled:
            conversation = factory.create(
                DemoConfig(
                    implementation=config.implementation,
                    chunk_delay_seconds=config.chunk_delay_seconds,
                ),
                deps,
            )
        runtime = ApplicationRuntime(
            [kernel, control, models, conversation]
            if conversation is not None
            else [kernel, control, models]
        )
        redactor = Redactor()
        return ServerFactory().create(
            ServerConfig(profile=config.profile, allowed_origins=config.allowed_origins),
            ServerDependencies(
                conversation=conversation,
                modules=modules,
                implementation=config.implementation,
                lifespan=runtime.lifespan,
                is_ready=lambda: runtime.ready,
                storage=kernel.info,
                control=control,
                models=models,
                redact=redactor.text,
                logger=LoggerFactory().create(redactor),
            ),
        )


def create_app() -> FastAPI:
    return ApplicationFactory().create(
        load_config(),
        RuntimeDependencies(
            now=ClockFactory().create().now, new_id=IdentifierFactory().create().new_id
        ),
    )
