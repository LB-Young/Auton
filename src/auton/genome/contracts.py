from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

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


class ArenaSnapshotCommand(Contract):
    base_snapshot_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_id: str = Field(min_length=1, max_length=100)
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["patch", "ablation"]
    replacement_content: str | None = Field(default=None, min_length=1, max_length=32000)

    @model_validator(mode="after")
    def matching_mode(self) -> "ArenaSnapshotCommand":
        if (self.mode == "patch") != (self.replacement_content is not None):
            raise ValueError("Only patch accepts replacement content")
        return self


class Snapshot(Contract):
    purpose: Literal["runtime", "optimization_arena"] = "runtime"
    parent_snapshot_id: str | None = None
    arena_asset_id: str | None = None
    arena_mode: Literal["patch", "ablation"] | None = None
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
