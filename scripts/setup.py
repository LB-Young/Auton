"""Install locked dependencies; keep bootstrap orchestration in Python."""

import os
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["uv", "sync", "--frozen"], cwd=root, check=True)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=root / "clients/web", check=True)
    print("Ready. Run make dev; browser tests additionally need make browser-install.")


if __name__ == "__main__":
    main()
