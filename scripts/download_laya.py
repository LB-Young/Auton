"""Download the reviewed, pinned multilingual Laya checkpoint; no remote Python files."""

import hashlib
import json
import time
from pathlib import Path

import httpx

REPOSITORY = "convaiinnovations/laya"
REVISION = "e333cb7c823cd1787276228260f56d02fbf5180b"
FILES = {
    "model.safetensors": (
        643835514,
        "sha256",
        "9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204",
    ),
    "tokenizer/tokenizer.json": (
        34363188,
        "sha256",
        "609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f",
    ),
    "encoder/config.json": (1938, "git", "0de0e2d30638873790cf962def52e2acf4db3eef"),
    "rl_agent_config.json": (472, "git", "00e35f88bb731bb9126a914666ab1cdac8a204c8"),
    "tokenizer/tokenizer_config.json": (524, "git", "c255ac0c8cb34a37d066cd0dafe313fd769d27ae"),
}
DIRECTORY = Path(__file__).resolve().parents[1] / "weights/laya-multilingual"


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
    if algorithm == "git":
        hasher.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main() -> None:
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "repository": REPOSITORY,
        "revision": REVISION,
        "subfolder": "multilingual",
        "files": {},
    }
    checksums: dict[str, str] = {}
    with httpx.Client(timeout=httpx.Timeout(60, connect=20), follow_redirects=True) as client:
        for name, (size, algorithm, expected) in FILES.items():
            target = DIRECTORY / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not (
                target.exists()
                and target.stat().st_size == size
                and digest(target, algorithm) == expected
            ):
                temporary = target.with_name(target.name + ".part")
                print("Downloading", name, size, "bytes", flush=True)
                mode = "raw" if algorithm == "git" else "resolve"
                with client.stream(
                    "GET",
                    f"https://huggingface.co/{REPOSITORY}/{mode}/{REVISION}/multilingual/{name}?download=true",
                ) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as handle:
                        for block in response.iter_bytes(1024 * 1024):
                            handle.write(block)
                if temporary.stat().st_size != size or digest(temporary, algorithm) != expected:
                    raise ValueError("Artifact verification failed: " + name)
                temporary.replace(target)
            checksums[name] = digest(target, "sha256")
            print("Verified", name, flush=True)
    manifest["files"] = checksums
    (DIRECTORY / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Local checkpoint ready:", DIRECTORY, flush=True)


if __name__ == "__main__":
    for attempt in range(4):
        try:
            main()
            break
        except httpx.HTTPError:
            if attempt == 3:
                raise
            print("Transient download failure; retrying verified files", flush=True)
            time.sleep(1)
