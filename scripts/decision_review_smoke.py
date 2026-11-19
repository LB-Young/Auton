"""Opt-in real independent reviewer over a completed public M15 trace; shadow remains HOLD."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.kernel.ports import RuntimeDependencies


def main(reuse: bool) -> None:
    root = Path(__file__).resolve().parents[1] / ".auton_local/evolution-smoke"
    progress = json.loads((root / "progress.json").read_text())
    pointer = root / "review-progress.json"
    if pointer.exists() and not reuse:
        raise RuntimeError(
            "Review already recorded; use --reuse-completed and inspect before new paid work"
        )
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

        def get(path: str) -> Any:
            response = client.get("/api/v1" + path)
            response.raise_for_status()
            return response.json()

        if reuse:
            review = get("/decision-review/reviews/" + json.loads(pointer.read_text())["id"])
        else:
            arena = get("/evolution/arenas/" + progress["arena_id"])
            assert arena["status"] == "complete"
            trial = arena["trials"][0]
            run = get("/agent/runs/" + trial["run_id"])
            decision = run["judgments"][0]
            command = {
                "request_id": "native-two-stage-independent-review",
                "project_id": arena["project_id"],
                "run_id": run["id"],
                "expected_run_version": run["version"],
                "judgment_id": decision["request_id"],
                "question_id": decision["answers"][0]["question_id"],
                "assessment_report_id": trial["report_id"],
                "public": True,
            }
            response = client.post("/api/v1/decision-review/jobs", json=command)
            response.raise_for_status()
            review = response.json()
            pointer.write_text(json.dumps({"id": review["id"]}))
            pointer.chmod(0o600)
        assert review["status"] in {"complete", "blocked"}, [
            (review.get(k) or {}).get("reason") for k in ("stage_a", "stage_b")
        ]
        assert review["verdict"] == "HOLD" and not review["positive_training_eligible"]
        assert not review["subject"]["decision"]["adopted"]
        stages = [review["stage_a"], review["stage_b"]]
        assert all(s["source"] == "runtime" and s["dispatch"] == "confirmed" for s in stages)
        assert get("/decision-review/eligible?project_id=" + review["command"]["project_id"]) == []
        calibration = get("/decision-review/calibrations")
        assert not any(c["eligible"] for c in calibration)
        print(
            json.dumps(
                {
                    "review_id": review["id"],
                    "status": review["status"],
                    "verdict": review["verdict"],
                    "reason_codes": review["reason_codes"],
                    "stage_models": [s["reported_model"] for s in stages],
                    "stage_reasons": [s["reason"] for s in stages],
                    "stage_fingerprints": [s["fingerprint"] for s in stages],
                    "tokens": sum(s["tokens"] for s in stages),
                    "cost_microusd": sum(s["cost_microusd"] for s in stages),
                    "reused_without_new_model_calls": reuse,
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-completed", action="store_true")
    main(parser.parse_args().reuse_completed)
