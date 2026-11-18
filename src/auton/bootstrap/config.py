import os
import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from auton.agent.contracts import AgentConfig
from auton.constitution.config import ConstitutionConfig
from auton.context.contracts import ContextConfig
from auton.experience.contracts import ExperienceConfig
from auton.genome.contracts import GenomeConfig
from auton.judgment.config import JudgmentConfig
from auton.kernel.config import KernelConfig
from auton.model.config import ModelConfig
from auton.tools.config import ToolConfig


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    experience: ExperienceConfig = Field(default_factory=ExperienceConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    constitution: ConstitutionConfig = Field(default_factory=ConstitutionConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    genome: GenomeConfig = Field(default_factory=GenomeConfig)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    judgment: JudgmentConfig = Field(default_factory=JudgmentConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    kernel: KernelConfig = Field(default_factory=KernelConfig)
    profile: Literal["demo", "test", "dev", "production"] = "demo"
    implementation: str = "scripted"
    chunk_delay_seconds: float = Field(default=0.035, ge=0, le=2)
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    )

    @model_validator(mode="after")
    def validate_profile(self) -> "ApplicationConfig":
        if self.judgment.backend == "mock" and self.profile != "test":
            raise ValueError("Mock judgment is test-only")
        if self.profile == "test" and self.judgment.backend != "mock":
            raise ValueError("Test profile requires explicit mock judgment")
        if self.models.backend == "mock" and self.profile != "test":
            raise ValueError("Mock model is test-only")
        if self.profile == "test" and self.models.backend != "mock":
            raise ValueError("Test profile requires explicit mock models")
        if self.kernel.backend == "memory" and self.profile != "test":
            raise ValueError("Memory event storage is test-only")
        if self.profile in {"dev", "production"} and self.implementation != "disabled":
            raise ValueError("Non-demo profiles must use implementation=disabled in M01")
        if self.profile in {"demo", "test"} and self.implementation not in {"echo", "scripted"}:
            raise ValueError("Demo implementation must be echo or scripted")
        if not self.allowed_origins:
            raise ValueError("At least one explicit origin is required")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"localhost", "127.0.0.1", "testserver"}
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("M01 accepts explicit local origins only")
        return self


def load_config() -> ApplicationConfig:
    configured = os.environ.get("AUTON_CONFIG")
    path = (
        Path(configured) if configured else Path(__file__).resolve().parents[3] / "config/demo.toml"
    )
    with path.open("rb") as handle:
        return ApplicationConfig.model_validate(tomllib.load(handle))
