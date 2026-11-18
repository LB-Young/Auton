import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

import anyio
import httpx

from auton.agent.contracts import AgentRun, CreateRun, RunCommand
from auton.experience.contracts import RecoveryCommand, Trajectory
from auton.genome.contracts import Revision
from auton.kernel.ports import ApplicationError


class AgentClient:
    def __init__(self, base: str, directory: Path) -> None:
        parsed = urlsplit(base)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CLI requires an explicit local HTTP server origin")
        self.directory = directory
        self.path = directory / (hashlib.sha256(base.encode()).hexdigest() + ".json")
        self.client = httpx.AsyncClient(
            base_url=base,
            timeout=60,
            follow_redirects=False,
            headers={"X-Auton-Client": "web", "Origin": base.rstrip("/")},
            trust_env=False,
        )

    def _cookie(self) -> str | None:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("CLI cookie path cannot be a symlink")
        return str(json.loads(self.path.read_text())["owner"]) if self.path.exists() else None

    def _save_cookie(self, value: str) -> None:
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump({"owner": value}, handle)

    async def start(self) -> None:
        stored = await anyio.to_thread.run_sync(self._cookie)
        if stored:
            self.client.headers["Cookie"] = "auton_owner=" + stored
        await self._request("GET", "/api/v1/bootstrap")
        current = self.client.cookies.get("auton_owner")
        if not current:
            raise ApplicationError(
                401, "cli_session_missing", "Local server did not create an identity"
            )
        if stored and current != stored:
            raise ApplicationError(
                401,
                "cli_identity_expired",
                "Server identity expired; persistent cross-restart identity is not implemented yet",
            )
        await anyio.to_thread.run_sync(self._save_cookie, current)

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> httpx.Response:
        response = await self.client.request(method, path, json=body)
        if not response.is_success:
            try:
                error = response.json()
            except ValueError:
                error = {}
            raise ApplicationError(
                response.status_code,
                str(error.get("code", "cli_request_failed")),
                str(error.get("message", "Local server rejected the request")),
            )
        return response

    async def initialize(
        self, project: str, title: str, read_only: bool, notes: str | None
    ) -> dict[str, object]:
        projects = (await self._request("GET", "/api/v1/projects")).json()
        if not any(p["id"] == project for p in projects):
            await self._request("POST", "/api/v1/projects", {"id": project, "title": title})
        workspaces = (await self._request("GET", "/api/v1/tools/workspaces")).json()
        workspace = next((w for w in workspaces if w["id"] == project), None)
        if workspace and workspace["read_only"] != read_only:
            raise ApplicationError(
                409,
                "cli_workspace_scope_changed",
                "Existing workspace has a different immutable read-only scope",
            )
        if workspace is None:
            await self._request(
                "POST",
                "/api/v1/tools/workspaces",
                {"id": project, "title": title, "read_only": read_only},
            )
        if notes is not None:
            path = "/api/v1/projects/" + quote(project, safe="")
            state = Revision.model_validate((await self._request("GET", path + "/assets")).json())
            existing = next((a.asset for a in state.assets if a.asset.id == "notes"), None)
            if existing and existing.content != notes:
                raise ApplicationError(
                    409,
                    "cli_notes_exist",
                    "Existing notes differ; review changes through the asset API",
                )
            if existing is None:
                proposal = (
                    await self._request(
                        "POST",
                        path + "/candidates",
                        {
                            "expected": state.candidates_revision,
                            "asset": {
                                "id": "notes",
                                "name": "CLI notes",
                                "kind": "document",
                                "origin": "user_explicit",
                                "source": "CLI explicitly selected input",
                                "content": notes,
                            },
                        },
                    )
                ).json()
                await self._request(
                    "POST",
                    path + "/assets/notes/promote",
                    {
                        "expected": proposal["revision"],
                        "candidates_revision": proposal["candidates_revision"],
                    },
                )
        return {
            "project_id": project,
            "workspace_id": project,
            "read_only": read_only,
            "notes_imported": notes is not None,
        }

    async def trajectory(self, project: str, run_id: str) -> Trajectory:
        return Trajectory.model_validate(
            (
                await self._request(
                    "GET",
                    (
                        f"/api/v1/projects/{quote(project, safe='')}/runs/"
                        f"{quote(run_id, safe='')}/trajectory"
                    ),
                )
            ).json()
        )

    async def recover(self, project: str, run_id: str, command: RecoveryCommand) -> AgentRun:
        return AgentRun.model_validate(
            (
                await self._request(
                    "POST",
                    (
                        f"/api/v1/projects/{quote(project, safe='')}/runs/"
                        f"{quote(run_id, safe='')}/recover"
                    ),
                    command.model_dump(mode="json"),
                )
            ).json()
        )

    async def create(self, command: CreateRun) -> AgentRun:
        return AgentRun.model_validate(
            (
                await self._request("POST", "/api/v1/agent/runs", command.model_dump(mode="json"))
            ).json()
        )

    async def get(self, identity: str) -> AgentRun:
        return AgentRun.model_validate(
            (await self._request("GET", "/api/v1/agent/runs/" + quote(identity, safe=""))).json()
        )

    async def list(self, project: str) -> list[AgentRun]:
        return [
            AgentRun.model_validate(value)
            for value in (
                await self._request(
                    "GET", "/api/v1/agent/runs?project_id=" + quote(project, safe="")
                )
            ).json()
        ]

    async def command(self, identity: str, command: RunCommand) -> AgentRun:
        return AgentRun.model_validate(
            (
                await self._request(
                    "POST",
                    f"/api/v1/agent/runs/{quote(identity, safe='')}/commands",
                    command.model_dump(mode="json"),
                )
            ).json()
        )


class AgentClientFactory:
    def create(
        self, base: str = "http://127.0.0.1:8000", directory: Path = Path(".auton_local/cli")
    ) -> AgentClient:
        return AgentClient(base, directory)
