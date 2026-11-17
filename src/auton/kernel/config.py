from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KernelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backend: Literal["sqlite", "memory"] = "sqlite"
    data_directory: Path = Path(".auton_local")
    busy_timeout_ms: int = Field(default=1000, ge=0, le=30000)

    @property
    def event_path(self) -> Path:
        return self.data_directory / "kernel/events.sqlite3"
