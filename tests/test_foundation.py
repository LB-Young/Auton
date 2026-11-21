from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from auton.agent.contracts import AgentConfig
from auton.assess.contracts import AssessConfig
from auton.bootstrap.app import ApplicationFactory, ApplicationRuntime
from auton.bootstrap.config import ApplicationConfig
from auton.datasets.contracts import DatasetConfig
from auton.decision_review.contracts import DecisionReviewConfig
from auton.delegation.contracts import DelegationConfig
from auton.demo.config import DemoConfig
from auton.demo.factory import DemoConversationFactory
from auton.demo.ports import ConversationPort
from auton.evolve.contracts import EvolutionConfig
from auton.experience.contracts import ExperienceConfig
from auton.genome.contracts import GenomeConfig
from auton.judgment.config import JudgmentConfig
from auton.kernel.config import KernelConfig
from auton.kernel.modules import ModuleDescriptor, resolve_modules
from auton.kernel.ports import ModuleFactory, RuntimeDependencies
from auton.learning.contracts import LearningConfig
from auton.model.config import ModelConfig
from auton.operations.contracts import OperationsConfig
from auton.release.contracts import ReleaseConfig
from auton.server.identity import ServerSettings
from auton.tools.config import ToolConfig
from auton.training.contracts import DecisionTrainingConfig, TrainingConfig


@pytest.mark.parametrize("implementation", ["echo", "scripted"])
def test_factory_swap_has_identical_http_and_event_contract(
    implementation: str, deps: RuntimeDependencies, tmp_path: Path
) -> None:
    app = ApplicationFactory().create(
        ApplicationConfig(
            agent=AgentConfig(directory=str(tmp_path / "agent")),
            tools=ToolConfig(directory=tmp_path / "tools"),
            genome=GenomeConfig(directory=tmp_path / "genome"),
            experience=ExperienceConfig(directory=tmp_path / "experience"),
            datasets=DatasetConfig(directory=tmp_path / "datasets"),
            learning=LearningConfig(directory=tmp_path / "learning", background=False),
            training=TrainingConfig(directory=tmp_path / "training"),
            release=ReleaseConfig(directory=tmp_path / "release"),
            operations=OperationsConfig(directory=tmp_path / "operations"),
            decision_training=DecisionTrainingConfig(directory=tmp_path / "decision-training"),
            decision_review=DecisionReviewConfig(directory=tmp_path / "decision-review"),
            evolve=EvolutionConfig(directory=tmp_path / "evolve"),
            delegation=DelegationConfig(directory=tmp_path / "delegation"),
            assess=AssessConfig(directory=tmp_path / "assess"),
            kernel=KernelConfig(backend="memory"),
            server=ServerSettings(identity_backend="memory"),
            profile="test",
            models=ModelConfig(backend="mock"),
            judgment=JudgmentConfig(backend="mock"),
            implementation=implementation,
            chunk_delay_seconds=0,
            allowed_origins=("http://testserver",),
        ),
        deps,
    )
    with TestClient(
        app, headers={"X-Auton-Client": "web", "Origin": "http://testserver"}
    ) as client:
        assert client.get("/api/v1/health").json()["status"] == "ready"
        assert client.get("/api/v1/bootstrap").json()["implementation"] == implementation
        session = client.post("/api/v1/sessions", json={"request_id": "create"}).json()
        with client.websocket_connect(
            f"/api/v1/sessions/{session['id']}/events", headers={"Origin": "http://testserver"}
        ) as ws:
            assert ws.receive_json()["payload"]["status"] == "idle"
            reply = client.post(
                f"/api/v1/sessions/{session['id']}/messages",
                json={"request_id": "send", "content": "模块化开发"},
            )
            assert reply.status_code == 202
            for _ in range(200):
                event = ws.receive_json()
                assert event["schema_version"] == "1"
                assert event["payload"]["source"] == "demo"
                if event["payload"]["status"] == "completed":
                    break
            else:
                pytest.fail("No terminal event")
            assert "模块化开发" in event["payload"]["messages"][-1]["content"]
            assert event["payload"]["artifacts"][0]["source"] == "demo"


def test_factory_does_not_start_resources_and_rejects_unknown(deps: RuntimeDependencies) -> None:
    factory: ModuleFactory[DemoConfig, RuntimeDependencies, ConversationPort]
    factory = DemoConversationFactory()
    service = factory.create(DemoConfig(), deps)
    with pytest.raises(Exception, match="尚未启动"):
        service.list_sessions("owner")
    with pytest.raises(ValueError, match="Unknown"):
        factory.create(DemoConfig(implementation="arbitrary.module"), deps)


@pytest.mark.parametrize(
    "config",
    [
        {"profile": "production", "implementation": "echo"},
        {"implementation": "unknown"},
        {"allowed_origins": ["*"]},
        {"allowed_origins": ["https://evil.example"]},
        {"unexpected": "ignored?"},
    ],
)
def test_invalid_configuration_is_rejected(config: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ApplicationConfig.model_validate(config)


def test_real_profile_never_uses_demo(deps: RuntimeDependencies, tmp_path: Path) -> None:
    app = ApplicationFactory().create(
        ApplicationConfig(
            agent=AgentConfig(directory=str(tmp_path / "agent")),
            tools=ToolConfig(directory=tmp_path / "tools"),
            genome=GenomeConfig(directory=tmp_path / "genome"),
            experience=ExperienceConfig(directory=tmp_path / "experience"),
            datasets=DatasetConfig(directory=tmp_path / "datasets"),
            learning=LearningConfig(directory=tmp_path / "learning", background=False),
            training=TrainingConfig(directory=tmp_path / "training"),
            release=ReleaseConfig(directory=tmp_path / "release"),
            operations=OperationsConfig(directory=tmp_path / "operations"),
            decision_training=DecisionTrainingConfig(directory=tmp_path / "decision-training"),
            decision_review=DecisionReviewConfig(directory=tmp_path / "decision-review"),
            evolve=EvolutionConfig(directory=tmp_path / "evolve"),
            delegation=DelegationConfig(directory=tmp_path / "delegation"),
            assess=AssessConfig(directory=tmp_path / "assess"),
            server=ServerSettings(directory=tmp_path / "server"),
            profile="production",
            implementation="disabled",
            kernel=KernelConfig(data_directory=tmp_path),
        ),
        deps,
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/bootstrap").json()["demo"] is False
        result = client.post("/api/v1/sessions", json={"request_id": "not-demo"})
        assert result.status_code == 501
        assert result.json()["code"] == "not_implemented"


def test_module_graph_rejects_missing_cycle_and_duplicates() -> None:
    a = ModuleDescriptor(id="a", title="A", milestone="M01", status="ready", provides=("a",))
    b = ModuleDescriptor(
        id="b", title="B", milestone="M01", status="ready", provides=("b",), requires=("a",)
    )
    assert resolve_modules([b, a]) == ["a", "b"]
    with pytest.raises(ValueError, match="missing"):
        resolve_modules([b])
    with pytest.raises(ValueError, match="cycle"):
        resolve_modules([a.model_copy(update={"requires": ("b",)}), b])
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_modules([a, a])


async def test_startup_failure_closes_partial_resources_and_never_reports_ready() -> None:
    closed: list[str] = []

    class Resource:
        def __init__(self, name: str, fail: bool = False) -> None:
            self.name, self.fail = name, fail

        async def start(self) -> None:
            if self.fail:
                raise RuntimeError("startup failure")

        async def close(self) -> None:
            closed.append(self.name)

    runtime = ApplicationRuntime([Resource("first"), Resource("partial", True)])
    with pytest.raises(RuntimeError, match="startup failure"):
        async with runtime.lifespan(FastAPI()):
            pytest.fail("Failed startup must not yield")
    assert not runtime.ready
    assert closed == ["partial", "first"]


def test_clock_and_identifier_dependencies_are_explicit() -> None:
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    deps = RuntimeDependencies(now=lambda: fixed, new_id=lambda: "deterministic-id")
    assert deps.now() == fixed
