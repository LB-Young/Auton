from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from auton.agent.contracts import AgentConfig
from auton.assess.contracts import AssessConfig
from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.experience.contracts import ExperienceConfig
from auton.genome.contracts import GenomeConfig
from auton.judgment.config import JudgmentConfig
from auton.kernel.config import KernelConfig
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig
from auton.server.identity import ServerSettings
from auton.tools.config import ToolConfig


@pytest.fixture
def deps() -> RuntimeDependencies:
    return RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))


@pytest.fixture
def client(deps: RuntimeDependencies, tmp_path: Path) -> Iterator[TestClient]:
    app = ApplicationFactory().create(
        ApplicationConfig(
            assess=AssessConfig(directory=tmp_path / "assess"),
            kernel=KernelConfig(backend="memory"),
            tools=ToolConfig(directory=tmp_path / "tools"),
            experience=ExperienceConfig(directory=tmp_path / "experience"),
            agent=AgentConfig(directory=str(tmp_path / "agent")),
            genome=GenomeConfig(directory=tmp_path / "assets"),
            server=ServerSettings(identity_backend="memory"),
            profile="test",
            models=ModelConfig(backend="mock"),
            judgment=JudgmentConfig(backend="mock"),
            implementation="scripted",
            chunk_delay_seconds=0.001,
            allowed_origins=("http://testserver",),
        ),
        deps,
    )
    with TestClient(app, headers={"X-Auton-Client": "web", "Origin": "http://testserver"}) as value:
        value.get("/api/v1/bootstrap")
        yield value
