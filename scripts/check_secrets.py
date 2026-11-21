"""Reject staged copies of locally configured credentials without printing values."""

import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    values = {**dotenv_values(ROOT / ".env", interpolate=False), **os.environ}
    secrets = {
        value.encode()
        for name, value in values.items()
        if value
        and len(value) >= 12
        and any(part in name.upper() for part in ("API_KEY", "SECRET", "PASSWORD", "TOKEN"))
    }
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    for name in names:
        if not name:
            continue
        filename = os.fsdecode(name)
        content = subprocess.check_output(["git", "show", f":{filename}"], cwd=ROOT)
        if any(secret in content for secret in secrets):
            raise SystemExit(
                f"Credential found in staged file: {filename}; remove before committing"
            )
    print("Staged credential check passed (values never printed)")


if __name__ == "__main__":
    main()
