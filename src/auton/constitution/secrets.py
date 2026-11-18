import logging
import os
import re
from pathlib import Path
from typing import Protocol

from dotenv import dotenv_values
from pydantic import JsonValue, SecretStr

from auton.kernel.ports import ApplicationError


class SecretStorePort(Protocol):
    def get(self, name: str) -> SecretStr: ...


class LocalSecretStore:
    def __init__(self, path: Path) -> None:
        # No global environment mutation, interpolation, or public serialization.
        self._values = {**dotenv_values(path, interpolate=False), **os.environ}

    def get(self, name: str) -> SecretStr:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,99}", name):
            raise ValueError("Only environment variable names are accepted as secret references")
        value = self._values.get(name)
        if not value:
            raise ApplicationError(
                503, "credential_missing", f"Configure the secret reference {name}"
            )
        return SecretStr(value)

    def __repr__(self) -> str:
        return "LocalSecretStore(<redacted>)"


class SecretStoreFactory:
    def create(self, path: Path = Path(".env")) -> SecretStorePort:
        return LocalSecretStore(path)


class Redactor:
    def __init__(self, secrets: tuple[SecretStr, ...] = ()) -> None:
        self._secrets = tuple(value.get_secret_value() for value in secrets)

    def text(self, value: str) -> str:
        for secret in self._secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return re.sub(r"\bsk-[a-zA-Z0-9_-]{12,}\b", "[REDACTED]", value)

    def redact(self, value: JsonValue) -> JsonValue:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {
                key: "[REDACTED]"
                if any(
                    part in key.lower()
                    for part in (
                        "authorization",
                        "api_key",
                        "password",
                        "secret",
                        "access_token",
                    )
                )
                else self.redact(item)
                for key, item in value.items()
            }
        return value


class RedactingFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__("%(levelname)s auton %(message)s")
        self.redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self.redactor.text(super().format(record))


class LoggerFactory:
    def create(self, redactor: Redactor) -> logging.Logger:
        # App-owned logger, not a mutation of process-global logging configuration.
        logger = logging.Logger("auton", logging.INFO)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(RedactingFormatter(redactor))
        logger.addHandler(handler)
        return logger


class StreamingRedactor:
    """Keep an overlap so a credential split across chunks is never published."""

    def __init__(self, redactor: Redactor, secrets: tuple[SecretStr, ...] = ()) -> None:
        self.redactor = redactor
        self.secrets = tuple(
            value.get_secret_value() for value in secrets if value.get_secret_value()
        )
        self.overlap = max((len(value) - 1 for value in self.secrets), default=2)
        self.overlap = max(2, self.overlap)
        self.buffer = ""

    def feed(self, value: str) -> str:
        self.buffer += value
        cut = len(self.buffer)
        for secret in self.secrets:
            for size in range(min(len(secret) - 1, len(self.buffer)), 0, -1):
                if self.buffer.endswith(secret[:size]):
                    cut = min(cut, len(self.buffer) - size)
                    break
        for prefix in ("s", "sk"):
            if self.buffer.endswith(prefix):
                cut = min(cut, len(self.buffer) - len(prefix))
        unfinished = re.search(r"\bsk-[a-zA-Z0-9_-]*\Z", self.buffer)
        if unfinished:
            cut = min(cut, unfinished.start())
        spans = [
            (m.start(), m.end()) for m in re.finditer(r"\bsk-[a-zA-Z0-9_-]{12,}\b", self.buffer)
        ]
        for secret in self.secrets:
            start = self.buffer.find(secret)
            while start >= 0:
                spans.append((start, start + len(secret)))
                start = self.buffer.find(secret, start + 1)
        for start, end in sorted(spans):
            if start < cut < end:
                cut = end
        text, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return self.redactor.text(text)

    def finish(self) -> str:
        text = self.redactor.text(self.buffer)
        self.buffer = ""
        return text
