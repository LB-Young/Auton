from auton.genome.contracts import GenomeConfig
from auton.genome.policy import MemoryPolicyFactory
from auton.genome.ports import GenomePort
from auton.genome.repository import AssetRepositoryFactory
from auton.genome.service import GenomeDependencies, GenomeService, ResolverFactory


class GenomeFactory:
    def create(self, config: GenomeConfig, deps: GenomeDependencies) -> GenomePort:
        repository = AssetRepositoryFactory().create(config)
        policy = MemoryPolicyFactory().create()
        return GenomeService(
            repository, policy, ResolverFactory().create(repository, policy, deps), deps
        )
