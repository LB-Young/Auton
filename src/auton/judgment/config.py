from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JudgmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backend: Literal["laya", "mock"] = "laya"
    directory: Path = Path("weights/laya-multilingual")
    revision: Literal["e333cb7c823cd1787276228260f56d02fbf5180b"] = (
        "e333cb7c823cd1787276228260f56d02fbf5180b"
    )
    application_enabled: bool = False
    device: Literal["cpu", "mps"] = "cpu"
    max_tokens: int = Field(default=1024, ge=128, le=1024)
    timeout_seconds: float = Field(default=90, gt=0, le=180)
    load_timeout_seconds: float = Field(default=120, gt=0, le=300)
