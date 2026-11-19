"""Optional deployment-side HF/PEFT runtime. Heavy dependencies are image-only.

The JSON envelope parser is explicit, fail-closed, and must be evaluated with the
selected model. This server is never started by the Auton application or trainer.
"""

import argparse
import hashlib
import hmac
import importlib
import importlib.metadata
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from auton.model.config import ModelSpec
from auton.model.contracts import ModelRequest


def verified_files(directory: Path, files: dict[str, str]) -> None:
    if not files:
        raise ValueError("empty_runtime_file_manifest")
    for name, expected in files.items():
        path = directory / name
        if path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("unsafe_runtime_file")
        checksum = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(chunk)
        if checksum.hexdigest() != expected:
            raise ValueError("runtime_file_digest_mismatch")
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
    if actual != set(files):
        raise ValueError("runtime_unmanifested_files")


def parse_output(text: str, request: ModelRequest, parser: str = "tagged_json") -> dict[str, Any]:
    blocks = (
        re.findall(r"<tool_call>(.*?)</tool_call>", text, flags=re.DOTALL)
        if parser == "tagged_json"
        else ([text] if request.tools and text.lstrip().startswith("{") else [])
    )
    permitted = {tool.name for tool in request.tools}
    calls = []
    for index, block in enumerate(blocks):
        call = json.loads(block)
        if (
            not isinstance(call, dict)
            or set(call) != {"name", "arguments"}
            or call["name"] not in permitted
            or not isinstance(call["arguments"], dict)
        ):
            raise ValueError("runtime_tool_envelope_invalid")
        calls.append({"id": "local-" + request.digest[:16] + "-" + str(index), **call})
    if parser == "tagged_json" and (
        text.count("<tool_call>") != len(blocks) or text.count("</tool_call>") != len(blocks)
    ):
        raise ValueError("runtime_tool_envelope_truncated")
    if request.tool_choice == "none" and calls:
        raise ValueError("runtime_tools_forbidden")
    if request.tool_choice == "required" and not calls:
        raise ValueError("runtime_tool_required")
    content = (
        re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL).strip()
        if blocks and parser == "tagged_json"
        else ""
        if calls
        else text
    )
    return {"content": content, "tool_calls": calls}


class HFRuntime:
    def __init__(self, config: dict[str, Any]) -> None:
        self.spec = ModelSpec.model_validate(config["spec"])
        if self.spec.provider != "local" or self.spec.quantization != "none":
            raise ValueError("reference_runtime_requires_local_unquantized_model")
        if self.spec.runtime_revision != "auton-hf-json-v1":
            raise ValueError("runtime_revision_mismatch")
        base, adapter = Path(config["base_directory"]), Path(config["adapter_directory"])
        verified_files(base, config["base_files"])
        from auton.kernel.documents import digest

        base_manifest = config["base_manifest"]
        if (
            base_manifest.get("files") != config["base_files"]
            or digest(base_manifest) != self.spec.base_manifest_digest
            or base_manifest.get("revision") != self.spec.base_revision
            or base_manifest.get("tool_parser") != self.spec.local_tool_parser
            or base_manifest.get("template_sha256") != self.spec.template_revision
        ):
            raise ValueError("base_manifest_binding_mismatch")
        verified_files(adapter, config["adapter_files"])
        if config["adapter_files"].get("adapter.safetensors") != self.spec.adapter_revision:
            raise ValueError("adapter_manifest_mismatch")
        fingerprint = digest(
            {
                "model_id": self.spec.id,
                "bundle_id": self.spec.declared_revision,
                "base_files": config["base_files"],
                "adapter_files": config["adapter_files"],
                "template_revision": self.spec.template_revision,
                "runtime_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "device": config["device"],
                "quantization": "none",
                "tool_parser": self.spec.local_tool_parser,
                "lora_rank": self.spec.local_lora_rank,
                "dtype": "float32",
                "libraries": {
                    name: importlib.metadata.version(name)
                    for name in ("torch", "transformers", "peft", "safetensors", "tokenizers")
                },
            }
        )
        if fingerprint != self.spec.expected_fingerprint:
            raise ValueError("runtime_fingerprint_mismatch: expected " + fingerprint)
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        peft = importlib.import_module("peft")
        self.torch = torch
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(
            str(base), local_files_only=True, trust_remote_code=False
        )
        template = self.tokenizer.chat_template
        if (
            not isinstance(template, str)
            or hashlib.sha256(template.encode()).hexdigest() != self.spec.template_revision
        ):
            raise ValueError("runtime_template_digest_mismatch")
        # M18 checkpoints contain safe tensor state, not a PEFT save_pretrained directory.
        # Reconstruct the exact M18 LoRA recipe, then load the pinned adapter bytes.
        self.model = peft.get_peft_model(
            transformers.AutoModelForCausalLM.from_pretrained(
                str(base),
                local_files_only=True,
                trust_remote_code=False,
                use_safetensors=True,
                torch_dtype=torch.float32,
            ),
            peft.LoraConfig(
                r=self.spec.local_lora_rank,
                lora_alpha=2 * self.spec.local_lora_rank,
                target_modules="all-linear",
                lora_dropout=0.0,
                task_type="CAUSAL_LM",
            ),
        )
        state = importlib.import_module("safetensors.torch").load_file(
            str(adapter / "adapter.safetensors"), device="cpu"
        )
        expected = peft.get_peft_model_state_dict(self.model)
        if set(state) != set(expected) or any(state[k].shape != expected[k].shape for k in state):
            raise ValueError("runtime_adapter_layout_mismatch")
        peft.set_peft_model_state_dict(self.model, state)
        self.model.to(config["device"]).eval()
        self.lock = threading.Lock()
        # Real tensor operation before ready; no download and no synthetic quality claim.
        with torch.inference_mode():
            warm = self.tokenizer("warmup", return_tensors="pt").to(self.model.device)
            self.model(**warm)
        self.manifest = {
            "model_id": self.spec.id,
            "bundle_id": self.spec.declared_revision,
            "base_revision": self.spec.base_revision,
            "base_manifest_digest": self.spec.base_manifest_digest,
            "adapter_sha256": self.spec.adapter_revision,
            "template_revision": self.spec.template_revision,
            "runtime_revision": self.spec.runtime_revision,
            "quantization": self.spec.quantization,
            "fingerprint": fingerprint,
            "ready": True,
        }

    def execute(self, body: dict[str, Any], generate: bool) -> dict[str, Any]:
        request = ModelRequest.model_validate(body["request"])
        if request.digest != body["request_digest"] or request.model_id != self.spec.id:
            raise ValueError("runtime_request_binding_mismatch")
        messages: list[dict[str, Any]] = [dict(m.wire()) for m in request.messages]
        for message in messages:
            if message.get("tool_calls"):
                for call in message["tool_calls"]:
                    call["function"]["arguments"] = json.loads(call["function"]["arguments"])
        tools = [
            {"type": "function", "function": tool.model_dump(mode="json")} for tool in request.tools
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tools=tools, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        encoded = self.tokenizer(text, add_special_tokens=False, return_tensors="pt")
        tokens = int(encoded["input_ids"].shape[-1])
        result = {"request_digest": request.digest, "fingerprint": self.spec.expected_fingerprint}
        if not generate:
            return {**result, "tokens": tokens}
        if tokens + request.max_output_tokens > self.spec.context_tokens:
            raise ValueError("runtime_context_exceeded")
        with self.lock, self.torch.inference_mode():
            encoded = encoded.to(self.model.device)
            output = self.model.generate(
                **encoded,
                max_new_tokens=request.max_output_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )[0][tokens:]
        if len(output) == request.max_output_tokens:
            raise ValueError("runtime_output_budget_exhausted")
        parsed = parse_output(
            self.tokenizer.decode(output, skip_special_tokens=True),
            request,
            self.spec.local_tool_parser,
        )
        return {
            **result,
            **parsed,
            "model_id": self.spec.id,
            "input_tokens": tokens,
            "output_tokens": len(output),
            "finish_reason": "tool_calls" if parsed["tool_calls"] else "stop",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    secret = os.environ[config["spec"]["local_secret_reference"]]
    if len(secret) < 32:
        raise ValueError("runtime_bearer_secret_too_short")
    runtime = HFRuntime(config)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass  # Never log prompts, generated bytes, or credentials.

        def handle_request(self, post: bool) -> None:
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + secret):
                self.send_error(401)
                return
            try:
                if not post and self.path == "/auton/manifest":
                    result = runtime.manifest
                elif post and self.path in {"/auton/token-count", "/auton/generate"}:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 1024 * 1024:
                        raise ValueError("runtime_request_size")
                    result = runtime.execute(
                        json.loads(self.rfile.read(size)), self.path.endswith("generate")
                    )
                else:
                    self.send_error(404)
                    return
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(422, "Runtime request rejected")

        def do_GET(self) -> None:
            self.handle_request(False)

        def do_POST(self) -> None:
            self.handle_request(True)

    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
