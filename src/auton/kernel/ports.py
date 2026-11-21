from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

ConfigT = TypeVar("ConfigT", contravariant=True)
DependenciesT = TypeVar("DependenciesT", contravariant=True)
ServiceT = TypeVar("ServiceT", covariant=True)


class ModuleFactory(Protocol[ConfigT, DependenciesT, ServiceT]):
    def create(self, config: ConfigT, deps: DependenciesT) -> ServiceT: ...


class LifecycleHandle(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class RuntimeDependencies:
    now: Callable[[], datetime]
    new_id: Callable[[], str]


class ApplicationError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
