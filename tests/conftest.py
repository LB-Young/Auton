from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.kernel.config import KernelConfig
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig


@pytest.fixture
def deps() -> RuntimeDependencies:
    return RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))


@pytest.fixture
def client(deps: RuntimeDependencies) -> Iterator[TestClient]:
    app = ApplicationFactory().create(
        ApplicationConfig(
            kernel=KernelConfig(backend="memory"),
            profile="test",
            models=ModelConfig(backend="mock"),
            implementation="scripted",
            chunk_delay_seconds=0.001,
            allowed_origins=("http://testserver",),
        ),
        deps,
    )
    with TestClient(app, headers={"X-Auton-Client": "web", "Origin": "http://testserver"}) as value:
        value.get("/api/v1/bootstrap")
        yield value
