from typing import Protocol

from auton.constitution.config import Principal
from auton.genome.contracts import Asset, Project, Revision, Snapshot, VersionInfo
from auton.kernel.ports import LifecycleHandle


class AssetReadPort(Protocol):
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
        self, principal: Principal, project_id: str, snapshot_id: str
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


class GenomePort(LifecycleHandle, AssetReadPort, AssetProposalPort, AssetPublishPort, Protocol):
    pass
