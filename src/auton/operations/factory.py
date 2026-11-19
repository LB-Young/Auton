from auton.kernel.documents import VersionedDocumentStore
from auton.operations.contracts import OperationsConfig
from auton.operations.dependencies import OperationsDependencies
from auton.operations.ports import SchedulerPort
from auton.operations.queue import JobQueueFactory
from auton.operations.service import Scheduler
from auton.operations.telemetry import RetentionPolicyFactory, TelemetryFactory


class SchedulerFactory:
    def create(self, config: OperationsConfig, deps: OperationsDependencies) -> SchedulerPort:
        store = VersionedDocumentStore(
            config,
            deps.events,
            deps.runtime,
            deps.test_source,
            "operations_observe" if config.observer_only else "operations",
        )
        queue = JobQueueFactory().create(config, deps, store)
        return Scheduler(
            config,
            deps,
            store,
            queue,
            TelemetryFactory().create(config, deps, store, queue),
            RetentionPolicyFactory().create(config, store),
        )
