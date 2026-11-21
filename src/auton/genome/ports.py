from collections.abc import Awaitable, Callable
from typing import Protocol

from auton.constitution.config import Principal
from auton.genome.contracts import (
    ArenaSnapshotCommand,
    Asset,
    AssetReleaseCommand,
    AssetReleaseState,
    Project,
    Revision,
    Snapshot,
    VersionInfo,
)
from auton.kernel.ports import LifecycleHandle


class AssetReadPort(Protocol):
    async def resolve_for_goal(
        self,
        principal: Principal,
        project_id: str,
        goal_id: str,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> Snapshot: ...
    async def diff(
        self, principal: Principal, project_id: str, asset_id: str, revision: str
    ) -> str: ...
    async def projects(self, principal: Principal) -> list[Project]: ...
    async def view(self, principal: Principal, project_id: str) -> Revision: ...
    async def history(
        self, principal: Principal, project_id: str, asset_id: str
    ) -> list[VersionInfo]: ...
    async def resolve(self, principal: Principal, project_id: str) -> Snapshot: ...
    async def snapshot(
        self,
        principal: Principal,
        project_id: str,
        snapshot_id: str,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> Snapshot: ...


class AssetArenaPort(Protocol):
    async def arena_snapshot(
        self, principal: Principal, project_id: str, command: ArenaSnapshotCommand
    ) -> Snapshot: ...


class AssetProposalPort(Protocol):
    async def propose(
        self, principal: Principal, project_id: str, asset: Asset, expected: str | None
    ) -> Revision: ...


class AssetPublishPort(Protocol):
    async def create_project(self, principal: Principal, project: Project) -> Revision: ...
    async def promote(
        self,
        principal: Principal,
        project_id: str,
        asset_id: str,
        expected: str,
        candidates_revision: str,
    ) -> Revision: ...
    async def revoke(
        self, principal: Principal, project_id: str, asset_id: str, expected: str
    ) -> Revision: ...
    async def rollback(
        self, principal: Principal, project_id: str, asset_id: str, revision: str, expected: str
    ) -> Revision: ...


class AssetReleasePort(Protocol):
    def bind_release_guard(self, guard: Callable[[Principal, str], Awaitable[None]]) -> None: ...
    async def release_asset(
        self, principal: Principal, command: AssetReleaseCommand
    ) -> AssetReleaseState: ...
    async def control_release_asset(
        self,
        principal: Principal,
        project_id: str,
        release_id: str,
        action: str,
        expected_version: int,
    ) -> AssetReleaseState: ...


class GenomePort(
    LifecycleHandle,
    AssetReadPort,
    AssetArenaPort,
    AssetProposalPort,
    AssetPublishPort,
    AssetReleasePort,
    Protocol,
):
    pass
