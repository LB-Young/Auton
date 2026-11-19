"""Module-owned namespace over the public versioned document storage capability."""

from auton.evolve.contracts import EvolutionConfig
from auton.kernel.documents import VersionedDocumentStore
from auton.kernel.documents import digest as digest
from auton.kernel.documents import key as key
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


class EvolutionStore(VersionedDocumentStore):
    def __init__(
        self,
        config: EvolutionConfig,
        events: EventLogPort,
        runtime: RuntimeDependencies,
        test: bool,
    ) -> None:
        super().__init__(config, events, runtime, test, "evolution")
