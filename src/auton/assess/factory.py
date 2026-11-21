from auton.assess.checkers import CheckerFactory
from auton.assess.contracts import AssessConfig
from auton.assess.judge import JudgeFactory
from auton.assess.ports import AssessPort, EvalStorePort
from auton.assess.service import AssessDependencies, Assessment
from auton.assess.store import EvalStore
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


class EvalStoreFactory:
    def create(
        self, config: AssessConfig, events: EventLogPort, runtime: RuntimeDependencies
    ) -> EvalStorePort:
        return EvalStore(config, events, runtime)


class AssessFactory:
    def create(self, config: AssessConfig, deps: AssessDependencies) -> AssessPort:
        return Assessment(
            config,
            deps,
            EvalStoreFactory().create(config, deps.events, deps.runtime),
            CheckerFactory().create(deps.tools, deps.context),
            JudgeFactory().create(config, deps.models),
        )
