import stat
from pathlib import Path

import httpx
import pytest

from auton.cli.factory import AgentClientFactory
from auton.kernel.ports import ApplicationError


async def test_cli_identity_persistence_permissions_and_expiry(tmp_path: Path) -> None:
    owner = "synthetic-cli-owner"
    cookies: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        cookies.append(request.headers.get("cookie", ""))
        return httpx.Response(
            200,
            json={},
            headers={"set-cookie": f"auton_owner={owner}; Path=/; HttpOnly; SameSite=Strict"},
        )

    first = AgentClientFactory().create(directory=tmp_path)
    await first.client.aclose()
    first.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(respond)
    )
    await first.start()
    assert stat.S_IMODE(first.path.stat().st_mode) == 0o600
    await first.close()
    second = AgentClientFactory().create(directory=tmp_path)
    await second.client.aclose()
    second.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(respond)
    )
    try:
        await second.start()
        assert cookies[-1] == "auton_owner=" + owner
        owner = "rotated-identity"
        with pytest.raises(ApplicationError) as error:
            await second.start()
        assert error.value.code == "cli_identity_expired"
    finally:
        await second.close()
    with pytest.raises(ValueError):
        AgentClientFactory().create("https://example.org")


async def test_cli_initializes_its_own_project_assets_and_immutable_workspace(
    client: object, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(client, TestClient)

    def forward(request: httpx.Request) -> httpx.Response:
        headers = {"X-Auton-Client": "web", "Origin": "http://testserver"}
        if request.headers.get("content-type"):
            headers["Content-Type"] = request.headers["content-type"]
        if request.headers.get("cookie"):
            headers["Cookie"] = request.headers["cookie"]
        response = client.request(
            request.method, request.url.raw_path.decode(), content=request.content, headers=headers
        )
        return httpx.Response(
            response.status_code, content=response.content, headers=response.headers
        )

    cli = AgentClientFactory().create(directory=tmp_path / "cli")
    await cli.client.aclose()
    cli.client = httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(forward)
    )
    try:
        await cli.start()
        value = await cli.initialize(
            "cli-project", "CLI project", False, "Public context provenance notes"
        )
        assert value["workspace_id"] == "cli-project" and not value["read_only"]
        assert value == await cli.initialize(
            "cli-project", "CLI project", False, "Public context provenance notes"
        )
        with pytest.raises(ApplicationError):
            await cli.initialize("cli-project", "CLI project", True, None)
        with pytest.raises(ApplicationError):
            await cli.initialize("cli-project", "CLI project", False, "changed content")
    finally:
        await cli.close()
