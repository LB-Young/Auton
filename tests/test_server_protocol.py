import asyncio
import stat
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import SecretStr
from test_agent import agent as agent
from test_agent import command, create, result, wait
from test_context import USER
from test_context import context as context

from auton.agent.service import AgentRuntime
from auton.constitution.secrets import Redactor, StreamingRedactor
from auton.datasets.contracts import DatasetConfig
from auton.decision_review.contracts import DecisionReviewConfig
from auton.evolve.contracts import EvolutionConfig
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.model.contracts import ModelChunk, ModelRequest
from auton.server.commands import CommandHandler
from auton.server.identity import IdentityFactory, ServerSettings
from auton.server.run_events import EventStreamFactory, RunEventStream
from auton.training.contracts import TrainingConfig


async def test_identity_is_persistent_hashed_and_expires_without_silent_replacement(
    tmp_path: Path, deps: RuntimeDependencies
) -> None:
    now = datetime.now(UTC)
    clock = replace(deps, now=lambda: now)
    config = ServerSettings(directory=tmp_path, identity_ttl_seconds=60)
    first = IdentityFactory().create(config, clock)
    await first.start()
    token, info = await first.session("")
    owner = first.owner(token)
    assert owner != token and info.persistent and token not in info.model_dump_json()
    await first.close()
    assert stat.S_IMODE((tmp_path / "identity.sqlite3").stat().st_mode) == 0o600
    assert token.encode() not in (tmp_path / "identity.sqlite3").read_bytes()
    second = IdentityFactory().create(config, clock)
    await second.start()
    try:
        assert second.owner(token) == owner and second.info(token).identity_id == info.identity_id
        await second.revoke(token)
        with pytest.raises(ApplicationError):
            await second.session(token)
    finally:
        await second.close()
    expired = IdentityFactory().create(
        config, replace(clock, now=lambda: now + timedelta(seconds=61))
    )
    await expired.start()
    try:
        with pytest.raises(ApplicationError):
            expired.owner(token)
    finally:
        await expired.close()


@pytest.mark.parametrize("width", [1, 2, 7, 13, 40])
def test_streaming_redaction_keeps_split_credentials_out_of_deltas(width: int) -> None:
    credential = SecretStr("synthetic-stream-credential-123456789")
    stream = StreamingRedactor(Redactor((credential,)), (credential,))
    value = (
        "prefix " + credential.get_secret_value() + " and sk-syntheticfixturecredential and suffix"
    )
    chunks = [stream.feed(value[i : i + width]) for i in range(0, len(value), width)]
    chunks.append(stream.finish())
    text = "".join(chunks)
    assert credential.get_secret_value() not in text and "sk-syntheticfixturecredential" not in text
    assert text == Redactor((credential,)).text(value)


async def test_command_handler_survives_http_waiter_cancellation(agent: AgentRuntime) -> None:
    from auton.experience.ports import ExperiencePort

    handler = CommandHandler(agent, cast(ExperiencePort, object()))
    await handler.start()
    entered, release, completed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation() -> str:
        entered.set()
        await release.wait()
        completed.set()
        return "accepted"

    waiter = asyncio.create_task(handler.execute("stable-key", "digest", operation))
    await entered.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    await handler.close()
    assert completed.is_set() and not handler.active


async def test_transient_generation_is_not_a_persisted_result(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def stream(request: ModelRequest) -> AsyncGenerator[ModelChunk, None]:
        yield ModelChunk(kind="delta", content="UNPERSISTED_SEGMENT")
        entered.set()
        await release.wait()
        yield ModelChunk(
            kind="completed", result=result(request, "Final result with no eligible source.")
        )

    monkeypatch.setattr(agent.deps.models, "stream", stream)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)
    progress = await agent.transient(USER, run.id)
    assert progress and progress.text == "UNPERSISTED_SEGMENT" and not progress.persisted
    await command(agent, await agent.get(USER, run.id), "pause")
    assert await agent.transient(USER, run.id) is None
    release.set()
    paused = await wait(agent, run.id)
    assert paused.status == "paused"
    records = await agent.deps.events.read(limit=1000)
    assert all("UNPERSISTED_SEGMENT" not in r.event.canonical() for r in records)


async def test_slow_socket_is_closed_without_cancelling_agent(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auton.server.identity import IdentityPort

    entered, release = asyncio.Event(), asyncio.Event()

    async def stream(request: ModelRequest) -> AsyncGenerator[ModelChunk, None]:
        entered.set()
        await release.wait()
        yield ModelChunk(
            kind="completed", result=result(request, "Final report without eligible citations.")
        )

    monkeypatch.setattr(agent.deps.models, "stream", stream)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)

    class VerifiedIdentity:
        def owner(self, token: str) -> str:
            return USER.owner

    class SlowSocket:
        closed = False

        async def accept(self) -> None:
            pass

        async def send_json(self, value: object) -> None:
            await asyncio.Event().wait()

        async def receive(self) -> dict[str, str]:
            await asyncio.Event().wait()
            return {"type": "websocket.disconnect"}

        async def close(self, code: int = 1000) -> None:
            self.closed = True
            raise WebSocketDisconnect(code=1006)

    channel = EventStreamFactory().create(
        ServerSettings(identity_backend="memory", stream_send_timeout=0.1),
        agent,
        agent.deps.events,
        cast(IdentityPort, VerifiedIdentity()),
    )
    assert isinstance(channel, RunEventStream)
    socket = SlowSocket()
    await channel.connect(cast(WebSocket, socket), USER, "fixture", run.id, 0)
    assert socket.closed and not channel.active
    assert (await agent.get(USER, run.id)).status == "running"
    release.set()
    assert (await wait(agent, run.id)).status != "cancelled"


def test_upload_http_validation_isolation_and_idempotence(client: object) -> None:
    import hashlib

    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)
    assert (
        client.post("/api/v1/projects", json={"id": "upload", "title": "Uploads"}).status_code
        == 201
    )
    content = b"User provided notes\n"
    body = dict(
        request_id="upload-1",
        project_id="upload",
        filename="notes.md",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    prepared = client.post("/api/v1/uploads", json=body)
    assert prepared.status_code == 200
    intent = prepared.json()
    assert client.post("/api/v1/uploads", json=body).json() == intent
    assert (
        client.post("/api/v1/uploads", json={**body, "filename": "changed.md"}).status_code == 409
    )
    assert (
        client.post(
            "/api/v1/uploads", json={**body, "request_id": "big", "size_bytes": 131073}
        ).status_code
        == 413
    )
    path = "/api/v1/uploads/" + intent["id"] + "/content"
    assert client.post(path, content=b"wrong").status_code == 422
    receipt = client.post(path, content=content)
    assert receipt.status_code == 200 and receipt.json()["status"] == "candidate"
    state = client.get("/api/v1/projects/upload/assets").json()
    assert not state["assets"] and len(state["candidates"]) == 1
    assert client.post(path, content=content).json() == receipt.json()
    assert len(client.get("/api/v1/projects/upload/assets").json()["candidates"]) == 1
    client.cookies.clear()
    client.get("/api/v1/bootstrap")
    assert client.post(path, content=content).status_code == 404


async def test_upload_expiry_and_git_ack_loss(
    agent: AgentRuntime, tmp_path: Path, deps: RuntimeDependencies, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from auton.genome.ports import GenomePort
    from auton.server.uploads import UploadCommand, UploadService

    assets = cast(GenomePort, agent.deps.assets)
    now = deps.now()
    service = UploadService(
        ServerSettings(directory=tmp_path / "uploads", upload_ttl_seconds=1),
        assets,
        replace(deps, now=lambda: now),
    )
    await service.start()
    content = b"Imported user document."
    body = UploadCommand(
        request_id="ack",
        project_id="project",
        filename="notes.md",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    try:
        intent = await service.prepare(USER, body)
        service.runtime = replace(deps, now=lambda: now + timedelta(seconds=2))
        with pytest.raises(ApplicationError) as error:
            await service.complete(USER, intent.id, content)
        assert error.value.status == 410
        service.runtime = replace(deps, now=lambda: now)
        original = assets.propose
        count = 0

        async def lost_ack(*args: object, **kwargs: object) -> object:
            nonlocal count
            count += 1
            await original(*args, **kwargs)  # type: ignore[arg-type]
            raise ApplicationError(503, "ack_lost", "Git committed but acknowledgement was lost")

        monkeypatch.setattr(assets, "propose", lost_ack)
        receipt = await service.complete(USER, intent.id, content)
        assert count == 1
    finally:
        await service.close()
    restarted = UploadService(service.config, assets, service.runtime)
    await restarted.start()
    try:
        assert await restarted.complete(USER, intent.id, content) == receipt
        assert count == 1
    finally:
        await restarted.close()


def test_run_websocket_replay_reset_and_ownership(client: object) -> None:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    assert isinstance(client, TestClient)
    client.post("/api/v1/projects", json={"id": "events", "title": "Events"})
    client.post("/api/v1/tools/workspaces", json={"id": "events", "title": "Events"})
    run = client.post(
        "/api/v1/agent/runs",
        json=create(project_id="events", workspace_id="events").model_dump(mode="json"),
    ).json()
    path = "/api/v1/agent/runs/" + run["id"]
    state = client.get(path + "/snapshot").json()
    assert state["cursor"] > 0 and state["run"]["id"] == run["id"]
    with client.websocket_connect(
        path + "/events?after=0", headers={"Origin": "http://testserver"}
    ) as ws:
        anchor = ws.receive_json()
        assert anchor["kind"] == "snapshot" and anchor["persisted"]
        event = ws.receive_json()
        assert event["kind"] == "checkpoint" and "payload" not in event
    # Disconnecting a reader never sends a cancel command.
    assert client.get(path).json()["status"] != "cancelled"
    with client.websocket_connect(
        path + "/events?after=999999", headers={"Origin": "http://testserver"}
    ) as ws:
        assert ws.receive_json()["kind"] == "reset_required"
        assert ws.receive_json()["kind"] == "snapshot"
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(path + "/events", headers={"Origin": "https://evil.example"}),
    ):
        pytest.fail("Cross-origin socket was accepted")
    client.cookies.clear()
    client.get("/api/v1/bootstrap")
    assert client.get(path + "/snapshot").status_code == 404
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(path + "/events", headers={"Origin": "http://testserver"}),
    ):
        pytest.fail("Cross-owner socket was accepted")


def test_persistent_http_identity_and_upload_survive_application_restart(
    tmp_path: Path, deps: RuntimeDependencies
) -> None:
    import hashlib

    from fastapi.testclient import TestClient

    from auton.agent.contracts import AgentConfig
    from auton.assess.contracts import AssessConfig
    from auton.bootstrap.app import ApplicationFactory
    from auton.bootstrap.config import ApplicationConfig
    from auton.delegation.contracts import DelegationConfig
    from auton.experience.contracts import ExperienceConfig
    from auton.genome.contracts import GenomeConfig
    from auton.judgment.config import JudgmentConfig
    from auton.kernel.config import KernelConfig
    from auton.model.config import ModelConfig
    from auton.tools.config import ToolConfig

    config = ApplicationConfig(
        datasets=DatasetConfig(directory=tmp_path / "datasets"),
        training=TrainingConfig(directory=tmp_path / "training"),
        decision_review=DecisionReviewConfig(directory=tmp_path / "decision-review"),
        evolve=EvolutionConfig(directory=tmp_path / "evolve"),
        delegation=DelegationConfig(directory=tmp_path / "delegation"),
        assess=AssessConfig(directory=tmp_path / "assess"),
        profile="test",
        kernel=KernelConfig(data_directory=tmp_path / "events"),
        server=ServerSettings(directory=tmp_path / "server"),
        genome=GenomeConfig(directory=tmp_path / "assets"),
        agent=AgentConfig(directory=str(tmp_path / "agent")),
        tools=ToolConfig(directory=tmp_path / "tools"),
        experience=ExperienceConfig(directory=tmp_path / "experience"),
        models=ModelConfig(backend="mock"),
        judgment=JudgmentConfig(backend="mock"),
        allowed_origins=("http://testserver",),
    )
    headers = {"Origin": "http://testserver", "X-Auton-Client": "web"}
    with TestClient(ApplicationFactory().create(config, deps), headers=headers) as first:
        info = first.get("/api/v1/bootstrap").json()["identity"]
        token = first.cookies.get("auton_owner")
        first.post("/api/v1/projects", json={"id": "persistent", "title": "Persistent"})
        content = b"Persistent upload."
        body = dict(
            request_id="persist-upload",
            project_id="persistent",
            filename="notes.md",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        intent = first.post("/api/v1/uploads", json=body).json()
    with TestClient(
        ApplicationFactory().create(config, deps),
        headers={**headers, "Cookie": f"auton_owner={token}"},
    ) as second:
        assert (
            second.get("/api/v1/bootstrap").json()["identity"]["identity_id"] == info["identity_id"]
        )
        assert second.get("/api/v1/projects").json()[0]["id"] == "persistent"
        receipt = second.post("/api/v1/uploads/" + intent["id"] + "/content", content=content)
        assert receipt.status_code == 200
        assert second.get("/api/v1/projects/persistent/assets").json()["candidates"]


def test_expired_cookie_bootstrap_and_explicit_reset(client: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)
    assert (
        client.get("/api/v1/bootstrap", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    client.cookies.clear()
    client.cookies.set("auton_owner", "x" * 43)
    assert client.get("/api/v1/bootstrap").status_code == 401
    assert (
        client.post("/api/v1/identity/adopt-legacy", json={"project_id": "unknown"}).status_code
        == 409
    )
    assert client.post("/api/v1/identity/reset", json={"request_id": "reset"}).status_code == 200
    assert client.get("/api/v1/bootstrap").status_code == 200
    assert client.post("/api/v1/sessions", content=b"x" * 2097153).status_code == 413
    assert client.post("/api/v1/sessions", content=iter([b"x" * 1048576] * 3)).status_code == 413


async def test_legacy_identity_rotation_is_persistent_and_cannot_be_repeated(
    tmp_path: Path, deps: RuntimeDependencies
) -> None:
    from secrets import token_urlsafe

    config = ServerSettings(directory=tmp_path)
    service = IdentityFactory().create(config, deps)
    await service.start()
    legacy = token_urlsafe(32)
    try:
        replacement, info = await service.adopt_legacy(legacy)
        assert replacement != legacy and service.owner(replacement) == legacy
        assert replacement.encode() not in (tmp_path / "identity.sqlite3").read_bytes()
        with pytest.raises(ApplicationError):
            service.owner(legacy)
        with pytest.raises(ApplicationError):
            await service.adopt_legacy(legacy)
    finally:
        await service.close()
    restarted = IdentityFactory().create(config, deps)
    await restarted.start()
    try:
        assert restarted.owner(replacement) == legacy
        assert restarted.info(replacement).identity_id == info.identity_id
        with pytest.raises(ApplicationError):
            await restarted.adopt_legacy(legacy)
    finally:
        await restarted.close()


async def test_graceful_shutdown_waits_for_result_and_pauses_instead_of_cancelling(
    agent: AgentRuntime, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()

    async def stream(request: ModelRequest) -> AsyncGenerator[ModelChunk, None]:
        entered.set()
        await release.wait()
        yield ModelChunk(
            kind="completed", result=result(request, "Observed but not adopted after shutdown.")
        )

    monkeypatch.setattr(agent.deps.models, "stream", stream)
    run = await agent.create(USER, create())
    await asyncio.wait_for(entered.wait(), 10)
    shutdown = asyncio.create_task(agent.close())
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    await asyncio.wait_for(shutdown, 10)
    await agent.start()
    state = await agent.get(USER, run.id)
    assert state.status == "paused" and state.model_results and not state.stop_requested
    assert not state.final_text
