"""Goal-sticky asset rollout metadata, independent of the untrusted learning branch."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from auton.constitution.config import Principal
from auton.genome.contracts import AssetReleaseState
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort
from auton.model.contracts import Contract
from auton.model.publication_contracts import input_language


class AssetProfileConfig(Contract):
    directory: Path
    max_documents: int = 10000

    @property
    def digest(self) -> str:
        return digest({"schema": "asset-release-profiles-v1"})


class AssetReleaseProfiles:
    def __init__(self, directory: Path, events: EventLogPort, runtime: RuntimeDependencies) -> None:
        self.guard: Callable[[Principal, str], Awaitable[None]] | None = None
        self.store = VersionedDocumentStore(
            AssetProfileConfig(directory=directory), events, runtime, False, "asset_profiles"
        )

    async def start(self) -> None:
        await self.store.start()

    async def close(self) -> None:
        await self.store.close()

    async def get(self, principal: Principal, identity: str) -> AssetReleaseState | None:
        value = await self.store.get("release", principal.owner, identity)
        return AssetReleaseState.model_validate(value) if value else None

    async def put(
        self, principal: Principal, value: AssetReleaseState, expected: int | None
    ) -> None:
        await self.store.put(
            "release", principal.owner, value.id, value.model_dump(mode="json"), expected
        )

    async def project(self, principal: Principal, project: str) -> tuple[AssetReleaseState, ...]:
        values = await self.store.list("release", principal.owner)
        return tuple(
            sorted(
                (AssetReleaseState.model_validate(v) for v in values if v["project_id"] == project),
                key=lambda r: r.sequence,
            )
        )

    async def selected(
        self,
        principal: Principal,
        project: str,
        goal: str,
        goal_text: str = "",
        data_domain: str = "local-only",
    ) -> tuple[AssetReleaseState, ...]:
        records = await self.project(principal, project)
        latest: dict[str, AssetReleaseState] = {}
        for record in records:
            latest[record.command.asset_id] = record
        selected = []
        for asset_id, current in latest.items():
            assignment_id = key(principal.owner, "goal:" + project + ":" + goal + ":" + asset_id)
            old = await self.store.get("assignment", principal.owner, assignment_id)
            if old:
                chosen = (
                    await self.get(principal, str(old["release_id"])) if old["release_id"] else None
                )
            else:
                fraction = (
                    int(key(principal.owner, project + "\0" + goal + "\0" + asset_id)[:8], 16) % 100
                )
                chosen = (
                    current
                    if current.status == "active"
                    and fraction < current.command.percentage
                    and input_language(goal_text) in current.command.languages
                    and data_domain in current.command.data_domains
                    else None
                )
                await self.store.put(
                    "assignment",
                    principal.owner,
                    assignment_id,
                    {
                        "id": assignment_id,
                        "version": 0,
                        "project_id": project,
                        "release_id": chosen.id if chosen else None,
                    },
                    None,
                )
            if chosen:
                if chosen.status == "revoked":
                    raise ApplicationError(
                        409,
                        "asset_release_revoked",
                        "Pinned asset release was revoked; resume only at a safe checkpoint",
                    )
                selected.append(chosen)
        return tuple(selected)

    async def validate(
        self,
        principal: Principal,
        release_ids: tuple[str, ...],
        goal_text: str | None = None,
        data_domain: str | None = None,
    ) -> None:
        for identity in release_ids:
            saved = await self.get(principal, identity)
            if saved is not None and (
                (goal_text is not None and input_language(goal_text) not in saved.command.languages)
                or (data_domain is not None and data_domain not in saved.command.data_domains)
            ):
                raise ApplicationError(
                    409, "asset_release_scope", "Current task is outside approved asset scope"
                )
            if saved is None or saved.status == "revoked":
                raise ApplicationError(
                    409, "asset_release_revoked", "Pinned asset release no longer applies"
                )
            if self.guard is None:
                raise ApplicationError(
                    503,
                    "asset_release_guard_missing",
                    "Independent release source guard is required",
                )
            await self.guard(principal, identity)
