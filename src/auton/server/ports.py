from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from auton.demo.ports import ConversationPort
from auton.kernel.modules import ModuleDescriptor


class BootstrapResponse(BaseModel):
    profile: str
    demo: bool
    implementation: str
    persistence: Literal["memory-only"] = "memory-only"
    modules: list[ModuleDescriptor]


class HealthResponse(BaseModel):
    status: Literal["ready", "starting", "stopped"]
    profile: str


@dataclass(frozen=True)
class ServerDependencies:
    conversation: ConversationPort | None
    modules: list[ModuleDescriptor]
    implementation: str
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]]
    is_ready: Callable[[], bool]
