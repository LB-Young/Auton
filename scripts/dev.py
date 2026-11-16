"""Python entry point for development, contract generation and verification."""

import argparse
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "clients/web"
PYTHON = sys.executable
NPM = "npm.cmd" if os.name == "nt" else "npm"


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def tool(name: str) -> str:
    return str(Path(PYTHON).parent / (name + (".exe" if os.name == "nt" else "")))


def api_command() -> list[str]:
    return [
        PYTHON,
        "-m",
        "uvicorn",
        "auton.bootstrap.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--no-access-log",
    ]


def web_command() -> list[str]:
    return [NPM, "run", "dev", "--prefix", str(WEB)]


def stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


@contextmanager
def servers() -> Iterator[list[subprocess.Popen[bytes]]]:
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for command in [api_command(), web_command()]:
            processes.append(subprocess.Popen(command, cwd=ROOT, start_new_session=True))
        for url in ["http://127.0.0.1:8000/api/v1/health", "http://127.0.0.1:5173"]:
            deadline = time.monotonic() + 30
            while True:
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("Development server exited during startup (port in use?)")
                try:
                    with urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Server did not become ready: {url}")
                time.sleep(0.2)
        yield processes
    finally:
        for process in reversed(processes):
            stop(process)


def contracts(check: bool = False) -> None:
    run([PYTHON, "scripts/export_contracts.py", *(["--check"] if check else [])])
    if not check:
        run([NPM, "run", "contracts"], WEB)
        return
    # Compare without modifying the committed generated file.
    with tempfile.TemporaryDirectory(prefix="auton-contract-") as temporary:
        generated = Path(temporary) / "api.generated.ts"
        run(
            [
                str(WEB / "node_modules/.bin/openapi-typescript"),
                str(ROOT / "contracts/openapi.json"),
                "-o",
                str(generated),
            ]
        )
        run(
            [
                str(WEB / "node_modules/.bin/prettier"),
                "--write",
                str(generated),
                "--config",
                str(WEB / ".prettierrc.json"),
            ]
        )
        if generated.read_bytes() != (WEB / "src/shared/api.generated.ts").read_bytes():
            raise SystemExit("TypeScript contract drift: run make contracts")
        print("Generated TypeScript matches backend contract")


def check() -> None:
    for arguments in [
        ["-m", "ruff", "check", "src", "tests", "scripts"],
        ["-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        ["-m", "mypy"],
        ["-m", "pytest", "-q", "-m", "not browser"],
        ["scripts/check_boundaries.py"],
    ]:
        run([PYTHON, *arguments])
    run([tool("lint-imports")])
    contracts(check=True)
    run([NPM, "run", "lint"], WEB)
    run([NPM, "run", "build"], WEB)


def interrupt(_signum: int, _frame: FrameType | None) -> None:
    raise KeyboardInterrupt


def main() -> None:
    signal.signal(signal.SIGTERM, interrupt)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("all", "api", "web", "check", "contracts", "e2e"))
    args = parser.parse_args()
    try:
        if args.command == "check":
            check()
        elif args.command == "contracts":
            contracts()
        elif args.command == "api":
            run(api_command())
        elif args.command == "web":
            run(web_command())
        else:
            with servers() as processes:
                if args.command == "e2e":
                    run([PYTHON, "-m", "pytest", "-q", "-m", "browser", "tests/e2e"])
                else:
                    print("Auton: http://127.0.0.1:5173  (Ctrl+C to stop)", flush=True)
                    while True:
                        if any(process.poll() is not None for process in processes):
                            raise RuntimeError("A development server exited")
                        time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
