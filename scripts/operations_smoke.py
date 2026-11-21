"""Observe existing private native traces; no new LLM call, training, or publication."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.kernel.ports import RuntimeDependencies


def main() -> None:
    root = Path(__file__).resolve().parents[1] / ".auton_local/evolution-smoke"
    progress = json.loads((root / "progress.json").read_text())
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
    config["operations"]["directory"] = str(root / "operations-observe-v2")
    database = root / "operations-observe-v2/operations_observe.sqlite3"
    if database.exists():
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            records = connection.execute(
                "SELECT d.payload FROM heads h JOIN documents d USING(kind,owner,id,version) "
                "WHERE h.kind='schedule'"
            )
            for (raw,) in records:
                stored = json.loads(raw)
                if stored["enabled"] and stored["command"]["operation"]["kind"] not in {
                    "telemetry",
                    "retention",
                }:
                    raise RuntimeError("Native observe namespace contains other enabled work")
    config["operations"]["observer_only"] = True
    config["operations"]["enabled"] = True
    app = ApplicationFactory().create(
        ApplicationConfig.model_validate(config),
        RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4())),
    )
    with TestClient(
        app, headers={"X-Auton-Client": "web", "Origin": "http://testserver"}
    ) as client:
        for name, value in progress["cookies"].items():
            client.cookies.set(name, value)

        def call(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
            response = client.request(
                method, "/api/v1" + path, **({"json": body} if body is not None else {})
            )
            response.raise_for_status()
            return response.json()

        project = "public-skill-arena"
        prior = call("GET", "/operations/schedules?project_id=" + project)
        if any(
            s["command"]["operation"]["kind"] not in {"telemetry", "retention"} and s["enabled"]
            for s in prior
        ):
            raise RuntimeError(
                "Native operations smoke refuses to run alongside other enabled work"
            )
        schedule = next(
            (
                s
                for s in prior
                if s["command"]["request_id"] == "native-operations-isolated-observe-v2"
            ),
            None,
        )
        if schedule is None:
            schedule = call(
                "POST",
                "/operations/schedules",
                {
                    "request_id": "native-operations-isolated-observe-v2",
                    "project_id": project,
                    "operation": {"kind": "telemetry"},
                    "enabled": True,
                    "confirm_background_actions": True,
                    "expires_at": datetime.now(UTC).timestamp() + 3600,
                },
            )
        call("POST", "/operations/tick", {})
        jobs = call("GET", "/operations/jobs?project_id=" + project)
        own = next(j for j in jobs if j["schedule_id"] == schedule["id"])
        assert own["status"] == "succeeded", own["reason"]
        samples = call("GET", "/operations/samples?project_id=" + project)
        sample = next(s for s in samples if s["id"] == own["id"])
        backup = call(
            "POST", "/operations/backups", {"request_id": "native-operations-isolated-snapshot-v2"}
        )
        print(
            json.dumps(
                {
                    "job_id": own["id"],
                    "status": own["status"],
                    "runs_observed": sample["runs"],
                    "source_counts": sample["source_counts"],
                    "known_historical_cost_microusd": sample["known_cost_microusd"],
                    "unknown_historical_charges": sample["unknown_charges"],
                    "backup_id": backup["id"],
                    "backup_sha256": backup["sha256"],
                    "new_model_calls": 0,
                    "training_started": False,
                    "published": False,
                }
            )
        )


if __name__ == "__main__":
    main()
