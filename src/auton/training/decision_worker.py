"""Portable encoder-choice student; typed option ranking, no chat SFT or online adoption."""

import hashlib
import importlib
import json
import math
import random
import runpy
import signal
import sys
import time
from pathlib import Path
from typing import Any


def encode_choice(record: dict[str, Any], order: list[int] | None = None) -> dict[str, Any]:
    question = record["input"]["question"]
    options = (
        question["options"]
        if question["type"] != "boolean"
        else [{"id": "no", "description": "No"}, {"id": "yes", "description": "Yes"}]
    )
    identities = [o["id"] for o in options]
    if not 2 <= len(options) <= 6 or len(set(identities)) != len(identities):
        raise ValueError("invalid_option_set")
    target = record["target"]
    if target["selected_id"] not in identities or target["question_id"] != question["id"]:
        raise ValueError("invalid_option_target")
    order = list(range(len(options))) if order is None else order
    if sorted(order) != list(range(len(options))):
        raise ValueError("invalid_option_permutation")
    state = record["input"]["state"]
    text = [
        "state:\n"
        + state
        + "\nquestion:\n"
        + question["instructions"]
        + "\noption:\n"
        + options[i]["description"]
        for i in order
    ]
    reordered = [identities[i] for i in order]
    return {
        "id": record["id"],
        "texts": text,
        "options": reordered,
        "gold": target["selected_id"],
        "label": reordered.index(target["selected_id"]),
        "point": question["point"],
        "group_id": record.get("_lineage_group", hashlib.sha256(state.encode()).hexdigest()),
        "language": "zh" if any("\u4e00" <= c <= "\u9fff" for c in state) else "other",
        "long_state": len(state) > 3000,
        "state_digest": hashlib.sha256(state.encode()).hexdigest(),
    }


def run(path: Path) -> None:
    manifest = json.loads(path.read_text())
    signal.alarm(manifest["max_wall_seconds"])
    resource = importlib.import_module("resource")
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (manifest["max_output_bytes"], manifest["max_output_bytes"])
    )
    common = runpy.run_path("/common.py")
    atomic, sha = common["atomic_json"], common["sha"]
    metrics = runpy.run_path("/decision_metrics.py")["summarize"]
    torch = importlib.import_module("torch")
    hf = importlib.import_module("transformers")
    peft = importlib.import_module("peft")
    safe = importlib.import_module("safetensors.torch")
    args = manifest["command"]
    torch.manual_seed(args["seed"])
    torch.use_deterministic_algorithms(True)
    device = manifest["device"]
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("requested_device_unavailable")
    tokenizer = hf.AutoTokenizer.from_pretrained(
        "/base", local_files_only=True, trust_remote_code=False, use_fast=True
    )
    encoder = hf.AutoModel.from_pretrained(
        "/base",
        local_files_only=True,
        trust_remote_code=False,
        use_safetensors=True,
        torch_dtype=torch.float32,
    )
    encoder = peft.get_peft_model(
        encoder,
        peft.LoraConfig(
            r=args["rank"],
            lora_alpha=2 * args["rank"],
            target_modules="all-linear",
            lora_dropout=0.0,
            task_type="FEATURE_EXTRACTION",
        ),
    )
    head = torch.nn.Linear(encoder.config.hidden_size, 1)
    encoder.to(device)
    head.to(device)
    parameters = [p for p in encoder.parameters() if p.requires_grad] + list(head.parameters())
    optimizer = torch.optim.AdamW(parameters, lr=args["learning_rate"])
    runtime = {
        "device": device,
        "cuda_devices": torch.cuda.device_count() if device == "cuda" else 0,
        "versions": {
            n: importlib.import_module("importlib.metadata").version(n)
            for n in ("torch", "transformers", "peft", "safetensors")
        },
    }
    datasets = {}
    for scope, expected in manifest["data_sha256"].items():
        source = path.parent / (scope + ".jsonl")
        if sha(source) != expected:
            raise ValueError("data_digest_changed")
        datasets[scope] = [json.loads(line) for line in source.read_text().splitlines()]
    if not datasets.get("train"):
        raise ValueError("training_data_empty")
    limit = min(
        args["max_sequence_length"],
        getattr(encoder.config, "max_position_embeddings", args["max_sequence_length"]),
    )

    def logits(row: dict[str, Any]) -> Any:
        inputs = tokenizer(row["texts"], padding=True, truncation=False, return_tensors="pt")
        if inputs["input_ids"].shape[1] > limit:
            raise ValueError("decision_state_too_long_no_truncation")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        encoded = encoder(**inputs).last_hidden_state
        mask = inputs["attention_mask"].unsqueeze(-1)
        pooled = (encoded * mask).sum(1) / mask.sum(1).clamp(min=1)
        return head(pooled).squeeze(-1)

    output = Path("/output")
    completed = 0
    resume = manifest.get("resume")
    if resume:
        root = path.parent / "resume"
        if resume["manifest_digest"] != manifest["plan_digest"]:
            raise ValueError("resume_lineage_changed")
        for name, expected in resume["files"].items():
            if sha(root / name) != expected:
                raise ValueError("checkpoint_corrupt")
        with importlib.import_module("safetensors").safe_open(
            str(root / "state.safetensors"), framework="pt", device="cpu"
        ) as handle:
            if json.loads(handle.metadata().get("runtime", "{}")) != runtime:
                raise ValueError("resume_runtime_changed")
        weights = safe.load_file(str(root / "adapter.safetensors"), device=device)
        peft.set_peft_model_state_dict(
            encoder, {k[8:]: v for k, v in weights.items() if k.startswith("encoder.")}
        )
        head.load_state_dict({k[5:]: v for k, v in weights.items() if k.startswith("head.")})
        state = safe.load_file(str(root / "state.safetensors"))
        torch.set_rng_state(state["rng"])
        if device == "cuda":
            torch.cuda.set_rng_state_all(
                [state[f"cuda_rng_{i}"] for i in range(torch.cuda.device_count())]
            )
        for i, parameter in enumerate(parameters):
            keys = ("step", "exp_avg", "exp_avg_sq")
            present = [f"optimizer_{i}_{k}" in state for k in keys]
            if any(present) and not all(present):
                raise ValueError("optimizer_checkpoint_incomplete")
            if all(present):
                for k in keys:
                    optimizer.state[parameter][k] = state[f"optimizer_{i}_{k}"].to(
                        device if k != "step" else "cpu"
                    )
        completed = resume["step"]

    def measure(save_predictions: bool = False) -> dict[str, Any]:
        encoder.eval()
        head.eval()
        results = {}
        with torch.no_grad():
            for scope, records in datasets.items():
                rows = []
                for record in records:
                    row = encode_choice(record)
                    probabilities = torch.softmax(logits(row), 0).cpu().tolist()
                    best = max(range(len(probabilities)), key=lambda i: probabilities[i])
                    selected = (
                        row["options"][best]
                        if probabilities[best] >= args["abstention_threshold"]
                        else None
                    )
                    rows.append(
                        {
                            **row,
                            "selected_id": selected,
                            "probabilities": dict(zip(row["options"], probabilities, strict=True)),
                        }
                    )
                if save_predictions and scope == "validation":
                    atomic(
                        output / "predictions-validation.json",
                        [
                            {
                                "sample_id": row["id"],
                                "point": row["point"],
                                "option_ids": row["options"],
                                "probabilities": row["probabilities"],
                                "selected_id": row["selected_id"],
                                "teacher_selected_id": row["gold"],
                                "observed_state_digest": row["state_digest"],
                                "adopted": False,
                            }
                            for row in rows
                        ],
                    )
                by_point = {
                    point: metrics([r for r in rows if r["point"] == point])
                    for point in sorted({r["point"] for r in rows})
                }
                results[scope] = {
                    "overall": metrics(rows),
                    "by_point": by_point,
                    "by_language": {
                        language: metrics([r for r in rows if r["language"] == language])
                        for language in sorted({r["language"] for r in rows})
                    },
                    "long_state": metrics([r for r in rows if r["long_state"]]),
                }
        return results

    baseline = measure() if completed == 0 else manifest["baseline"]
    atomic(output / "baseline.json", baseline)
    start = time.monotonic()
    for step in range(completed, args["steps"]):
        encoder.train()
        head.train()
        record = datasets["train"][step % len(datasets["train"])]
        original = encode_choice(record)
        order = list(range(len(original["options"])))
        random.Random(args["seed"] + step).shuffle(order)
        row = encode_choice(record, order)
        optimizer.zero_grad(set_to_none=True)
        value = torch.nn.functional.cross_entropy(
            logits(row).unsqueeze(0), torch.tensor([row["label"]], device=device)
        )
        if not math.isfinite(float(value.item())):
            raise ValueError("non_finite_loss")
        value.backward()
        torch.nn.utils.clip_grad_norm_(parameters, 1.0)
        optimizer.step()
        folder_name = "step-" + str(step + 1).zfill(8)
        folder = output / (folder_name + ".tmp")
        folder.mkdir()
        weights = {
            "encoder." + k: v.detach().cpu().contiguous()
            for k, v in peft.get_peft_model_state_dict(encoder).items()
        }
        weights.update(
            {"head." + k: v.detach().cpu().contiguous() for k, v in head.state_dict().items()}
        )
        safe.save_file(weights, str(folder / "adapter.safetensors"))
        state = {"rng": torch.get_rng_state()}
        if device == "cuda":
            state.update({f"cuda_rng_{i}": v for i, v in enumerate(torch.cuda.get_rng_state_all())})
        for i, parameter in enumerate(parameters):
            state.update(
                {
                    f"optimizer_{i}_{k}": v.detach().cpu().contiguous()
                    for k, v in optimizer.state[parameter].items()
                }
            )
        safe.save_file(
            state,
            str(folder / "state.safetensors"),
            metadata={"runtime": json.dumps(runtime, sort_keys=True)},
        )
        checkpoint = {
            "step": step + 1,
            "files": {p.name: sha(p) for p in folder.iterdir()},
            "manifest_digest": manifest["plan_digest"],
        }
        atomic(folder / "checkpoint.json", checkpoint)
        folder.rename(output / folder_name)
        atomic(output / "progress.json", {"checkpoint": checkpoint, "folder": folder_name})
    atomic(
        output / "result.json",
        {
            "protocol": "auton-training-worker-v1",
            "plan_digest": manifest["plan_digest"],
            "metrics": {
                "baseline_seed": baseline,
                "candidate": measure(True),
                "runtime": runtime,
                "wall_seconds": time.monotonic() - start,
                "teacher_comparison": "qualified_KEEP_agreement_only",
                "prior_champion": "not_evaluated",
                "independent_gold_evaluated": False,
                "agent_closed_loop_evaluated": False,
                "shadow_adopted": False,
                "deployment_precision": "float32",
                "quantized_deployment_evaluated": False,
            },
        },
    )


if __name__ == "__main__":
    try:
        run(Path(sys.argv[1]))
    except Exception as error:
        # Error types only; no state, training material or credential output.
        temp = Path("/output/error.json")
        temp.write_text(json.dumps({"error_type": type(error).__name__}))
        raise SystemExit(1) from None
