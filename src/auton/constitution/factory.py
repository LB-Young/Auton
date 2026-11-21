from dataclasses import dataclass

from auton.constitution.config import ConstitutionConfig
from auton.constitution.control import ConstitutionService
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class ConstitutionDependencies:
    events: EventLogPort
    runtime: RuntimeDependencies


class ConstitutionFactory:
    def create(
        self,
        config: ConstitutionConfig,
        deps: ConstitutionDependencies,
    ) -> ConstitutionService:
        return ConstitutionService(config, deps.events, deps.runtime)
