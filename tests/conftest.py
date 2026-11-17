from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.genome.contracts import GenomeConfig
from auton.judgment.config import JudgmentConfig
from auton.kernel.config import KernelConfig
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig
from auton.tools.config import ToolConfig


@pytest.fixture
def deps() -> RuntimeDependencies:
    return RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))


@pytest.fixture
def client(deps: RuntimeDependencies, tmp_path: Path) -> Iterator[TestClient]:
    app = ApplicationFactory().create(
        ApplicationConfig(
            kernel=KernelConfig(backend="memory"),
            tools=ToolConfig(directory=tmp_path / "tools"),
            genome=GenomeConfig(directory=tmp_path / "assets"),
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
