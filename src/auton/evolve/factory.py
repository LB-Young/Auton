import asyncio

from auton.evolve.arena import ArenaRunner
from auton.evolve.contracts import EvolutionConfig
from auton.evolve.dependencies import EvolutionDependencies
from auton.evolve.diagnosis import DiagnoserFactory
from auton.evolve.fields import OptimizableFieldFactory
from auton.evolve.gates import GateFactory
from auton.evolve.jobs import EvolutionJobs
from auton.evolve.mutation import MutationStrategyFactory
from auton.evolve.ports import EvolutionPort
from auton.evolve.service import Evolution
from auton.evolve.store import EvolutionStore
from auton.kernel.storage import EventLogPort


class EvolutionFactory:
    def create(
        self, config: EvolutionConfig, deps: EvolutionDependencies, events: EventLogPort
    ) -> EvolutionPort:
        lock, slots = asyncio.Lock(), EvolutionJobs(config.max_active_jobs)
        store = EvolutionStore(config, events, deps.runtime, deps.test_source)
        service = Evolution(
            config,
            deps,
            store,
            OptimizableFieldFactory().create(),
            DiagnoserFactory().create(),
            MutationStrategyFactory().create(config, deps.models),
            lock,
            slots,
        )
        service.runner = ArenaRunner(
            config, deps, store, GateFactory().create(), lock, slots, service.write_playbook
        )
        return service
