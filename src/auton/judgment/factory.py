from auton.judgment.adapter import LayaAdapter, MockJudgmentAdapter
from auton.judgment.config import JudgmentConfig
from auton.judgment.policy import RoutePolicyFactory
from auton.judgment.ports import JudgmentAdapterPort, JudgmentPort
from auton.judgment.service import JudgmentDependencies, JudgmentService


class LayaAdapterFactory:
    def create(self, config: JudgmentConfig) -> JudgmentAdapterPort:
        return LayaAdapter(config)


class JudgmentFactory:
    def create(self, config: JudgmentConfig, deps: JudgmentDependencies) -> JudgmentPort:
        adapter = (
            MockJudgmentAdapter(config)
            if config.backend == "mock"
            else LayaAdapterFactory().create(config)
        )
        return JudgmentService(
            adapter, RoutePolicyFactory().create(), deps, config.application_enabled
        )
