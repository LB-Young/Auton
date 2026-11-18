from auton.context.compression import CompressorFactory
from auton.context.contracts import ContextConfig
from auton.context.ports import ContextEnginePort
from auton.context.retrieval import RerankerFactory, RetrieverFactory
from auton.context.service import ContextDependencies, ContextEngine
from auton.context.tokenization import TokenCounterFactory


class ContextEngineFactory:
    def create(self, config: ContextConfig, deps: ContextDependencies) -> ContextEnginePort:
        return ContextEngine(
            config,
            deps,
            TokenCounterFactory().create(config.tokenizer_directory),
            RetrieverFactory().create(config),
            RerankerFactory().create(),
            CompressorFactory().create(),
        )
