from auton.delegation.contracts import DelegationConfig
from auton.delegation.integrator import ResultIntegratorFactory
from auton.delegation.ports import DelegationPort
from auton.delegation.roles import RoleFactory
from auton.delegation.service import Delegation, DelegationDependencies
from auton.delegation.store import DelegationStore
from auton.kernel.storage import EventLogPort


class DelegationFactory:
    def create(
        self, config: DelegationConfig, deps: DelegationDependencies, events: EventLogPort
    ) -> DelegationPort:
        return Delegation(
            config,
            deps,
            DelegationStore(config, events, deps.runtime),
            RoleFactory(),
            ResultIntegratorFactory().create(deps.tools),
        )
