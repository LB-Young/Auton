"""Isolated optional native inference. JSON lines in/out, no credentials or network setup."""

import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any


def load(directory: Path, device: str, revision: str) -> Any:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["revision"] != revision or manifest["subfolder"] != "multilingual":
        raise ValueError("Checkpoint identity differs")
    expected = {
        "model.safetensors",
        "rl_agent_config.json",
        "encoder/config.json",
        "tokenizer/tokenizer.json",
        "tokenizer/tokenizer_config.json",
    }
    if set(manifest["files"]) != expected:
        raise ValueError("Checkpoint manifest is incomplete")
    for name, checksum in manifest["files"].items():
        hasher = hashlib.sha256()
        with (directory / name).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        if hasher.hexdigest() != checksum:
            raise ValueError("Checkpoint digest differs")
    if importlib.metadata.version("laya") != "0.3.20":
        raise ValueError("Unsupported Laya runtime")
    module = importlib.import_module("laya")
    agent = module.Agent(str(directory.resolve()), device=device, fast=False, compile=False)
    if str(agent.device) != device:
        raise ValueError("Requested device is unavailable")
    return agent


def predict(agent: Any, value: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    # This adapter is intentionally bound to the inspected 0.3.20 packing protocol.
    common = importlib.import_module("laya.common")
    valid: dict[str, Any] = {}
    failed: dict[str, Any] = {}
    for qid, question in value["questions"].items():
        internal = agent._to_internal(question)
        options = common.render_options(internal)
        lengths = [
            len(
                agent.tok(" " + text.replace(agent.tok.mask_token, " "), add_special_tokens=False)[
                    "input_ids"
                ]
            )
            for text in options
        ]
        instruction = f"{internal['t']} question: {internal['ins']}".replace(
            agent.tok.mask_token, " "
        )
        head = len(agent.tok(instruction, add_special_tokens=False)["input_ids"])
        if max(lengths) > 48 or head + sum(lengths) + len(options) > 768:
            failed[qid] = {"error": "question_truncated"}
            continue
        sequence, _ = common.build_sequence(
            agent.tok, value["state"], internal, max_len=100000, head_max_len=768
        )
        if len(sequence) > max_tokens:
            failed[qid] = {"error": "state_truncated"}
            continue
        valid[qid] = question
    raw = (
        agent.predict(value["state"], valid, max_len=max_tokens, head_max_len=768)
        if valid
        else {"answers": {}}
    )
    raw["answers"].update(failed)
    return raw


def main() -> None:
    directory, device, revision, maximum = sys.argv[1:]
    try:
        with contextlib.redirect_stdout(sys.stderr):
            agent = load(Path(directory), device, revision)
        print(
            json.dumps({"ready": True, "runtime": "laya-0.3.20", "device": str(agent.device)}),
            flush=True,
        )
    except Exception:
        print(json.dumps({"ready": False, "error": "local_model_load_failed"}), flush=True)
        return
    for line in sys.stdin:
        try:
            value = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                raw = predict(agent, value, int(maximum))
            print(json.dumps({"raw": raw}, allow_nan=False), flush=True)
        except Exception:
            print(json.dumps({"error": "local_inference_failed"}), flush=True)


if __name__ == "__main__":
    main()
