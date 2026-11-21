from dataclasses import dataclass

from auton.datasets.ports import DatasetPort
from auton.genome.ports import AssetReadPort
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class TrainingDependencies:
    datasets: DatasetPort
    assets: AssetReadPort
    events: EventLogPort
    runtime: RuntimeDependencies
    test_source: bool = False
