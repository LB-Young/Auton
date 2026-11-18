from pydantic import BaseModel, ConfigDict, Field

from auton.server.identity import ServerSettings


class ServerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    settings: ServerSettings = Field(default_factory=ServerSettings)
    profile: str
    allowed_origins: tuple[str, ...]
