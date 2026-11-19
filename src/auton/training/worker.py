"""Portable, offline HF/PEFT reference worker. Optional dependencies live only in its image.

This file can be mounted alone. It imports no Auton application or provider configuration.
"""

import hashlib
import importlib
import json
import math
import os
import re
import resource
import signal
import sys
import time
from pathlib import Path
from typing import Any


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def hf_messages(record: dict[str, Any]) -> list[dict[str, Any]]:
    messages = []
    for original in record["messages"]:
        message = dict(original)
        if "tool_calls" in message:
            message["tool_calls"] = [
                {
                    "id": c["id"],
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["arguments"]},
                }
                for c in message["tool_calls"]
            ]
        messages.append(message)
    return messages


def encode_record(record: dict[str, Any], tokenizer: Any, limit: int) -> dict[str, Any]:
    """Only exact selected assistant spans carry loss; refuse incompatible templates."""
    index = record["input_message_count"]
    messages = hf_messages(record)
    if record["kind"] != "executor" or record["loss_message_indices"] != [index]:
        raise ValueError("wrong_loss_mask")
    if index < 1 or index >= len(messages) or messages[index]["role"] != "assistant":
        raise ValueError("wrong_target_role")
    calls = messages[index].get("tool_calls", [])
    replies = messages[index + 1 :]
    if (
        not calls
        or {c["id"] for c in calls} != {r.get("tool_call_id") for r in replies}
        or len(calls) != len(replies)
        or any(r["role"] != "tool" for r in replies)
    ):
        raise ValueError("truncated_tool_pair")
    tools = [{"type": "function", "function": t} for t in record["tools"]]

    def render(items: list[dict[str, Any]], generation: bool = False) -> str:
        result = tokenizer.apply_chat_template(
            items,
            tools=tools,
            tokenize=False,
            add_generation_prompt=generation,
            enable_thinking=False,
        )
        if not isinstance(result, str):
            raise ValueError("template_not_text")
        return result

    prefix = render(messages[:index], True)
    target = render(messages[: index + 1])
    full = render(messages)
    if not target.startswith(prefix) or not full.startswith(target):
        raise ValueError("template_target_boundary_unsupported")
    encoded = tokenizer(full, add_special_tokens=False, return_offsets_mapping=True)
    tokens = encoded["input_ids"]
    if len(tokens) > limit:
        raise ValueError("sequence_limit_no_truncation")
    start, end = len(prefix), len(target)
    labels = []
    for token, (a, b) in zip(tokens, encoded["offset_mapping"], strict=True):
        if a < start < b or a < end < b:
            raise ValueError("token_straddles_supervision_boundary")
        labels.append(token if start <= a < b <= end else -100)
    if not any(v != -100 for v in labels):
        raise ValueError("empty_supervision")
    return {
        "input_ids": tokens,
        "labels": labels,
        "prompt": prefix,
        "target": messages[index],
        "id": record["id"],
    }


def atomic_json(path: Path, value: Any) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w") as handle:
        json.dump(value, handle, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)


def run(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    signal.alarm(manifest["max_wall_seconds"])
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    peft = importlib.import_module("peft")
    safe = importlib.import_module("safetensors.torch")
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (manifest["max_output_bytes"], manifest["max_output_bytes"])
    )
    plan = manifest["command"]
    output = Path("/output")
    started = time.monotonic()
    torch.manual_seed(plan["seed"])
    torch.use_deterministic_algorithms(True)
    device = manifest["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("requested_device_unavailable")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        "/base", local_files_only=True, trust_remote_code=False, use_fast=True
    )
    datasets = {}
    for scope, expected in manifest["data_sha256"].items():
        path = manifest_path.parent / (scope + ".jsonl")
        if sha(path) != expected:
            raise ValueError("dataset_digest_changed")
        datasets[scope] = [
            encode_record(json.loads(line), tokenizer, plan["max_sequence_length"])
            for line in path.read_text().splitlines()
        ]
    if not datasets.get("train"):
        raise ValueError("training_data_empty")
    model = transformers.AutoModelForCausalLM.from_pretrained(
        "/base",
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        torch_dtype=torch.float32,
    )
    model = peft.get_peft_model(
        model,
        peft.LoraConfig(
            r=plan["rank"],
            lora_alpha=2 * plan["rank"],
            target_modules="all-linear",
            lora_dropout=0.0,
            task_type="CAUSAL_LM",
        ),
    )
    model.to(device)
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=plan["learning_rate"])
    completed = 0
    runtime = {
        "device": device,
        "cuda_devices": torch.cuda.device_count() if device == "cuda" else 0,
        "versions": {
            name: importlib.import_module("importlib.metadata").version(name)
            for name in ("torch", "transformers", "peft", "safetensors")
        },
    }

    def save(step: int) -> None:
        name = "step-" + str(step).zfill(8)
        folder = output / (name + ".tmp")
        folder.mkdir(exist_ok=False)
        safe.save_file(
            {
                k: v.detach().cpu().contiguous()
                for k, v in peft.get_peft_model_state_dict(model).items()
            },
            str(folder / "adapter.safetensors"),
        )
        tensors = {"rng": torch.get_rng_state()}
        if device == "cuda":
            tensors.update(
                {f"cuda_rng_{i}": v for i, v in enumerate(torch.cuda.get_rng_state_all())}
            )
        for i, parameter in enumerate(params):
            for k, v in optimizer.state[parameter].items():
                if not torch.is_tensor(v):
                    raise ValueError("optimizer_state_not_safe_tensor")
                tensors[f"optimizer_{i}_{k}"] = v.detach().cpu().contiguous()
        safe.save_file(
            tensors,
            str(folder / "state.safetensors"),
            metadata={"runtime": json.dumps(runtime, sort_keys=True)},
        )
        files = {p.name: sha(p) for p in folder.iterdir()}
        checkpoint = {"step": step, "files": files, "manifest_digest": manifest["plan_digest"]}
        atomic_json(folder / "checkpoint.json", checkpoint)
        folder.rename(output / name)
        atomic_json(output / "progress.json", {"checkpoint": checkpoint, "folder": name})

    resume = manifest.get("resume")
    if resume:
        folder = manifest_path.parent / "resume"
        checkpoint = resume
        if checkpoint["manifest_digest"] != manifest["plan_digest"]:
            raise ValueError("resume_plan_mismatch")
        for name, expected in checkpoint["files"].items():
            if sha(folder / name) != expected:
                raise ValueError("checkpoint_corrupt")
        with importlib.import_module("safetensors").safe_open(
            str(folder / "state.safetensors"), framework="pt", device="cpu"
        ) as saved_state:
            if json.loads(saved_state.metadata().get("runtime", "{}")) != runtime:
                raise ValueError("resume_runtime_changed")
        peft.set_peft_model_state_dict(
            model, safe.load_file(str(folder / "adapter.safetensors"), device=device)
        )
        state = safe.load_file(str(folder / "state.safetensors"))
        torch.set_rng_state(state["rng"])
        if device == "cuda":
            torch.cuda.set_rng_state_all(
                [state[f"cuda_rng_{i}"] for i in range(torch.cuda.device_count())]
            )
        for i, parameter in enumerate(params):
            for k in ("step", "exp_avg", "exp_avg_sq"):
                optimizer.state[parameter][k] = state[f"optimizer_{i}_{k}"].to(
                    device if k != "step" else "cpu"
                )
        completed = checkpoint["step"]

    def loss(record: dict[str, Any]) -> Any:
        return model(
            input_ids=torch.tensor([record["input_ids"]], device=device),
            labels=torch.tensor([record["labels"]], device=device),
        ).loss

    def measure() -> dict[str, Any]:
        model.eval()
        result = {}
        with torch.no_grad():
            for scope, rows in datasets.items():
                losses = [float(loss(r).item()) for r in rows]
                valid, exact = 0, 0
                for row in rows:
                    ids = tokenizer(row["prompt"], return_tensors="pt", add_special_tokens=False)[
                        "input_ids"
                    ].to(device)
                    generated = model.generate(
                        ids,
                        max_new_tokens=256,
                        do_sample=False,
                        pad_token_id=tokenizer.eos_token_id,
                    )
                    text = tokenizer.decode(generated[0, ids.shape[1] :], skip_special_tokens=False)
                    blocks = (
                        re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.S)
                        if manifest["tool_parser"] == "tagged_json"
                        else [text]
                    )
                    try:
                        parsed = [json.loads(b) for b in blocks]
                        expected = row["target"]["tool_calls"]
                        valid += int(
                            len(parsed) == len(expected)
                            and all(
                                isinstance(c, dict)
                                and isinstance(c.get("name"), str)
                                and isinstance(c.get("arguments"), dict)
                                for c in parsed
                            )
                        )
                        exact += int(
                            parsed
                            == [
                                {
                                    "name": c["function"]["name"],
                                    "arguments": c["function"]["arguments"],
                                }
                                for c in expected
                            ]
                        )
                    except (ValueError, TypeError):
                        pass
                result[scope] = {
                    "count": len(rows),
                    "loss": sum(losses) / len(losses),
                    "tool_protocol_pass": valid,
                    "exact_action_pass": exact,
                }
        return result

    baseline = measure() if completed == 0 else manifest["baseline"]
    atomic_json(output / "baseline.json", baseline)
    for step in range(completed, plan["steps"]):
        if time.monotonic() - started > manifest["max_wall_seconds"]:
            raise TimeoutError("worker_wall_budget")
        model.train()
        optimizer.zero_grad(set_to_none=True)
        value = loss(datasets["train"][step % len(datasets["train"])])
        if not math.isfinite(float(value.item())):
            raise ValueError("non_finite_loss")
        value.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimizer.step()
        save(step + 1)
    metrics = {
        "baseline": baseline,
        "candidate": measure(),
        "completed_steps": plan["steps"],
        "device": device,
        "deployment_precision": "float32",
        "quantized_deployment_evaluated": False,
        "runtime_versions": {
            name: importlib.import_module("importlib.metadata").version(name)
            for name in ("torch", "transformers", "peft", "safetensors")
        },
        "wall_seconds": time.monotonic() - started,
    }
    atomic_json(
        output / "result.json",
        {
            "protocol": "auton-training-worker-v1",
            "plan_digest": manifest["plan_digest"],
            "metrics": metrics,
        },
    )


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]))
    except Exception as error:
        # Never log raw examples, prompts, generated text or environment contents.
        atomic_json(Path("/output/error.json"), {"error_type": type(error).__name__})
        raise SystemExit(1) from None
