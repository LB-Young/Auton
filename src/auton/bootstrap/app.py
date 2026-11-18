from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from auton.agent.factory import AgentRuntimeFactory
from auton.agent.service import AgentDependencies
from auton.bootstrap.config import ApplicationConfig, load_config
from auton.bootstrap.registry import module_catalog
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import LoggerFactory, Redactor, SecretStoreFactory
from auton.context.factory import ContextEngineFactory
from auton.context.service import ContextDependencies
from auton.demo.config import DemoConfig
from auton.demo.factory import DemoConversationFactory
from auton.demo.ports import ConversationPort
from auton.experience.factory import ExperienceFactory
from auton.experience.service import ExperienceDependencies
from auton.genome.factory import GenomeFactory
from auton.genome.service import GenomeDependencies
from auton.judgment.factory import JudgmentFactory
from auton.judgment.service import JudgmentDependencies
from auton.kernel.factory import ClockFactory, IdentifierFactory, KernelFactory
from auton.kernel.modules import resolve_modules
from auton.kernel.ports import LifecycleHandle, ModuleFactory, RuntimeDependencies
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies
from auton.server.commands import CommandHandlerFactory
from auton.server.config import ServerConfig
from auton.server.factory import ServerFactory
from auton.server.feedback import FeedbackFactory
from auton.server.identity import IdentityFactory
from auton.server.ports import ServerDependencies
from auton.server.uploads import UploadFactory
from auton.tools.factory import ToolHostFactory
from auton.tools.service import ToolDependencies


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
        judgment = JudgmentFactory().create(
            config.judgment, JudgmentDependencies(control, control, kernel.events, deps, models)
        )
        tools = ToolHostFactory().create(
            config.tools, ToolDependencies(control, control, control, kernel.events, deps)
        )
        genome = GenomeFactory().create(
            config.genome, GenomeDependencies(control, kernel.events, deps)
        )
        context = ContextEngineFactory().create(
            config.context, ContextDependencies(tools, genome, models, control, kernel.events, deps)
        )
        agent = AgentRuntimeFactory().create(
            config.agent,
            AgentDependencies(
                context, models, tools, judgment, genome, kernel.events, deps, control
            ),
        )
        experience = ExperienceFactory().create(
            config.experience, ExperienceDependencies(kernel.events, agent, genome, context, deps)
        )
        identity = IdentityFactory().create(config.server, deps)
        commands = CommandHandlerFactory().create(agent, experience)
        uploads = UploadFactory().create(config.server, genome, deps)
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
            [
                kernel,
                control,
                models,
                judgment,
                tools,
                genome,
                context,
                agent,
                experience,
                identity,
                commands,
                uploads,
                conversation,
            ]
            if conversation is not None
            else [
                kernel,
                control,
                models,
                judgment,
                tools,
                genome,
                context,
                agent,
                experience,
                identity,
                commands,
                uploads,
            ]
        )
        redactor = Redactor()
        return ServerFactory().create(
            ServerConfig(
                profile=config.profile,
                allowed_origins=config.allowed_origins,
                settings=config.server,
            ),
            ServerDependencies(
                conversation=conversation,
                modules=modules,
                implementation=config.implementation,
                lifespan=runtime.lifespan,
                is_ready=lambda: runtime.ready,
                storage=kernel.info,
                control=control,
                models=models,
                judgment=judgment,
                tools=tools,
                genome=genome,
                context=context,
                agent=agent,
                experience=experience,
                identity=identity,
                commands=commands,
                feedback=FeedbackFactory().create(agent, kernel.events, deps),
                uploads=uploads,
                events=kernel.events,
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
