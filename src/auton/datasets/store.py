from auton.datasets.contracts import DatasetConfig
from auton.kernel.documents import VersionedDocumentStore
from auton.kernel.documents import digest as digest
from auton.kernel.documents import key as key
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


class DatasetStore(VersionedDocumentStore):
    def __init__(
        self, config: DatasetConfig, events: EventLogPort, runtime: RuntimeDependencies, test: bool
    ) -> None:
        super().__init__(config, events, runtime, test, "datasets")
