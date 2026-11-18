"""Export deterministic HTTP and WebSocket contracts without starting resources."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from auton.bootstrap.app import ApplicationFactory
from auton.bootstrap.config import ApplicationConfig
from auton.demo.ports import SessionEvent
from auton.kernel.ports import RuntimeDependencies
from auton.server.run_events import RunFrame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    app = ApplicationFactory().create(
        ApplicationConfig(),
        RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4())),
    )
    schema = app.openapi()
    event = SessionEvent.model_json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    schema["components"]["schemas"].update(event.pop("$defs", {}))
    schema["components"]["schemas"]["SessionEvent"] = event
    frame = RunFrame.model_json_schema(
        mode="serialization", ref_template="#/components/schemas/{model}"
    )
    schema["components"]["schemas"].update(frame.pop("$defs", {}))
    schema["components"]["schemas"]["RunFrame"] = frame
    text = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path = Path(__file__).resolve().parents[1] / "contracts/openapi.json"
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            raise SystemExit("Contract drift: run make contracts and commit generated files")
        print("API contract is up to date")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("Exported contracts/openapi.json")


if __name__ == "__main__":
    main()
