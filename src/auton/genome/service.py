import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import anyio

from auton.constitution.config import ActionRequest, Principal
from auton.constitution.ports import PolicyControlPort
from auton.constitution.secrets import Redactor
from auton.genome.contracts import (
    ArenaSnapshotCommand,
    Asset,
    AssetRecord,
    AssetReleaseCommand,
    AssetReleaseState,
    Catalog,
    Project,
    Revision,
    Snapshot,
    VersionInfo,
)
from auton.genome.policy import MemoryPolicy
from auton.genome.release_profiles import AssetReleaseProfiles
from auton.genome.repository import GitAssetRepository, error
from auton.kernel.documents import digest, key
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
        self.profiles = AssetReleaseProfiles(
            repo.config.directory / "release-profiles", deps.events, deps.runtime
        )

    def event_id(
        self,
        principal: Principal,
        project_id: str,
        snapshot_id: str,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> str:
        return (
            "genome-snapshot:"
            + hashlib.sha256(
                (principal.owner + "\0" + project_id + "\0" + snapshot_id).encode()
            ).hexdigest()
        )

    async def snapshot(
        self,
        principal: Principal,
        project_id: str,
        snapshot_id: str,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> Snapshot:
        stored = await self.deps.events.lookup(self.event_id(principal, project_id, snapshot_id))
        if stored is None:
            raise error("snapshot_not_found", "No project-owned snapshot")
        result = Snapshot.model_validate(stored.event.payload["snapshot"])
        await self.profiles.validate(principal, result.release_ids, goal_text, data_domain)
        if result.purpose == "optimization_arena":
            if not result.parent_snapshot_id or result.parent_snapshot_id == result.id:
                raise error("arena_source_invalid", "Arena requires an ordinary parent snapshot")
            parent = await self.snapshot(principal, project_id, result.parent_snapshot_id)
            if parent.purpose != "runtime":
                raise error("arena_source_invalid", "Nested candidate arenas are forbidden")
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

    async def resolve(
        self,
        principal: Principal,
        project_id: str,
        goal_id: str | None = None,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> Snapshot:
        goal_key = key(principal.owner, "snapshot-goal:" + project_id + ":" + (goal_id or ""))
        if goal_id:
            pinned = await self.profiles.store.get("goal_snapshot", principal.owner, goal_key)
            if pinned:
                if pinned["scope_digest"] != digest(
                    {"goal": goal_text, "data_domain": data_domain}
                ):
                    raise error("asset_goal_scope_changed", "Pinned goal input scope is immutable")
                return await self.snapshot(principal, project_id, str(pinned["snapshot_id"]))
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
        states = await self.profiles.project(principal, project_id) if goal_id else ()
        for state in states:
            present = next((a for a in assets if a.id == state.target.id), None)
            if (
                state.status == "revoked"
                and state.applied_revision
                and present
                and digest(present.model_dump(mode="json"))
                == digest(state.target.model_dump(mode="json"))
            ):
                raise error(
                    "asset_rollback_pending", "Wait for rollback reconciliation before new goals"
                )
        releases = (
            await self.profiles.selected(principal, project_id, goal_id, goal_text, data_domain)
            if goal_id
            else ()
        )
        current_assets = {a.id: a for a in assets}
        latest_states = {state.command.asset_id: state for state in states}
        for asset_id, state in latest_states.items():
            present = current_assets.get(asset_id)
            if (
                state.applied_revision
                and state.id not in {r.id for r in releases}
                and present
                and digest(present.model_dump(mode="json"))
                == digest(state.target.model_dump(mode="json"))
            ):
                self.policy.publishable(current, state.parent, self.deps.runtime.now())
                current_assets[asset_id] = state.parent
        for released in releases:
            active = current_assets.get(released.target.id)
            if active is None or (
                hashlib.sha256(active.content.encode()).hexdigest()
                != released.command.content_sha256
                and revision != released.command.expected_revision
            ):
                raise error("asset_release_source_changed", "Published asset parent changed")
            self.policy.publishable(current, released.target, self.deps.runtime.now())
            current_assets[released.target.id] = released.target
        assets = tuple(current_assets[k] for k in sorted(current_assets))
        draft = Snapshot(
            release_ids=tuple(r.id for r in releases),
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
        if goal_id:
            await self.profiles.store.put(
                "goal_snapshot",
                principal.owner,
                goal_key,
                {
                    "id": goal_key,
                    "version": 0,
                    "snapshot_id": identity,
                    "scope_digest": digest({"goal": goal_text, "data_domain": data_domain}),
                },
                None,
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
        await self.resolver.profiles.start()
        self.ready = True

    async def close(self) -> None:
        self.ready = False
        await self.resolver.profiles.close()

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
                    **catalog.audit,
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

    async def resolve_for_goal(
        self,
        principal: Principal,
        project_id: str,
        goal_id: str,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> Snapshot:
        return await self.resolver.resolve(principal, project_id, goal_id, goal_text, data_domain)

    def bind_release_guard(self, guard: Callable[[Principal, str], Awaitable[None]]) -> None:
        self.resolver.profiles.guard = guard

    async def release_asset(
        self, principal: Principal, command: AssetReleaseCommand
    ) -> AssetReleaseState:
        async with self._lock:
            self.human(principal)
            approval = await self.deps.events.lookup(command.approval_event_id)
            if (
                approval is None
                or approval.event.kind != "release.approved"
                or approval.event.scope.project_id != command.project_id
                or approval.event.payload.get("release_id") != command.release_id
                or approval.event.payload.get("owner_key") != key(principal.owner, "release-owner")
                or approval.event.payload.get("candidate_sha256") != command.content_sha256
                or approval.event.payload.get("target_digest")
                != digest(
                    {"candidate_sha256": command.content_sha256, "asset_id": command.asset_id}
                )
                or approval.event.payload.get("percentage") != command.percentage
                or approval.event.payload.get("languages") != list(command.languages)
                or approval.event.payload.get("data_domains") != list(command.data_domains)
            ):
                raise error(
                    "release_approval_missing",
                    "Exact independent asset approval receipt is required",
                )
            old = await self.resolver.profiles.get(principal, command.release_id)
            if old:
                if old.command != command:
                    raise error("release_asset_conflict", "Release command is immutable")
                return old
            head, main = await self.read(principal, command.project_id)
            learning, candidates = await self.read(principal, command.project_id, "learning")
            if (
                main is None
                or candidates is None
                or learning != command.candidates_revision
                or command.asset_id not in main.records
                or command.candidate_id not in candidates.records
            ):
                raise error(
                    "release_asset_source_changed", "Owned source/candidate revisions changed"
                )
            parent = main.records[command.asset_id].asset
            candidate = candidates.records[command.candidate_id].asset
            if (
                not candidate.source.startswith("evolution-proposal:")
                or hashlib.sha256(candidate.content.encode()).hexdigest() != command.content_sha256
            ):
                raise error(
                    "release_asset_digest_changed",
                    "Learning candidate is not the approved evolution patch",
                )
            target = parent.model_copy(
                update={
                    "content": candidate.content,
                    "source": candidate.source,
                    "origin": "inferred",
                }
            )
            receipt_key = "release:" + command.release_id
            already = main.audit.get(receipt_key) == digest(command.model_dump(mode="json"))
            if not already and head != command.expected_revision:
                raise error("release_asset_source_changed", "Formal asset revision changed")
            if already and parent.content != candidate.content:
                raise error(
                    "release_asset_superseded", "A previously applied release was changed later"
                )
            if already:
                _, original = await self.read(
                    principal, command.project_id, "main", command.expected_revision
                )
                if original is None or command.asset_id not in original.records:
                    raise error(
                        "release_parent_missing", "Original compatible asset revision is required"
                    )
                parent = original.records[command.asset_id].asset
                target = parent.model_copy(
                    update={
                        "content": candidate.content,
                        "source": candidate.source,
                        "origin": "inferred",
                    }
                )
            self.policy.publishable(main, target, self.deps.runtime.now())
            applied = head if already else None
            if command.percentage == 100 and not already:
                records = dict(main.records)
                records[command.asset_id] = AssetRecord(
                    asset=target, status="active", promoted_from=learning
                )
                applied = await self.write(
                    principal,
                    command.project_id,
                    "main",
                    head,
                    Catalog(
                        project=main.project,
                        records=records,
                        audit={**main.audit, receipt_key: digest(command.model_dump(mode="json"))},
                    ),
                    "asset.release",
                )
            result = AssetReleaseState(
                sequence=max(
                    (
                        r.sequence
                        for r in await self.resolver.profiles.project(principal, command.project_id)
                    ),
                    default=0,
                )
                + 1,
                id=command.release_id,
                project_id=command.project_id,
                command=command,
                parent=parent,
                target=target,
                applied_revision=applied,
            )
            await self.resolver.profiles.put(principal, result, None)
            return result

    async def control_release_asset(
        self,
        principal: Principal,
        project_id: str,
        release_id: str,
        action: str,
        expected_version: int,
    ) -> AssetReleaseState:
        async with self._lock:
            self.human(principal)
            record = await self.resolver.profiles.get(principal, release_id)
            if (
                record is None
                or record.project_id != project_id
                or record.version not in {expected_version, expected_version + 1}
            ):
                raise error("release_asset_conflict", "Asset release pointer changed")
            state = "paused" if action == "pause" else "revoked"
            updated = record.model_copy(update={"status": state, "version": record.version + 1})
            if record.status != state:
                await self.resolver.profiles.put(principal, updated, record.version)
            else:
                updated = record
            if action != "pause" and record.applied_revision:
                head, main = await self.read(principal, project_id)
                if (
                    main is not None
                    and main.audit.get("rollback:" + record.id) == record.command.content_sha256
                ):
                    return updated
                if (
                    main is None
                    or record.command.asset_id not in main.records
                    or digest(main.records[record.command.asset_id].asset.model_dump(mode="json"))
                    != digest(record.target.model_dump(mode="json"))
                ):
                    raise error(
                        "release_rollback_conflict",
                        "Do not overwrite a subsequent human asset change",
                    )
                self.policy.publishable(main, record.parent, self.deps.runtime.now())
                records = dict(main.records)
                records[record.command.asset_id] = AssetRecord(
                    asset=record.parent,
                    status="active",
                    promoted_from="release-rollback:" + record.id,
                )
                await self.write(
                    principal,
                    project_id,
                    "main",
                    head,
                    Catalog(
                        project=main.project,
                        records=records,
                        audit={
                            **main.audit,
                            "rollback:" + record.id: record.command.content_sha256,
                        },
                    ),
                    "asset.release.rollback",
                )
            return updated

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
            if asset.source.startswith("evolution-proposal:"):
                raise error(
                    "release_control_required",
                    "Evolution candidates require the independent release control plane",
                )
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

    async def snapshot(
        self,
        principal: Principal,
        project_id: str,
        snapshot_id: str,
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> Snapshot:
        await self.read(principal, project_id)
        return await self.resolver.snapshot(
            principal, project_id, snapshot_id, goal_text, data_domain
        )

    async def arena_snapshot(
        self, principal: Principal, project_id: str, command: ArenaSnapshotCommand
    ) -> Snapshot:
        async with self._lock:
            self.authorize(principal, "asset.propose")
            if principal.role not in {"user", "evolution"}:
                raise error(
                    "arena_role_denied", "Only the user/evolution control plane prepares arenas"
                )
            base = await self.snapshot(principal, project_id, command.base_snapshot_id)
            if base.purpose != "runtime":
                raise error(
                    "arena_source_invalid", "Arena derives from an ordinary frozen snapshot"
                )
            target = next((asset for asset in base.assets if asset.id == command.asset_id), None)
            if target is None or target.kind != "skill":
                raise error(
                    "arena_target_invalid", "Initial arena can only vary one existing Skill"
                )
            if (
                hashlib.sha256(target.content.encode()).hexdigest()
                != command.expected_content_sha256
            ):
                raise error(
                    "arena_parent_changed", "Target content does not match the chosen parent"
                )
            if command.replacement_content == target.content:
                raise error("arena_no_change", "Patch must change the selected Skill")
            if (
                command.replacement_content
                and Redactor().text(command.replacement_content) != command.replacement_content
            ):
                raise error("credential_in_input", "Do not put credentials into arena content")
            assets = tuple(
                asset
                if asset.id != target.id
                else asset.model_copy(
                    update={
                        "content": command.replacement_content,
                        "origin": "inferred",
                        "source": "optimization-arena:" + command.base_snapshot_id,
                    }
                )
                for asset in base.assets
                if asset.id != target.id or command.mode == "patch"
            )
            draft = base.model_copy(
                update={
                    "id": "",
                    "assets": assets,
                    "purpose": "optimization_arena",
                    "parent_snapshot_id": base.id,
                    "arena_asset_id": target.id,
                    "arena_mode": command.mode,
                }
            )
            result = draft.model_copy(
                update={"id": hashlib.sha256(draft.model_dump_json().encode()).hexdigest()}
            )
            event_id = self.resolver.event_id(principal, project_id, result.id)
            if await self.deps.events.lookup(event_id) is None:
                await self.deps.events.append(
                    [
                        Event(
                            event_id=event_id,
                            kind="genome.arena_prepared",
                            source="runtime",
                            timestamp=self.deps.runtime.now(),
                            scope=EventScope(project_id=project_id),
                            payload={
                                "snapshot": result.model_dump(mode="json"),
                                "permission_scope": "single-owner-development-arena",
                            },
                        )
                    ]
                )
            return await self.snapshot(principal, project_id, result.id)

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
