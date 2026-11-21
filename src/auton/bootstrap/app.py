from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from auton.agent.contracts import RunLimits
from auton.agent.factory import AgentRuntimeFactory
from auton.agent.service import AgentDependencies
from auton.assess.factory import AssessFactory
from auton.assess.service import AssessDependencies
from auton.bootstrap.config import ApplicationConfig, load_config
from auton.bootstrap.registry import module_catalog
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import LoggerFactory, Redactor, SecretStoreFactory
from auton.context.factory import ContextEngineFactory
from auton.context.service import ContextDependencies
from auton.conversation.factory import WorkspaceConversationFactory
from auton.conversation.service import ConversationDependencies
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.factory import DatasetPipelineFactory
from auton.decision_review.dependencies import ReviewDependencies
from auton.decision_review.factory import DecisionReviewFactory
from auton.delegation.factory import DelegationFactory
from auton.delegation.service import DelegationDependencies
from auton.demo.config import DemoConfig
from auton.demo.factory import DemoConversationFactory
from auton.demo.ports import ConversationPort
from auton.evolve.dependencies import EvolutionDependencies
from auton.evolve.factory import EvolutionFactory
from auton.experience.factory import ExperienceFactory
from auton.experience.service import ExperienceDependencies
from auton.genome.factory import GenomeFactory
from auton.genome.service import GenomeDependencies
from auton.judgment.factory import JudgmentFactory
from auton.judgment.service import JudgmentDependencies
from auton.kernel.config import KernelConfig
from auton.kernel.factory import ClockFactory, IdentifierFactory, KernelFactory
from auton.kernel.modules import resolve_modules
from auton.kernel.ports import LifecycleHandle, ModuleFactory, RuntimeDependencies
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies
from auton.model.publications import ModelPublications
from auton.operations.dependencies import OperationsDependencies
from auton.operations.factory import SchedulerFactory
from auton.release.dependencies import ReleaseDependencies
from auton.release.factory import ReleaseFactory
from auton.server.commands import CommandHandlerFactory
from auton.server.config import ServerConfig
from auton.server.factory import ServerFactory
from auton.server.feedback import FeedbackFactory
from auton.server.identity import IdentityFactory
from auton.server.ports import ServerDependencies
from auton.server.uploads import UploadFactory
from auton.tools.factory import ToolHostFactory
from auton.tools.service import ToolDependencies
from auton.training.decision_evaluation import DecisionEvaluationDependencies
from auton.training.decision_factory import DecisionTrainingFactory
from auton.training.dependencies import TrainingDependencies
from auton.training.factory import ExecutorTrainingFactory


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
        model_publications = ModelPublications(
            config.kernel.data_directory / "model-publications",
            kernel.events,
            deps,
            bool(config.models.local_targets),
            config.profile == "test",
        )
        models = ModelGatewayFactory().create(
            config.models,
            GatewayDependencies(control, kernel.events, deps, SecretStoreFactory().create()),
            model_publications,
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
        workspace_conversations = WorkspaceConversationFactory().create(
            ConversationDependencies(agent, genome, tools, models, kernel.events, deps)
        )
        experience = ExperienceFactory().create(
            config.experience, ExperienceDependencies(kernel.events, agent, genome, context, deps)
        )
        judge_kernel = KernelFactory().create(
            KernelConfig(
                backend=config.kernel.backend,
                data_directory=config.assess.directory / "judge-journal",
            ),
            deps,
        )
        judge_models = ModelGatewayFactory().create(
            config.models,
            GatewayDependencies(control, judge_kernel.events, deps, SecretStoreFactory().create()),
        )
        assess = AssessFactory().create(
            config.assess,
            AssessDependencies(agent, tools, context, judge_models, kernel.events, deps, True),
        )
        delegation = DelegationFactory().create(
            config.delegation,
            DelegationDependencies(
                agent,
                tools,
                assess,
                genome,
                deps,
                RunLimits.model_validate(
                    config.agent.model_dump(include=set(RunLimits.model_fields))
                ),
                models,
                config.models.backend == "mock",
            ),
            kernel.events,
        )
        evolve = EvolutionFactory().create(
            config.evolve,
            EvolutionDependencies(
                genome,
                genome,
                genome,
                assess,
                models,
                agent,
                tools,
                context,
                deps,
                RunLimits.model_validate(
                    config.agent.model_dump(include=set(RunLimits.model_fields))
                ),
                config.models.backend == "mock",
            ),
            kernel.events,
        )
        review_kernel = KernelFactory().create(
            KernelConfig(
                backend=config.kernel.backend,
                data_directory=config.decision_review.directory / "reviewer-journal",
            ),
            deps,
        )
        review_models = ModelGatewayFactory().create(
            config.models,
            GatewayDependencies(control, review_kernel.events, deps, SecretStoreFactory().create()),
        )
        decision_review = DecisionReviewFactory().create(
            config.decision_review,
            ReviewDependencies(
                agent,
                assess,
                experience,
                genome,
                review_models,
                kernel.events,
                deps,
                config.models.backend == "mock",
                delegation=delegation,
            ),
        )
        datasets = DatasetPipelineFactory().create(
            config.datasets,
            DatasetDependencies(
                agent,
                assess,
                genome,
                context,
                decision_review,
                evolve,
                delegation,
                kernel.events,
                deps,
                config.models.backend == "mock",
            ),
        )
        training = ExecutorTrainingFactory().create(
            config.training,
            TrainingDependencies(
                datasets, genome, kernel.events, deps, config.models.backend == "mock"
            ),
        )
        decision_training = DecisionTrainingFactory().create(
            config.decision_training,
            TrainingDependencies(
                datasets, genome, kernel.events, deps, config.models.backend == "mock"
            ),
            DecisionEvaluationDependencies(agent, assess),
        )
        release = ReleaseFactory().create(
            config.release,
            ReleaseDependencies(
                genome,
                genome,
                model_publications,
                agent,
                assess,
                evolve,
                training,
                decision_training,
                kernel.events,
                deps,
                tools,
                SecretStoreFactory().create(),
                config.models.local_targets,
                config.profile == "test",
            ),
        )
        model_publications.bind_guard(release.verify_runtime_source)
        genome.bind_release_guard(release.verify_runtime_source)
        operations = SchedulerFactory().create(
            config.operations,
            OperationsDependencies(
                genome,
                agent,
                assess,
                decision_review,
                datasets,
                training,
                decision_training,
                kernel.events,
                deps,
                2 * config.decision_review.max_stage_cost_microusd,
                config.profile == "test",
            ),
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
                model_publications,
                models,
                judgment,
                tools,
                genome,
                context,
                agent,
                workspace_conversations,
                experience,
                judge_kernel,
                judge_models,
                assess,
                delegation,
                evolve,
                review_kernel,
                review_models,
                decision_review,
                datasets,
                training,
                decision_training,
                release,
                operations,
                identity,
                commands,
                uploads,
                conversation,
            ]
            if conversation is not None
            else [
                kernel,
                control,
                model_publications,
                models,
                judgment,
                tools,
                genome,
                context,
                agent,
                workspace_conversations,
                experience,
                judge_kernel,
                judge_models,
                assess,
                delegation,
                evolve,
                review_kernel,
                review_models,
                decision_review,
                datasets,
                training,
                decision_training,
                release,
                operations,
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
                conversations=workspace_conversations,
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
                assess=assess,
                delegation=delegation,
                evolve=evolve,
                decision_review=decision_review,
                datasets=datasets,
                training=training,
                decision_training=decision_training,
                release=release,
                operations=operations,
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
