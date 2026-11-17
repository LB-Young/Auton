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
