from pydantic import BaseModel, ConfigDict, Field


class DemoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    implementation: str = "scripted"
    chunk_delay_seconds: float = Field(default=0.035, ge=0, le=2)
    max_sessions: int = Field(default=50, ge=1, le=200)
    max_messages: int = Field(default=100, ge=2, le=500)
