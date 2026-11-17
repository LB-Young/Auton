from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field

from auton.model.contracts import Contract


class GenomeConfig(Contract):
    directory: Path = Path(".auton_local/genome")


class Project(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=100)
    instructions: str = Field(default="", max_length=10000)


class Asset(Contract):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["skill", "prompt", "role", "knowledge", "document", "memory"]
    content: str = Field(min_length=1, max_length=32000)
    origin: Literal["user_explicit", "inferred", "external"]
    source: str = Field(min_length=1, max_length=1000)
    parents: tuple[str, ...] = Field(default=(), max_length=20)
    expires_at: AwareDatetime | None = None
    untrusted: Literal[True] = True


class AssetRecord(Contract):
    asset: Asset
    status: Literal["active", "candidate", "revoked"]
    promoted_from: str | None = None


class Catalog(Contract):
    project: Project
    audit: dict[str, str] = Field(default_factory=dict)
    records: dict[str, AssetRecord] = Field(default_factory=dict)
    schema_version: Literal[1] = 1


class Revision(Contract):
    project: Project
    revision: str | None
    candidates_revision: str | None
    assets: tuple[AssetRecord, ...]
    candidates: tuple[AssetRecord, ...]
    excluded: dict[str, str] = Field(default_factory=dict)


class Snapshot(Contract):
    id: str
    project_id: str
    revision: str
    instructions: str
    assets: tuple[Asset, ...]
    scope: Literal["project"] = "project"
    untrusted: Literal[True] = True


class VersionInfo(Contract):
    revision: str
    name: str
    status: str
    origin: str
    digest: str
