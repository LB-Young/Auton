"""Opt-in real DeepSeek/Laya execution for a public synthetic Skill arena; no release claim."""

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.kernel.ports import RuntimeDependencies

ROOT = Path(__file__).resolve().parents[1]
CONTENT = (
    "# Skill\nKeep project evidence and user boundaries.\n\n"
    "## Execution\nRead the goal.\nWrite once.\nReport the receipt.\n\n"
    "## Safety\nNever expand granted permissions or invent evidence.\n"
)


def main(reuse: bool) -> None:
    root = ROOT / ".auton_local/evolution-smoke"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    pointer = root / "progress.json"
    if pointer.exists() and not reuse:
        raise RuntimeError("An acceptance record exists; use --reuse-completed or inspect it first")
    config: dict[str, Any] = {
        "profile": "dev",
        "implementation": "disabled",
        "allowed_origins": ["http://testserver"],
        "constitution": {"remote_providers": ["deepseek"]},
    }
    for section in (
        "server",
        "tools",
        "genome",
        "agent",
        "experience",
        "assess",
        "delegation",
        "evolve",
        "decision_review",
        "datasets",
        "kernel",
    ):
        config[section] = {
            "data_directory" if section == "kernel" else "directory": str(root / section)
        }
    application = ApplicationFactory().create(
        ApplicationConfig.model_validate(config),
        RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4())),
    )
    with TestClient(
        application, headers={"X-Auton-Client": "web", "Origin": "http://testserver"}
    ) as client:
        if reuse:
            progress = json.loads(pointer.read_text())
            for name, value in progress["cookies"].items():
                client.cookies.set(name, value)
        else:
            client.get("/api/v1/bootstrap").raise_for_status()

        def get(path: str) -> Any:
            value = client.get("/api/v1" + path)
            value.raise_for_status()
            return value.json()

        def post(path: str, command: object) -> Any:
            value = client.post("/api/v1" + path, json=command)
            if not value.is_success:
                raise RuntimeError(f"{path}: {value.status_code} {value.text}")
            return value.json()

        project = "public-skill-arena"
        if reuse:
            arena = get("/evolution/arenas/" + progress["arena_id"])
            assert arena["status"] == "complete"
            proposal = get("/evolution/proposals/" + progress["proposal_id"])
            assert proposal["activation"] == "not_activated"
            print(
                json.dumps(
                    {
                        "reused_without_new_model_calls": True,
                        "arena_id": arena["id"],
                        "status": arena["status"],
                        "calls": arena["total_model_calls"],
                        "tokens": arena["total_tokens"],
                        "cost_microusd": arena["total_cost_microusd"],
                        "gates": arena["gates"],
                    },
                    ensure_ascii=False,
                )
            )
            return
        model = next(
            m["id"] for m in get("/models") if m["provider"] == "deepseek" and "flash" in m["id"]
        )
        post("/projects", {"id": project, "title": "Public synthetic Skill engineering acceptance"})
        post(
            "/tools/workspaces", {"id": "diagnosis", "title": "Public baseline", "read_only": False}
        )
        pending = post(
            f"/projects/{project}/candidates",
            {
                "asset": {
                    "id": "skill",
                    "name": "Verification Skill",
                    "kind": "skill",
                    "content": CONTENT,
                    "origin": "user_explicit",
                    "source": "public synthetic engineering acceptance",
                },
                "expected": None,
            },
        )
        post(
            f"/projects/{project}/assets/skill/promote",
            {
                "expected": pending["revision"],
                "candidates_revision": pending["candidates_revision"],
            },
        )
        snapshot = post(f"/projects/{project}/snapshots", {})
        goal = (
            "Write exactly hello followed by a newline to notes.md. "
            "Use file_write with content hello\\n. The new file has no old digest, "
            "so expected_sha256 must be null. Report the actual tool receipt."
        )
        sha = hashlib.sha256(b"hello\n").hexdigest()
        run = post(
            "/agent/runs",
            {
                "request_id": "diagnostic-baseline",
                "project_id": project,
                "workspace_id": "diagnosis",
                "model_id": model,
                "goal": goal,
                "data_domain": "public",
                "allowed_tools": ["file.write"],
                "acceptance": {"kind": "file", "path": "notes.md", "sha256": sha},
            },
        )
        deadline = time.monotonic() + 600
        while run["status"] not in {"succeeded", "failed", "blocked", "cancelled"}:
            if run["status"] == "waiting_approval":
                post(
                    f"/agent/runs/{run['id']}/commands",
                    {
                        "request_id": "approve-baseline",
                        "expected_goal_revision": 1,
                        "expected_version": run["version"],
                        "action": "approve",
                    },
                )
            if time.monotonic() > deadline:
                raise RuntimeError("Baseline deadline")
            time.sleep(0.2)
            run = get("/agent/runs/" + run["id"])
        assert run["status"] == "succeeded", run["reason"]
        report = post(
            "/assessment/jobs",
            {
                "request_id": "diagnosis",
                "project_id": project,
                "run_id": run["id"],
                "expected_version": run["version"],
            },
        )["report"]
        diagnosis = post(
            "/evolution/diagnoses",
            {
                "request_id": "diagnosis",
                "project_id": project,
                "asset_id": "skill",
                "report_ids": [report["id"]],
            },
        )
        before = "Read the goal.\nWrite once.\nReport the receipt.\n\n"
        proposal = post(
            "/evolution/proposals",
            {
                "request_id": "local-verification",
                "project_id": project,
                "diagnosis_id": diagnosis["id"],
                "base_snapshot_id": snapshot["id"],
                "asset_id": "skill",
                "expected_content_sha256": hashlib.sha256(CONTENT.encode()).hexdigest(),
                "patch": {
                    "heading": "## Execution",
                    "before": before,
                    "after": before.replace("Write once.", "Write once and verify the receipt."),
                },
                "rationale": "Check whether explicit receipt verification improves delivery.",
                "direction": "Improve receipt verification without extending permissions.",
            },
        )
        assert proposal["status"] == "proposed", proposal["reasons"]
        bank = get("/assessment/bank")
        cases = [
            {
                "id": i,
                "family": i,
                "origin_group": "public-" + i,
                "split": split,
                "prompt": prompt,
                "kind": "file",
                "target_path": "notes.md",
                "expected_sha256": sha,
                "source": "test_fixture",
                "data_domain": "public",
            }
            for i, split, prompt in (
                ("core", "train", goal),
                (
                    "dev",
                    "development",
                    "Create notes.md containing exactly hello and a final newline. "
                    "Use file_write and null expected_sha256 because this file is absent. "
                    "Only claim observed tool results.",
                ),
            )
        ]
        bank = post(
            "/assessment/bank",
            {
                "request_id": "public-synthetic-cases",
                "expected_revision": bank["revision"],
                "cases": cases,
            },
        )
        arena = post(
            "/evolution/arenas",
            {
                "request_id": "public-arena",
                "proposal_id": proposal["id"],
                "expected_proposal_version": proposal["version"],
                "bank_revision": bank["revision"],
                "train_cases": ["core"],
                "development_cases": ["dev"],
                "repeats": 1,
                "model_id": model,
                "limits": {
                    "max_steps": 3,
                    "max_tokens": 8000,
                    "max_cost_microusd": 4000,
                    "max_tool_calls": 1,
                },
                "checkpoints": [
                    {
                        "name": "old-digest",
                        "tool": "file_write",
                        "require_absent_or_null_old_digest": True,
                    }
                ],
                "public": True,
            },
        )
        progress = {
            "arena_id": arena["id"],
            "proposal_id": proposal["id"],
            "cookies": dict(client.cookies),
        }
        pointer.write_text(json.dumps(progress))
        pointer.chmod(0o600)
        post(
            "/evolution/arenas/" + arena["id"] + "/commands",
            {"request_id": "start", "expected_version": arena["version"], "action": "start"},
        )
        deadline = time.monotonic() + 1000
        while True:
            arena = get("/evolution/arenas/" + arena["id"])
            if arena["status"] == "complete":
                break
            assert arena["status"] not in {"blocked", "cancelled"}, arena["reason"]
            if arena["status"] == "waiting_approval":
                trial = next(t for t in arena["trials"] if t["id"] == arena["current_trial"])
                assert "+hello" in trial["pending_preview"]
                post(
                    "/evolution/arenas/" + arena["id"] + "/commands",
                    {
                        "request_id": "approve-" + str(arena["version"]),
                        "expected_version": arena["version"],
                        "action": "approve_current",
                    },
                )
            if time.monotonic() > deadline:
                raise RuntimeError("Arena deadline; inspect saved record")
            time.sleep(0.2)
        assert all(t["outcome"] == "pass" for t in arena["trials"]), [
            (t["variant"], t["outcome"], t["reasons"]) for t in arena["trials"]
        ]
        assert not arena["ready_for_release"] and not arena["unknown_model_calls"]
        proposal = get("/evolution/proposals/" + proposal["id"])
        assets = get(f"/projects/{project}/assets")
        queued = post(
            "/evolution/proposals/" + proposal["id"] + "/submit",
            {
                "request_id": "review-public-engineering",
                "expected_version": proposal["version"],
                "arena_id": arena["id"],
                "expected_learning_revision": assets["candidates_revision"],
                "direction_reviewed": True,
            },
        )
        assert queued["status"] == "review_queue" and queued["activation"] == "not_activated"
        summary = {
            "arena_id": arena["id"],
            "proposal_id": proposal["id"],
            "status": queued["status"],
            "calls": arena["total_model_calls"],
            "tokens": arena["total_tokens"],
            "cost_microusd": arena["total_cost_microusd"],
            "gates": arena["gates"],
            "baseline_tokens": run["tokens_used"],
            "baseline_cost_microusd": run["cost_microusd"],
        }
        (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-completed", action="store_true")
    main(parser.parse_args().reuse_completed)
