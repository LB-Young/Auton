from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from auton.kernel.config import KernelConfig
from auton.kernel.events import Event, StorageInfo
from auton.kernel.memory import MemoryEventLog
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.sqlite import SQLiteEventLog
from auton.kernel.storage import EventLogPort


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class IdentifierPort(Protocol):
    def new_id(self) -> str: ...


class UUIDIdentifiers:
    def new_id(self) -> str:
        return str(uuid4())


class IdentifierFactory:
    def create(self, implementation: str = "uuid") -> IdentifierPort:
        if implementation != "uuid":
            raise ValueError("Unknown identifier implementation")
        return UUIDIdentifiers()


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class FixedClock:
    value: datetime

    def now(self) -> datetime:
        return self.value


class ClockFactory:
    def create(self, implementation: str = "system", fixed_at: datetime | None = None) -> ClockPort:
        if implementation == "system" and fixed_at is None:
            return SystemClock()
        if implementation == "fixed" and fixed_at is not None and fixed_at.tzinfo is not None:
            return FixedClock(fixed_at)
        raise ValueError("Unknown or invalid clock configuration")


class EventLogFactory:
    def create(self, config: KernelConfig) -> EventLogPort:
        if config.backend == "sqlite":
            return SQLiteEventLog(config)
        return MemoryEventLog()


@dataclass(frozen=True)
class KernelRuntime:
    events: EventLogPort
    dependencies: RuntimeDependencies

    async def start(self) -> None:
        await self.events.start()
        await self.events.append(
            [
                Event(
                    event_id=self.dependencies.new_id(),
                    kind="kernel.started",
                    timestamp=self.dependencies.now(),
                    source="system",
                    payload={"backend": self.events.info().backend},
                )
            ]
        )

    async def close(self) -> None:
        await self.events.close()

    def info(self) -> StorageInfo:
        return self.events.info()


class KernelFactory:
    def create(self, config: KernelConfig, deps: RuntimeDependencies) -> KernelRuntime:
        return KernelRuntime(EventLogFactory().create(config), deps)
