from pydantic import BaseModel, ConfigDict


class ServerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    profile: str
    allowed_origins: tuple[str, ...]
