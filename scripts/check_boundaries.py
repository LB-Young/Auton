"""Enforce frontend module imports without adding a JavaScript build script."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "clients/web/src"


def violations() -> list[str]:
    errors: list[str] = []
    for path in WEB.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        source = path.relative_to(WEB).parts
        for reference in re.findall(r"from\s+['\"]([^'\"]+)['\"]", path.read_text()):
            if not reference.startswith("."):
                continue
            target = (path.parent / reference).resolve()
            if not target.is_relative_to(WEB):
                errors.append(f"{path.relative_to(ROOT)} imports outside src: {reference}")
                continue
            destination = target.relative_to(WEB).parts
            forbidden = False
            if source[0] == "shared":
                forbidden = destination[0] != "shared"
            if source[0] == "transport":
                forbidden = destination[0] not in {"shared", "transport"}
            if source[0] == "features":
                forbidden = destination[0] == "app"
                if destination[0] == "transport":
                    forbidden = target.name != "ports"
                if destination[0] == "features" and source[1] != destination[1]:
                    forbidden = target.name != "ports"
            if forbidden:
                errors.append(f"{path.relative_to(ROOT)} violates module boundary: {reference}")
    return errors


def main() -> None:
    errors = violations()
    if errors:
        raise SystemExit("\n".join(errors))
    print("Frontend module boundaries passed")


if __name__ == "__main__":
    main()
