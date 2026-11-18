from auton.experience.contracts import ExperienceConfig
from auton.experience.ports import ExperiencePort, ProjectionPort
from auton.experience.projection import SQLiteProjection
from auton.experience.repository import CheckpointRepositoryFactory
from auton.experience.service import ExperienceDependencies, ExperienceService


class ProjectionFactory:
    def create(self, config: ExperienceConfig) -> ProjectionPort:
        return SQLiteProjection(config.directory)


class ExperienceFactory:
    def create(self, config: ExperienceConfig, deps: ExperienceDependencies) -> ExperiencePort:
        return ExperienceService(
            config,
            deps,
            ProjectionFactory().create(config),
            CheckpointRepositoryFactory().create(deps.events),
        )
