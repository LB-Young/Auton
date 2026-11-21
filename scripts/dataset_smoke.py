"""Curate one owned public native trace without new model calls or training."""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.kernel.ports import RuntimeDependencies

TERMS = "https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html"


def main(reuse: bool) -> None:
    root = Path(__file__).resolve().parents[1] / ".auton_local/evolution-smoke"
    progress = json.loads((root / "progress.json").read_text())
    pointer = root / "dataset-progress.json"
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
        "learning",
        "training",
        "decision_training",
        "release",
        "operations",
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
        for name, value in progress["cookies"].items():
            client.cookies.set(name, value)

        def call(method: str, path: str, body: Any = None) -> Any:
            response = client.request(
                method, "/api/v1" + path, **({"json": body} if body is not None else {})
            )
            response.raise_for_status()
            return response.json()

        if reuse:
            saved = json.loads(pointer.read_text())
            artifact = saved["artifact"]
            snapshot = call("GET", "/datasets/snapshots/" + artifact["snapshot_id"])
        else:
            project = "public-skill-arena"
            runs = call("GET", "/agent/runs?project_id=" + project)
            run = next(r for r in runs if r["command"]["request_id"] == "diagnostic-baseline")
            reports = call("GET", "/assessment/reports?project_id=" + project)
            report = next(
                r
                for r in reports
                if r["run_id"] == run["id"]
                and r["checkpoint_version"] == run["version"]
                and r["outcome"] == "pass"
            )
            grant_command = {
                "request_id": "native-public-executor-data-v1",
                "project_id": project,
                "run_ids": [run["id"]],
                "purposes": ["executor"],
                "data_license_reference": (
                    "User-authorized continual local training; project-owned public synthetic "
                    "file task and explicit original Skill; no third-party inputs"
                ),
                "local_training_authorized": True,
                "teacher_uses": [
                    {
                        "model_id": run["command"]["model_id"],
                        "declared_revision": run["executor_spec"]["declared_revision"],
                        "terms_reference": TERMS
                        + " (API section 4.2, effective 2026-04-29; checked 2026-11-19)",
                        "training_use_confirmed_by_user": True,
                    }
                ],
            }

            def build(consent: dict[str, Any], request: str) -> dict[str, Any]:
                granted = call("POST", "/datasets/grants", consent)
                return cast(
                    dict[str, Any],
                    call(
                        "POST",
                        "/datasets/snapshots",
                        {
                            "request_id": request,
                            "project_id": project,
                            "kind": "executor",
                            "grant_id": granted["id"],
                            "subjects": [
                                {
                                    "run_id": run["id"],
                                    "expected_version": run["version"],
                                    "assessment_report_id": report["id"],
                                    "family": "public-file-hello",
                                    "origin_group": "initial-diagnostic-public-file",
                                    "split": "train",
                                }
                            ],
                        },
                    ),
                )

            snapshot = build(grant_command, "native-public-executor-snapshot-v1")
            assert snapshot["status"] == "ready", snapshot["rejected"]
            artifact = call(
                "POST",
                "/datasets/snapshots/" + snapshot["id"] + "/exports",
                {
                    "request_id": "native-public-executor-export-v1",
                    "expected_content_digest": snapshot["content_digest"],
                    "purpose": "local_training",
                    "split": "train",
                },
            )
            temporary = build(
                {**grant_command, "request_id": "native-temporary-withdrawal-grant-v1"},
                "native-temporary-snapshot-v1",
            )
            temporary_artifact = call(
                "POST",
                "/datasets/snapshots/" + temporary["id"] + "/exports",
                {
                    "request_id": "native-temporary-export-v1",
                    "expected_content_digest": temporary["content_digest"],
                    "purpose": "local_training",
                    "split": "train",
                },
            )
            affected = call(
                "POST",
                "/datasets/withdrawals",
                {
                    "request_id": "native-withdraw-temporary-v1",
                    "project_id": project,
                    "grant_id": temporary["command"]["grant_id"],
                    "reason": (
                        "Verify scoped withdrawal blocks future artifact access "
                        "without revoking the primary source grant"
                    ),
                },
            )
            assert temporary["id"] in affected and snapshot["id"] not in affected
            denied = client.get("/api/v1/datasets/artifacts/" + temporary_artifact["id"])
            assert denied.status_code == 409
            pointer.write_text(
                json.dumps({"artifact": artifact, "withdrawn_artifact": temporary_artifact["id"]})
            )
            pointer.chmod(0o600)
        assert snapshot["status"] == "ready" and snapshot["training_ready"]
        response = client.get("/api/v1/datasets/artifacts/" + artifact["id"])
        response.raise_for_status()
        assert hashlib.sha256(response.content).hexdigest() == artifact["sha256"]
        records = [json.loads(line) for line in response.content.splitlines()]
        assert len(records) == 1 and records[0]["loss_message_indices"] == [
            records[0]["input_message_count"]
        ]
        assert not snapshot["examples"][0]["engineering_only"]
        print(
            json.dumps(
                {
                    "snapshot_id": snapshot["id"],
                    "artifact_id": artifact["id"],
                    "sha256": artifact["sha256"],
                    "bytes": artifact["size"],
                    "examples": len(records),
                    "groups": snapshot["source_groups"],
                    "status": snapshot["status"],
                    "new_model_calls": 0,
                    "training_started": False,
                    "reused": reuse,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-completed", action="store_true")
    main(parser.parse_args().reuse_completed)
