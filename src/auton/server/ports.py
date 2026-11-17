import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from auton.constitution.config import PublicPolicy
from auton.constitution.ports import PolicyControlPort
from auton.demo.ports import ConversationPort
from auton.genome.ports import GenomePort
from auton.judgment.ports import JudgmentPort
from auton.kernel.events import StorageInfo
from auton.kernel.modules import ModuleDescriptor
from auton.model.ports import ModelGatewayPort
from auton.tools.ports import ToolHostPort


class BootstrapResponse(BaseModel):
    profile: str
    demo: bool
    implementation: str
    persistence: Literal["memory-only"] = "memory-only"
    modules: list[ModuleDescriptor]
    event_storage: StorageInfo
    policy: PublicPolicy


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
    storage: Callable[[], StorageInfo]
    genome: GenomePort
    tools: ToolHostPort
    judgment: JudgmentPort
    models: ModelGatewayPort
    control: PolicyControlPort
    redact: Callable[[str], str]
    logger: logging.Logger
