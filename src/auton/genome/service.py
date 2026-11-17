import asyncio
import hashlib
from dataclasses import dataclass

import anyio

from auton.constitution.config import ActionRequest, Principal
from auton.constitution.ports import PolicyControlPort
from auton.constitution.secrets import Redactor
from auton.genome.contracts import (
    Asset,
    AssetRecord,
    Catalog,
    Project,
    Revision,
    Snapshot,
    VersionInfo,
)
from auton.genome.policy import MemoryPolicy
from auton.genome.repository import GitAssetRepository, error
from auton.kernel.events import Event, EventScope
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


@dataclass(frozen=True)
class GenomeDependencies:
    policy: PolicyControlPort
    events: EventLogPort
    runtime: RuntimeDependencies


class AssetResolver:
    def __init__(
        self, repo: GitAssetRepository, policy: MemoryPolicy, deps: GenomeDependencies
    ) -> None:
        self.repo, self.policy, self.deps = repo, policy, deps

    def event_id(self, principal: Principal, project_id: str, snapshot_id: str) -> str:
        return (
            "genome-snapshot:"
            + hashlib.sha256(
                (principal.owner + "\0" + project_id + "\0" + snapshot_id).encode()
            ).hexdigest()
        )

    async def snapshot(self, principal: Principal, project_id: str, snapshot_id: str) -> Snapshot:
        stored = await self.deps.events.lookup(self.event_id(principal, project_id, snapshot_id))
        if stored is None:
            raise error("snapshot_not_found", "No project-owned snapshot")
        result = Snapshot.model_validate(stored.event.payload["snapshot"])
        _, current = await anyio.to_thread.run_sync(
            lambda: self.repo.read(principal.owner, project_id)
        )
        if current is None or any(
            not self.policy.visible(current, a, self.deps.runtime.now()) for a in result.assets
        ):
            raise error(
                "snapshot_revoked", "Snapshot contains withdrawn, expired or unavailable sources"
            )
        return result

    async def resolve(self, principal: Principal, project_id: str) -> Snapshot:
        revision, current = await anyio.to_thread.run_sync(
            lambda: self.repo.read(principal.owner, project_id)
        )
        if revision is None or current is None:
            raise error("project_not_found", "No owned project")
        assets = tuple(
            r.asset
            for key, r in sorted(current.records.items())
            if self.policy.visible(current, r.asset, self.deps.runtime.now())
        )
        draft = Snapshot(
            id="",
            project_id=project_id,
            revision=revision,
            instructions=current.project.instructions,
            assets=assets,
        )
        identity = hashlib.sha256(draft.model_dump_json().encode()).hexdigest()
        result = draft.model_copy(update={"id": identity})
        event_id = self.event_id(principal, project_id, identity)
        if await self.deps.events.lookup(event_id) is None:
            await self.deps.events.append(
                [
                    Event(
                        event_id=event_id,
                        kind="genome.asset_used",
                        source="runtime",
                        timestamp=self.deps.runtime.now(),
                        scope=EventScope(project_id=project_id),
                        payload={
                            "snapshot": result.model_dump(mode="json"),
                            "asset_ids": [a.id for a in assets],
                            "permission_scope": "single-owner-project",
                        },
                    )
                ]
            )
        return await self.snapshot(principal, project_id, identity)


class ResolverFactory:
    def create(
        self, repo: GitAssetRepository, policy: MemoryPolicy, deps: GenomeDependencies
    ) -> AssetResolver:
        return AssetResolver(repo, policy, deps)


class GenomeService:
    def __init__(
        self,
        repo: GitAssetRepository,
        policy: MemoryPolicy,
        resolver: AssetResolver,
        deps: GenomeDependencies,
    ) -> None:
        self.repo, self.policy, self.resolver, self.deps = repo, policy, resolver, deps
        self._lock = asyncio.Lock()
        self.ready = False

    async def start(self) -> None:
        self.ready = True

    async def close(self) -> None:
        self.ready = False

    def authorize(self, principal: Principal, action: str) -> None:
        if not self.ready:
            raise error("genome_not_ready", "Asset service has not started")
        decision = self.deps.policy.preview(
            ActionRequest(
                principal=principal, goal_id="asset-control", goal_revision=1, action=action
            )
        )
        if decision.outcome != "allow":
            raise error(
                "asset_policy_denied", "Fixed policy does not authorize this asset operation"
            )

    def human(self, principal: Principal) -> None:
        if not self.ready:
            raise error("genome_not_ready", "Asset service has not started")
        self.authorize(principal, "asset.publish")
        if principal.role != "user":
            raise error("human_required", "Only a human publish Port may change official assets")

    async def read(
        self,
        principal: Principal,
        project_id: str,
        branch: str = "main",
        revision: str | None = None,
    ) -> tuple[str | None, Catalog | None]:
        if not self.ready:
            raise error("genome_not_ready", "Asset service has not started")
        self.authorize(principal, "asset.read")
        return await anyio.to_thread.run_sync(
            lambda: self.repo.read(principal.owner, project_id, branch, revision)
        )

    async def write(
        self,
        principal: Principal,
        project_id: str,
        branch: str,
        expected: str | None,
        catalog: Catalog,
        action: str,
    ) -> str:
        catalog = catalog.model_copy(
            update={
                "audit": {
                    "action": action,
                    "actor_role": principal.role,
                    "timestamp": self.deps.runtime.now().isoformat(),
                }
            }
        )
        revision = await anyio.to_thread.run_sync(
            lambda: self.repo.write(principal.owner, project_id, branch, expected, catalog)
        )
        # Git commits are immutable audit revisions. Journal acknowledgement is separate;
        # on storage failure the caller reloads the Git head, never blindly repeats a publish.
        event_id = (
            "genome-change:"
            + hashlib.sha256((principal.owner + project_id + revision).encode()).hexdigest()
        )
        await self.deps.events.append(
            [
                Event(
                    event_id=event_id,
                    kind="genome.changed",
                    source="runtime",
                    timestamp=self.deps.runtime.now(),
                    scope=EventScope(project_id=project_id),
                    payload={
                        "revision": revision,
                        "branch": branch,
                        "action": action,
                        "actor_role": principal.role,
                    },
                )
            ]
        )
        return revision

    async def projects(self, principal: Principal) -> list[Project]:
        self.authorize(principal, "asset.read")

        def load() -> list[Project]:
            root = self.repo.config.directory / hashlib.sha256(principal.owner.encode()).hexdigest()
            if not root.exists():
                return []
            results = []
            for path in sorted(root.glob("*.git")):
                _, catalog = self.repo.read(principal.owner, path.name[:-4])
                if catalog:
                    results.append(catalog.project)
            return results

        return await anyio.to_thread.run_sync(load)

    async def view(self, principal: Principal, project_id: str) -> Revision:
        revision, current = await self.read(principal, project_id)
        if current is None:
            raise error("project_not_found", "No owned project")
        learning, candidates = await self.read(principal, project_id, "learning")
        now = self.deps.runtime.now()
        pending = []
        if candidates:
            for record in candidates.records.values():
                existing = current.records.get(record.asset.id)
                if existing and (existing.status == "revoked" or existing.asset == record.asset):
                    continue
                if record.asset.expires_at and record.asset.expires_at <= now:
                    continue
                if any(
                    parent in current.records
                    and not self.policy.visible(current, current.records[parent].asset, now)
                    for parent in record.asset.parents
                ):
                    continue
                pending.append(record)
        return Revision(
            project=current.project,
            revision=revision,
            candidates_revision=learning,
            assets=tuple(
                r for r in current.records.values() if self.policy.visible(current, r.asset, now)
            ),
            candidates=tuple(pending),
            excluded={
                key: (
                    "revoked"
                    if r.status == "revoked"
                    else "expired"
                    if r.asset.expires_at and r.asset.expires_at <= now
                    else "source_unavailable"
                )
                for key, r in current.records.items()
                if not self.policy.visible(current, r.asset, now)
            },
        )

    async def create_project(self, principal: Principal, project: Project) -> Revision:
        async with self._lock:
            self.human(principal)
            if Redactor().text(project.model_dump_json()) != project.model_dump_json():
                raise error(
                    "credential_in_input", "Do not store credentials as project instructions"
                )
            revision, _ = await self.read(principal, project.id)
            if revision:
                raise error("project_exists", "A project with this identity already exists")
            await self.write(
                principal, project.id, "main", None, Catalog(project=project), "project.create"
            )
            return await self.view(principal, project.id)

    async def propose(
        self, principal: Principal, project_id: str, asset: Asset, expected: str | None
    ) -> Revision:
        async with self._lock:
            self.authorize(principal, "asset.propose")
            if principal.role not in {"user", "evolution"}:
                raise error("proposal_role_denied", "This reader cannot modify learning candidates")
            if principal.role != "user" and asset.origin == "user_explicit":
                raise error(
                    "origin_impersonation",
                    "Inferred memory cannot impersonate an explicit user statement",
                )
            if Redactor().text(asset.model_dump_json()) != asset.model_dump_json():
                raise error("credential_in_input", "Do not store credentials as asset content")
            _, main = await self.read(principal, project_id)
            if main is None:
                raise error("project_not_found", "No owned project")
            revision, learning = await self.read(principal, project_id, "learning")
            if revision != expected:
                raise error("asset_conflict", "Candidate branch changed")
            records = dict(learning.records) if learning else {}
            records[asset.id] = AssetRecord(asset=asset, status="candidate")
            await self.write(
                principal,
                project_id,
                "learning",
                expected,
                Catalog(project=main.project, records=records),
                "asset.propose",
            )
            return await self.view(principal, project_id)

    async def promote(
        self,
        principal: Principal,
        project_id: str,
        asset_id: str,
        expected: str,
        candidates_revision: str,
    ) -> Revision:
        async with self._lock:
            self.human(principal)
            head, main = await self.read(principal, project_id)
            learning, candidates = await self.read(principal, project_id, "learning")
            if (
                main is None
                or candidates is None
                or head != expected
                or learning != candidates_revision
            ):
                raise error("asset_conflict", "Project or learning revision changed")
            if asset_id not in candidates.records:
                raise error("asset_not_found", "No such learning candidate")
            asset = candidates.records[asset_id].asset
            self.policy.publishable(main, asset, self.deps.runtime.now())
            records = dict(main.records)
            records[asset_id] = AssetRecord(asset=asset, status="active", promoted_from=learning)
            await self.write(
                principal,
                project_id,
                "main",
                expected,
                Catalog(project=main.project, records=records),
                "asset.promote",
            )
            return await self.view(principal, project_id)

    async def revoke(
        self, principal: Principal, project_id: str, asset_id: str, expected: str
    ) -> Revision:
        async with self._lock:
            self.human(principal)
            revision, main = await self.read(principal, project_id)
            if main is None or revision != expected:
                raise error("asset_conflict", "Official revision changed")
            if asset_id not in main.records:
                raise error("asset_not_found", "No such official asset")
            revoked = {asset_id}
            while True:
                expanded = revoked | {
                    key for key, r in main.records.items() if set(r.asset.parents) & revoked
                }
                if expanded == revoked:
                    break
                revoked = expanded
            records = dict(main.records)
            for identity in revoked:
                record = records[identity]
                records[identity] = record.model_copy(
                    update={
                        "status": "revoked",
                        "asset": record.asset.model_copy(
                            update={"content": "[revoked]", "source": "revoked", "name": identity}
                        ),
                    }
                )
            await self.write(
                principal,
                project_id,
                "main",
                expected,
                Catalog(project=main.project, records=records),
                "asset.revoke",
            )
            return await self.view(principal, project_id)

    async def rollback(
        self, principal: Principal, project_id: str, asset_id: str, revision: str, expected: str
    ) -> Revision:
        async with self._lock:
            self.human(principal)
            head, main = await self.read(principal, project_id)
            _, old = await self.read(principal, project_id, "main", revision)
            if head != expected or main is None or old is None or asset_id not in old.records:
                raise error("asset_conflict", "Rollback source or current revision does not match")
            asset = old.records[asset_id].asset
            self.policy.publishable(main, asset, self.deps.runtime.now())
            records = dict(main.records)
            records[asset_id] = AssetRecord(
                asset=asset, status="active", promoted_from="rollback:" + revision
            )
            await self.write(
                principal,
                project_id,
                "main",
                expected,
                Catalog(project=main.project, records=records),
                "asset.rollback",
            )
            return await self.view(principal, project_id)

    async def history(
        self, principal: Principal, project_id: str, asset_id: str
    ) -> list[VersionInfo]:
        await self.view(principal, project_id)
        revisions = await anyio.to_thread.run_sync(
            lambda: self.repo.history(principal.owner, project_id)
        )
        result = []
        for revision in revisions:
            _, catalog = await self.read(principal, project_id, "main", revision)
            if catalog and asset_id in catalog.records:
                record = catalog.records[asset_id]
                result.append(
                    VersionInfo(
                        revision=revision,
                        name=record.asset.name,
                        status=record.status,
                        origin=record.asset.origin,
                        digest=hashlib.sha256(record.asset.content.encode()).hexdigest(),
                    )
                )
        return result

    async def resolve(self, principal: Principal, project_id: str) -> Snapshot:
        await self.view(principal, project_id)
        return await self.resolver.resolve(principal, project_id)

    async def snapshot(self, principal: Principal, project_id: str, snapshot_id: str) -> Snapshot:
        await self.read(principal, project_id)
        return await self.resolver.snapshot(principal, project_id, snapshot_id)

    async def diff(
        self, principal: Principal, project_id: str, asset_id: str, revision: str
    ) -> str:
        import difflib

        _, current = await self.read(principal, project_id)
        _, previous = await self.read(principal, project_id, "main", revision)
        if (
            current is None
            or previous is None
            or asset_id not in current.records
            or asset_id not in previous.records
        ):
            raise error("asset_not_found", "No comparable owned asset versions")
        asset = current.records[asset_id].asset
        old = previous.records[asset_id].asset
        if not self.policy.visible(
            current, asset, self.deps.runtime.now()
        ) or not self.policy.visible(current, old, self.deps.runtime.now()):
            raise error("asset_revoked", "Revoked or expired versions are unavailable")
        return "".join(
            difflib.unified_diff(
                old.content.splitlines(keepends=True),
                asset.content.splitlines(keepends=True),
                fromfile=revision + "/" + asset_id,
                tofile="current/" + asset_id,
            )
        )
