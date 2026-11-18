"""Explicit download of two pinned text tokenizers, not model weights or remote Python."""

import hashlib
import time
from pathlib import Path

import httpx

from auton.context.tokenization import BINDINGS


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "weights/context-tokenizers"
    with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=True) as client:
        for model, (repo, revision, expected, size) in BINDINGS.items():
            target = root / model / "tokenizer.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                data = target.read_bytes()
                if (
                    len(data) == size
                    and hashlib.sha1(f"blob {size}\0".encode() + data).hexdigest() == expected
                ):
                    print("Verified", model, flush=True)
                    continue
            for attempt in range(6):
                try:
                    endpoint = "raw" if attempt % 2 == 0 else "resolve"
                    response = client.get(
                        f"https://huggingface.co/{repo}/{endpoint}/{revision}/tokenizer.json?download=true"
                    )
                    response.raise_for_status()
                    data = response.content
                    if (
                        len(data) != size
                        or hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
                        != expected
                    ):
                        raise ValueError("Official tokenizer checksum mismatch")
                    temporary = target.with_suffix(".part")
                    temporary.write_bytes(data)
                    temporary.replace(target)
                    print("Verified", model, flush=True)
                    break
                except httpx.HTTPError:
                    if attempt == 5:
                        raise
                    print("Retrying official tokenizer", model, attempt + 1, flush=True)
                    time.sleep(1)


if __name__ == "__main__":
    main()
