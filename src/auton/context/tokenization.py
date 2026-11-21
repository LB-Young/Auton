import hashlib
import threading
from pathlib import Path

from tokenizers import Tokenizer  # type: ignore[import-untyped]

from auton.context.ports import TokenCounterPort
from auton.context.vendor import flash, pro
from auton.kernel.ports import ApplicationError
from auton.model.contracts import ModelRequest

BINDINGS = {
    "deepseek-flash": (
        "deepseek-ai/DeepSeek-V4.1-Flash",
        "314113f8a7dadb388215396ba5fbee2c610a04d6",
        "6a15814dd25c934028034531da744c689f87ff21",
        6367257,
    ),
    "deepseek-v4-pro": (
        "deepseek-ai/DeepSeek-V4-Pro",
        "b5968e9190ef611bbf34a7229255be88a0e937c1",
        "628e3364caad11bdf9e67cea06eae7878122811d",
        6367146,
    ),
}


class OfficialTokenCounter:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._loaded: dict[str, Tokenizer] = {}
        self._lock = threading.RLock()

    def count(self, request: ModelRequest) -> tuple[int, str]:
        binding = BINDINGS.get(request.model_id)
        if binding is None:
            raise ApplicationError(
                409, "tokenizer_model_unknown", "No pinned tokenizer/encoding for this model"
            )
        repo, revision, blob, size = binding
        with self._lock:
            if request.model_id not in self._loaded:
                path = self.directory / request.model_id / "tokenizer.json"
                if not path.is_file():
                    raise ApplicationError(
                        503, "tokenizer_missing", "Install the pinned context tokenizers"
                    )
                raw = path.read_bytes()
                if (
                    len(raw) != size
                    or hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != blob
                ):
                    raise ApplicationError(
                        409,
                        "tokenizer_digest_mismatch",
                        "Tokenizer bytes differ from the pinned official object",
                    )
                tokenizer = Tokenizer.from_file(str(path))
                tokenizer.no_truncation()
                tokenizer.no_padding()
                self._loaded[request.model_id] = tokenizer
            messages = [message.wire() for message in request.messages]
            if request.tools:
                messages[0]["tools"] = [
                    {"type": "function", "function": tool.model_dump()} for tool in request.tools
                ]
            encoder = flash if request.model_id == "deepseek-flash" else pro
            try:
                encoded = encoder.encode_messages(messages, thinking_mode="chat")
                if not isinstance(encoded, str):
                    raise ValueError("Only text encoding is enabled")
                count = len(
                    self._loaded[request.model_id].encode(encoded, add_special_tokens=False).ids
                )
            except (ValueError, AssertionError, KeyError, TypeError) as error:
                raise ApplicationError(
                    409,
                    "template_incompatible",
                    "Messages are incompatible with the pinned official text encoding",
                ) from error
            return count, repo + "@" + revision + ":chat"


class FixtureTokenCounter:
    def count(self, request: ModelRequest) -> tuple[int, str]:
        # Explicit test-only byte fixture, never a fallback for a real model.
        return len(request.model_dump_json().encode()), "fixture-byte-v1"


class TokenCounterFactory:
    def create(self, directory: Path) -> TokenCounterPort:
        return OfficialTokenCounter(directory)
