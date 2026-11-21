from auton.kernel.documents import VersionedDocumentStore
from auton.release.adapters import GenomeReleaseFactory, ModelReleaseFactory
from auton.release.contracts import ReleaseConfig
from auton.release.dependencies import ReleaseDependencies
from auton.release.policy import RolloutPolicyFactory
from auton.release.ports import ReleasePort
from auton.release.service import Releases
from auton.release.sources import ReleaseSourceReader


class ReleaseFactory:
    def create(self, config: ReleaseConfig, deps: ReleaseDependencies) -> ReleasePort:
        return Releases(
            config,
            deps,
            VersionedDocumentStore(config, deps.events, deps.runtime, deps.test_source, "release"),
            ReleaseSourceReader(deps),
            RolloutPolicyFactory().create(config, deps),
            GenomeReleaseFactory().create(deps),
            ModelReleaseFactory().create(deps),
        )
