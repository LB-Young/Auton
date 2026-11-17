import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from auton.demo.config import DemoConfig
from auton.demo.factory import DemoConversationFactory
from auton.demo.ports import CreateSession, SendMessage, StopRun
from auton.kernel.ports import RuntimeDependencies


def test_command_deduplication_conflicts_and_stale_stop(client: TestClient) -> None:
    session = client.post("/api/v1/sessions", json={"request_id": "create"}).json()
    assert (
        client.post("/api/v1/sessions", json={"request_id": "create"}).json()["id"] == session["id"]
    )
    path = f"/api/v1/sessions/{session['id']}"
    command = {"request_id": "send", "content": "test"}
    first = client.post(path + "/messages", json=command).json()
    again = client.post(path + "/messages", json=command).json()
    assert first["run_id"] == again["run_id"]
    assert len(client.get(path).json()["messages"]) == 2
    conflict = client.post(path + "/messages", json={**command, "content": "changed"})
    assert conflict.status_code == 409
    assert (
        client.post(path + "/stop", json={"request_id": "bad", "run_id": "old"}).status_code == 409
    )
    result = client.post(path + "/stop", json={"request_id": "stop", "run_id": first["run_id"]})
    assert result.json()["status"] in {"stopped", "completed"}


def test_origin_session_and_owner_checks(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/sessions",
            json={"request_id": "bad"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/sessions", json={"request_id": "bad"}, headers={"X-Auton-Client": ""}
        ).status_code
        == 403
    )
    session = client.post("/api/v1/sessions", json={"request_id": "create"}).json()
    with TestClient(client.app) as other:
        assert other.get(f"/api/v1/sessions/{session['id']}").status_code == 401
        other.get("/api/v1/bootstrap")
        assert other.get(f"/api/v1/sessions/{session['id']}").status_code == 404


def test_future_modules_are_not_ready(client: TestClient) -> None:
    modules = client.get("/api/v1/capabilities").json()
    planned = [module for module in modules if module["status"] == "planned"]
    assert len(planned) == 16
    assert all(module["factory_entry"] is None for module in planned)


def test_websocket_denies_untrusted_origin_and_unknown_session(client: TestClient) -> None:
    session = client.post("/api/v1/sessions", json={"request_id": "create"}).json()
    for session_id, origin in [
        (session["id"], "https://evil.example"),
        ("not-this-owner", "http://testserver"),
    ]:
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                f"/api/v1/sessions/{session_id}/events", headers={"Origin": origin}
            ),
        ):
            pytest.fail("Untrusted WebSocket must not be accepted")


def test_duplicate_after_stop_returns_current_snapshot_without_reexecuting(
    client: TestClient,
) -> None:
    session = client.post("/api/v1/sessions", json={"request_id": "create"}).json()
    path = f"/api/v1/sessions/{session['id']}"
    command = {"request_id": "send", "content": "one logical request"}
    running = client.post(path + "/messages", json=command).json()
    client.post(path + "/stop", json={"request_id": "stop", "run_id": running["run_id"]})
    previous = client.get(path).json()
    replay = client.post(path + "/messages", json=command).json()
    assert replay == previous
    assert len(replay["messages"]) == 2


async def test_stop_ack_and_disconnect_do_not_restart_or_cancel_other_runs(
    deps: RuntimeDependencies,
) -> None:
    service = DemoConversationFactory().create(DemoConfig(chunk_delay_seconds=0.01), deps)
    await service.start()
    try:
        session = service.create_session("owner", CreateSession(request_id="c"))
        queue = service.subscribe("owner", session.id)
        await queue.get()
        running = await service.send(
            "owner", session.id, SendMessage(request_id="s", content="hello")
        )
        service.unsubscribe(session.id, queue)
        await asyncio.sleep(0.03)
        assert service.get_session("owner", session.id).status == "running"
        assert running.run_id is not None
        stopped = await service.stop(
            "owner", session.id, StopRun(request_id="stop", run_id=running.run_id)
        )
        assert stopped.status == "stopped"
        count = len(stopped.messages[-1].content)
        await asyncio.sleep(0.03)
        assert len(service.get_session("owner", session.id).messages[-1].content) == count
    finally:
        await service.close()
        await service.close()
