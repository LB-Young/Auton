from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ToolConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    directory: Path = Path(".auton_local/tools")
    read_only: bool = False
    max_file_bytes: int = Field(default=131072, ge=1024, le=262144)
    max_output_bytes: int = Field(default=16384, ge=1024, le=65536)
    process_timeout_seconds: float = Field(default=5, gt=0, le=30)
    mcp_enabled: bool = True
