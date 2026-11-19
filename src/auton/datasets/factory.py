from auton.datasets.contracts import DatasetConfig
from auton.datasets.curation import DatasetCuratorFactory
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.groups import GroupLedger, GroupPolicyFactory
from auton.datasets.ports import DatasetPort
from auton.datasets.rendering import LearningRecordRenderer
from auton.datasets.service import Datasets
from auton.datasets.sources import DatasetSourceFactory
from auton.datasets.store import DatasetStore


class LineageStoreFactory:
    def create(self, config: DatasetConfig, deps: DatasetDependencies) -> DatasetStore:
        return DatasetStore(config, deps.events, deps.runtime, deps.test_source)


class ExporterFactory:
    def create(self) -> LearningRecordRenderer:
        return LearningRecordRenderer()


class DatasetPipelineFactory:
    def create(self, config: DatasetConfig, deps: DatasetDependencies) -> DatasetPort:
        store = LineageStoreFactory().create(config, deps)
        return Datasets(
            config,
            deps,
            store,
            DatasetSourceFactory().create(deps),
            GroupLedger(store, GroupPolicyFactory().create()),
            DatasetCuratorFactory(),
            ExporterFactory().create(),
        )
