import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_tools import RUNTIME, USER, request, write
from test_tools import host as host

from auton.constitution.config import Principal
from auton.kernel.ports import ApplicationError
from auton.tools.ports import ToolError
from auton.tools.service import ToolHost


async def test_bound_project_reads_lists_and_approved_writes_original_files(
    host: ToolHost, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "hello.py"
    source.write_text("print('before')\n")
    source.chmod(0o755)
    (project / ".env").write_text("private fixture")
    (project / "src").mkdir()
    workspace = await host.bind_project_workspace(USER, "project", "Project", str(project), False)
    assert workspace.root_path == str(project.resolve())
    assert not (project / ".auton-lock").exists()
    listing = await request(host, "list-project", "file.list", {"path": ""}, workspace.id)
    assert not (await host.prepare(listing)).requires_approval
    entries = json.loads((await host.execute(RUNTIME, listing.operation_id)).output)["entries"]
    assert {entry["name"] for entry in entries} == {"hello.py", "src"}
    read = await request(host, "read-project", "file.read", {"path": "hello.py"}, workspace.id)
    await host.prepare(read)
    assert (await host.execute(RUNTIME, read.operation_id)).output == "print('before')\n"
    patch = await request(
        host,
        "patch-project",
        arguments={
            "path": "hello.py",
            "content": "print('after')\n",
            "expected_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
        workspace_id=workspace.id,
    )
    plan = await host.prepare(patch)
    assert "-print('before')" in plan.preview and "+print('after')" in plan.preview
    assert source.read_text() == "print('before')\n"
    with pytest.raises(ApplicationError, match="approval"):
        await host.execute(RUNTIME, patch.operation_id)
    await write(host, patch)
    assert source.read_text() == "print('after')\n"
    assert source.stat().st_mode & 0o777 == 0o755
    assert not (project / ".auton-lock").exists()
    with pytest.raises(ToolError):
        await host.workspace(Principal(owner="another", role="user"), workspace.id)


async def test_external_root_boundary_links_hidden_paths_and_replacement(
    host: ToolHost, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("outside")
    (project / "escape").symlink_to(outside, target_is_directory=True)
    (project / "leak.txt").symlink_to(outside / "secret.txt")
    (project / "hard.txt").hardlink_to(outside / "secret.txt")
    (project / ".env").write_text("hidden")
    workspace = await host.bind_project_workspace(USER, "boundary", "Boundary", str(project), False)
    for name in ("../outside/secret.txt", "escape/secret.txt", "leak.txt", "hard.txt", ".env"):
        with pytest.raises(ToolError):
            host.sandbox.read(workspace, name)
    for name in ("../outside", "escape", "."):
        if name == ".":
            listing = json.loads(host.sandbox.list_files(workspace, name))
            assert "leak.txt" not in {entry["name"] for entry in listing["entries"]}
        else:
            with pytest.raises(ToolError):
                host.sandbox.list_files(workspace, name)
    project.rename(tmp_path / "moved")
    project.mkdir()
    (project / "secret.txt").write_text("replacement")
    with pytest.raises(ToolError, match="替换"):
        host.sandbox.read(workspace, "secret.txt")


async def test_project_picker_and_binding_do_not_accept_runtime_or_invalid_directories(
    host: ToolHost, tmp_path: Path
) -> None:
    parent = tmp_path / "folders"
    parent.mkdir()
    (parent / "project").mkdir()
    (parent / ".hidden").mkdir()
    (parent / "alias").symlink_to(parent / "project", target_is_directory=True)
    listing = await host.browse_directories(USER, str(parent))
    assert listing.directories == ("project",)
    for path in (str(parent / "missing"), "/", str(parent / ".hidden")):
        with pytest.raises(ToolError):
            await host.bind_project_workspace(USER, "invalid", "Invalid", path, False)
    with pytest.raises(ToolError):
        await host.bind_project_workspace(RUNTIME, "denied", "Denied", str(parent), False)
    with pytest.raises(ToolError):
        await host.browse_directories(RUNTIME, str(parent))


async def test_project_file_chunks_include_full_hash_for_safe_followup_edits(
    host: ToolHost, tmp_path: Path
) -> None:
    project = tmp_path / "chunked"
    project.mkdir()
    source = project / "source.py"
    source.write_text("\n".join(f"value_{n} = {n}" for n in range(500)))
    workspace = await host.bind_project_workspace(USER, "chunked", "Chunked", str(project), False)
    read = await request(
        host,
        "chunk",
        "file.read",
        {"path": "source.py", "start_line": 41, "max_lines": 40},
        workspace.id,
    )
    await host.prepare(read)
    receipt = await host.execute(RUNTIME, read.operation_id)
    body = json.loads(receipt.output)
    assert body["start_line"] == 41 and body["end_line"] == 80 and body["total_lines"] == 500
    assert "value_40" in body["content"] and "value_80" not in body["content"]
    assert body["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_directory_api_requires_identity_and_rejects_cross_site_browsing(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "http-project"
    root.mkdir()
    listing = client.get("/api/v1/local/directories", params={"path": str(root)})
    assert listing.status_code == 200 and listing.json()["path"] == str(root.resolve())
    denied = client.get(
        "/api/v1/local/directories",
        params={"path": str(root)},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert denied.status_code == 403
    command = {"request_id": "local-http", "title": "Project", "project_path": str(root)}
    created = client.post("/api/v1/conversations", json=command)
    assert created.status_code == 200
    assert client.post("/api/v1/conversations", json=command).json() == created.json()
    identity = created.json()["id"]
    assert client.get(f"/api/v1/conversations/{identity}").json()["conversation"][
        "project_path"
    ] == str(root.resolve())
    client.cookies.clear()
    assert client.get("/api/v1/local/directories").status_code == 401
    client.get("/api/v1/bootstrap")
    assert client.get(f"/api/v1/conversations/{identity}").status_code == 404
