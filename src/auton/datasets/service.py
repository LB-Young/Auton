import asyncio
import hashlib
import os
from pathlib import Path
from typing import Literal

import anyio

from auton.constitution.config import Principal
from auton.constitution.secrets import Redactor
from auton.datasets.contracts import (
    DataGrant,
    DataGrantCommand,
    DatasetArtifact,
    DatasetBuild,
    DatasetConfig,
    DatasetSnapshot,
    DatasetStatus,
    DatasetWithdrawal,
    ExportCommand,
    RejectedSubject,
    TrainingExample,
)
from auton.datasets.curation import DatasetCuratorFactory
from auton.datasets.dependencies import DatasetDependencies
from auton.datasets.groups import GroupLedger
from auton.datasets.rendering import LearningRecordRenderer
from auton.datasets.sources import DatasetSourceReader
from auton.datasets.store import DatasetStore, digest, key
from auton.kernel.ports import ApplicationError


class Datasets:
    def __init__(
        self,
        config: DatasetConfig,
        deps: DatasetDependencies,
        store: DatasetStore,
        reader: DatasetSourceReader,
        groups: GroupLedger,
        curators: DatasetCuratorFactory,
        renderer: LearningRecordRenderer,
    ) -> None:
        (
            self.config,
            self.deps,
            self.store,
            self.reader,
            self.groups,
            self.curators,
            self.renderer,
        ) = config, deps, store, reader, groups, curators, renderer
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        await self.store.start()

    async def close(self) -> None:
        async with self.lock:
            await self.store.close()

    def user(self, principal: Principal) -> None:
        self.store.database()
        if principal.role != "user":
            raise ApplicationError(
                403, "dataset_user_required", "Only users control dataset purposes and grants"
            )

    def status(self) -> DatasetStatus:
        return DatasetStatus(
            config_digest=self.config.digest,
            source_revision=self.config.source_revision,
            max_sources=self.config.max_sources,
        )

    async def load_grant(self, principal: Principal, identity: str) -> DataGrant:
        value = await self.store.get("grant", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "dataset_grant_missing", "No owned training grant")
        return DataGrant.model_validate(value)

    async def grant(self, principal: Principal, command: DataGrantCommand) -> DataGrant:
        self.user(principal)
        async with self.lock:
            identity = key(principal.owner, "grant:" + command.request_id)
            old = await self.store.get("grant", principal.owner, identity)
            if old:
                saved = DataGrant.model_validate(old)
                if saved.command != command:
                    raise ApplicationError(
                        409, "dataset_grant_conflict", "Grant request has different immutable scope"
                    )
                return saved
            if Redactor().text(command.model_dump_json()) != command.model_dump_json():
                raise ApplicationError(
                    403,
                    "dataset_credentials_detected",
                    "Do not put credentials in rights attestations",
                )
            await self.deps.assets.resolve(principal, command.project_id)
            for run_id in command.run_ids:
                run = await self.deps.agent.get(principal, run_id)
                if run.command.project_id != command.project_id:
                    raise ApplicationError(
                        404, "dataset_grant_scope", "Grant source belongs to another project"
                    )
            await self.store.capacity(principal.owner, 32)
            result = DataGrant(id=identity, command=command)
            await self.store.put(
                "grant", principal.owner, identity, result.model_dump(mode="json"), None
            )
            return result

    async def grants(self, principal: Principal, project: str) -> tuple[DataGrant, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            DataGrant.model_validate(v)
            for v in await self.store.list("grant", principal.owner)
            if v["command"]["project_id"] == project
        )

    async def withdrawn(self, principal: Principal, run_id: str) -> bool:
        return (
            await self.store.get(
                "withdrawal", principal.owner, key(principal.owner, "run:" + run_id)
            )
            is not None
        )

    async def build(self, principal: Principal, command: DatasetBuild) -> DatasetSnapshot:
        self.user(principal)
        identity = key(principal.owner, "build:" + command.request_id)
        async with self.lock:
            existing = await self.store.get("snapshot", principal.owner, identity)
            if existing:
                saved = DatasetSnapshot.model_validate(existing)
                if saved.command != command:
                    raise ApplicationError(
                        409, "dataset_build_conflict", "Build has different frozen source scope"
                    )
                return await self.current(principal, saved)
            if len(command.subjects) > self.config.max_sources:
                raise ApplicationError(
                    429, "dataset_source_limit", "Build exceeds bounded source count"
                )
            grant = await self.load_grant(principal, command.grant_id)
            if grant.command.project_id != command.project_id:
                raise ApplicationError(404, "dataset_grant_scope", "No owned project grant")
            await self.store.capacity(principal.owner, 4 * len(command.subjects) + 32)
            sources = []
            rejected = []
            for ref in command.subjects:
                try:
                    if await self.withdrawn(principal, ref.run_id):
                        raise ApplicationError(
                            403, "dataset_source_withdrawn", "Source was withdrawn"
                        )
                    sources.append(await self.reader.read(principal, command, ref, grant))
                except ApplicationError as error:
                    rejected.append(RejectedSubject(run_id=ref.run_id, reasons=(error.code,)))
            curator = self.curators.create(command.kind, self.deps)
            examples: list[TrainingExample] = []
            if command.kind == "router":
                try:
                    examples.extend(await curator.curate(principal, command, tuple(sources)))
                except ApplicationError as error:
                    rejected.extend(
                        RejectedSubject(run_id=s.ref.run_id, reasons=(error.code,)) for s in sources
                    )
            else:
                for source in sources:
                    try:
                        batch = await curator.curate(principal, command, (source,))
                        if not batch:
                            raise ApplicationError(
                                409,
                                "dataset_no_verified_target",
                                "No independently verified target action is available",
                            )
                        examples.extend(batch)
                    except ApplicationError as error:
                        rejected.append(
                            RejectedSubject(run_id=source.ref.run_id, reasons=(error.code,))
                        )
            unique = {e.id: e for e in examples}
            bounded = tuple(unique.values())
            if len(bounded) > self.config.max_examples or any(
                len(e.model_dump_json().encode()) > self.config.max_example_bytes for e in bounded
            ):
                raise ApplicationError(
                    429,
                    "dataset_example_limit",
                    "Reject oversized examples; never truncate tool pairs or original constraints",
                )
            assignment = await self.groups.assign(principal, bounded, True)
            if assignment.rejected_ids:
                rejected.extend(
                    RejectedSubject(run_id=p.run_id, reasons=("dataset_group_split_conflict",))
                    for e in bounded
                    if e.id in assignment.rejected_ids
                    for p in e.proofs
                )
            examples = sorted(assignment.examples, key=lambda example: example.id)
            status: Literal["ready", "blocked", "engineering_only"] = (
                "engineering_only"
                if any(e.engineering_only for e in examples)
                else "ready"
                if examples
                else "blocked"
            )
            snapshot = DatasetSnapshot(
                id=identity,
                command=command,
                config_digest=self.config.digest,
                grant_digest=digest(grant.model_dump(mode="json")),
                status=status,
                examples=tuple(examples),
                rejected=tuple(rejected),
                content_digest=digest([e.model_dump(mode="json") for e in examples]),
                source_groups=len({e.group_id for e in examples}),
                training_ready=status == "ready" and any(e.split == "train" for e in examples),
                created_at=self.deps.runtime.now().timestamp(),
            )
            if len(snapshot.model_dump_json().encode()) > self.config.max_snapshot_bytes:
                raise ApplicationError(
                    429, "dataset_snapshot_limit", "Bounded snapshot byte grant exceeded"
                )
            await self.store.put(
                "snapshot", principal.owner, identity, snapshot.model_dump(mode="json"), None
            )
            return await self.current(principal, snapshot)

    async def current(self, principal: Principal, snapshot: DatasetSnapshot) -> DatasetSnapshot:
        reasons = []
        if snapshot.config_digest != self.config.digest:
            reasons.append("dataset_configuration_changed")
        grant = await self.load_grant(principal, snapshot.command.grant_id)
        if grant.revoked or digest(grant.model_dump(mode="json")) != snapshot.grant_digest:
            reasons.append("dataset_grant_changed_or_withdrawn")
        if (
            digest([e.model_dump(mode="json") for e in snapshot.examples])
            != snapshot.content_digest
        ):
            raise ApplicationError(
                409, "dataset_manifest_corrupt", "Immutable snapshot content digest differs"
            )
        refs = {r.run_id: r for r in snapshot.command.subjects}
        proofs = {p.run_id: p for e in snapshot.examples for p in e.proofs}
        for run_id, proof in proofs.items():
            if await self.withdrawn(principal, run_id):
                reasons.append("dataset_source_withdrawn")
                continue
            try:
                source = await self.reader.read(principal, snapshot.command, refs[run_id], grant)
                if (
                    source.proof.model_copy(
                        update={
                            "review_id": proof.review_id,
                            "review_version": proof.review_version,
                        }
                    )
                    != proof
                ):
                    reasons.append("dataset_source_evidence_changed")
                if proof.review_id:
                    reviewed = await self.deps.reviews.get(principal, proof.review_id)
                    if (
                        not reviewed.positive_training_eligible
                        or reviewed.version != proof.review_version
                    ):
                        reasons.append("dataset_KEEP_revoked_or_changed")
            except ApplicationError as error:
                reasons.append("source_unavailable:" + error.code)
        if snapshot.examples:
            assignment = await self.groups.assign(principal, snapshot.examples, False)
            if assignment.rejected_ids or {e.id: e.group_id for e in assignment.examples} != {
                e.id: e.group_id for e in snapshot.examples
            }:
                reasons.append("dataset_split_lineage_changed")
        if reasons:
            return snapshot.model_copy(
                update={
                    "status": "blocked",
                    "training_ready": False,
                    "current_evidence_valid": False,
                    "invalidation_reasons": tuple(dict.fromkeys(reasons)),
                }
            )
        return snapshot

    async def get(self, principal: Principal, identity: str) -> DatasetSnapshot:
        self.user(principal)
        value = await self.store.get("snapshot", principal.owner, identity)
        if value is None:
            raise ApplicationError(404, "dataset_snapshot_missing", "No owned dataset snapshot")
        return await self.current(principal, DatasetSnapshot.model_validate(value))

    async def list(self, principal: Principal, project: str) -> tuple[DatasetSnapshot, ...]:
        self.user(principal)
        await self.deps.assets.resolve(principal, project)
        return tuple(
            [
                await self.current(principal, DatasetSnapshot.model_validate(v))
                for v in await self.store.list("snapshot", principal.owner)
                if v["command"]["project_id"] == project
            ]
        )

    async def withdraw(self, principal: Principal, command: DatasetWithdrawal) -> tuple[str, ...]:
        self.user(principal)
        async with self.lock:
            receipt_id = "withdraw:" + command.request_id
            operation_id = key(principal.owner, receipt_id)
            replay = await self.store.receipt(
                principal.owner,
                receipt_id,
                "withdrawal_operation",
                operation_id,
                command.model_dump(mode="json"),
            )
            if replay:
                operation = await self.store.get(
                    "withdrawal_operation", principal.owner, operation_id
                )
                assert operation is not None
                return tuple(str(v) for v in operation["affected"])
            if command.grant_id:
                grant = await self.load_grant(principal, command.grant_id)
                if grant.command.project_id != command.project_id:
                    raise ApplicationError(404, "dataset_grant_scope", "No owned grant")
                if not grant.revoked:
                    updated = grant.model_copy(
                        update={"version": grant.version + 1, "revoked": True}
                    )
                    await self.store.put(
                        "grant",
                        principal.owner,
                        grant.id,
                        updated.model_dump(mode="json"),
                        grant.version,
                    )
            else:
                assert command.run_id
                run = await self.deps.agent.get(principal, command.run_id)
                if run.command.project_id != command.project_id:
                    raise ApplicationError(404, "dataset_source_scope", "No owned source")
            identity = key(
                principal.owner,
                ("run:" + command.run_id) if command.run_id else ("grant:" + str(command.grant_id)),
            )
            old = await self.store.get("withdrawal", principal.owner, identity)
            if old is None:
                await self.store.put(
                    "withdrawal",
                    principal.owner,
                    identity,
                    {
                        "id": identity,
                        "version": 0,
                        "project_id": command.project_id,
                        "command": command.model_dump(mode="json"),
                    },
                    None,
                )
            snapshots = await self.store.list("snapshot", principal.owner)
            affected = tuple(
                str(v["id"])
                for v in snapshots
                if v["command"]["project_id"] == command.project_id
                and (
                    v["command"]["grant_id"] == command.grant_id
                    if command.grant_id
                    else any(
                        p["run_id"] == command.run_id for e in v["examples"] for p in e["proofs"]
                    )
                )
            )
            await self.store.put(
                "withdrawal_operation",
                principal.owner,
                operation_id,
                {
                    "id": operation_id,
                    "version": 0,
                    "project_id": command.project_id,
                    "command": command.model_dump(mode="json"),
                    "affected": list(affected),
                },
                None,
                receipt_id,
                command.model_dump(mode="json"),
            )
            return affected

    def artifact_path(self, identity: str) -> Path:
        root = self.config.directory / "exports"
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink():
            raise ApplicationError(
                503, "dataset_export_path", "Private export directory cannot be a symlink"
            )
        root.chmod(0o700)
        return root / (identity + ".jsonl")

    async def export(
        self, principal: Principal, identity: str, command: ExportCommand
    ) -> DatasetArtifact:
        self.user(principal)
        async with self.lock:
            snapshot = await self.get(principal, identity)
            if (
                snapshot.content_digest != command.expected_content_digest
                or not snapshot.current_evidence_valid
                or snapshot.status != "ready"
            ):
                raise ApplicationError(
                    409,
                    "dataset_not_exportable",
                    "Export requires a current approved runtime snapshot; "
                    "fixtures are engineering only",
                )
            selected = tuple(e for e in snapshot.examples if e.split == command.split)
            if not selected or command.purpose == "local_training" and not snapshot.training_ready:
                raise ApplicationError(
                    409,
                    "dataset_split_empty_or_unqualified",
                    "The requested purpose has no qualified records",
                )
            content = self.renderer.encode(selected)
            if len(content) > self.config.max_export_bytes:
                raise ApplicationError(429, "dataset_export_limit", "Export byte grant exceeded")
            export_id = key(principal.owner, "export:" + command.request_id)
            result = DatasetArtifact(
                id=export_id,
                snapshot_id=identity,
                command=command,
                sha256=hashlib.sha256(content).hexdigest(),
                size=len(content),
                example_count=len(selected),
                manifest_digest=snapshot.content_digest,
            )
            old = await self.store.get("artifact", principal.owner, export_id)
            if old:
                if DatasetArtifact.model_validate(old) != result:
                    raise ApplicationError(
                        409,
                        "dataset_export_conflict",
                        "Export request has a different source manifest or purpose",
                    )
            path = self.artifact_path(export_id)

            def write() -> None:
                try:
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    if path.is_symlink() or path.read_bytes() != content:
                        raise ApplicationError(
                            409,
                            "dataset_export_collision",
                            "Do not overwrite an unrelated artifact",
                        ) from None
                    return
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())

            await anyio.to_thread.run_sync(write)
            if not (await self.get(principal, identity)).current_evidence_valid:
                raise ApplicationError(
                    409,
                    "dataset_source_changed_during_export",
                    "Source changed before the artifact was committed",
                )
            if old is None:
                await self.store.put(
                    "artifact", principal.owner, export_id, result.model_dump(mode="json"), None
                )
            return result

    async def read_artifact(
        self, principal: Principal, identity: str
    ) -> tuple[DatasetArtifact, bytes]:
        self.user(principal)
        async with self.lock:
            value = await self.store.get("artifact", principal.owner, identity)
            if value is None:
                raise ApplicationError(404, "dataset_artifact_missing", "No owned dataset export")
            artifact = DatasetArtifact.model_validate(value)
            snapshot = await self.get(principal, artifact.snapshot_id)
            if (
                not snapshot.current_evidence_valid
                or snapshot.status != "ready"
                or snapshot.content_digest != artifact.manifest_digest
            ):
                raise ApplicationError(
                    409,
                    "dataset_artifact_withdrawn",
                    "Sources or their purpose grant no longer qualify",
                )
            if artifact.id != identity:
                raise ApplicationError(
                    409, "dataset_artifact_corrupt", "Artifact identity differs from its lookup key"
                )
            path = self.artifact_path(artifact.id)
            if path.is_symlink():
                raise ApplicationError(
                    409, "dataset_artifact_corrupt", "An export cannot be a symlink"
                )
            try:
                content = await anyio.to_thread.run_sync(path.read_bytes)
            except OSError as error:
                raise ApplicationError(
                    409,
                    "dataset_artifact_unavailable",
                    "Export bytes unavailable; replay export to repair",
                ) from error
            if (
                len(content) != artifact.size
                or hashlib.sha256(content).hexdigest() != artifact.sha256
            ):
                raise ApplicationError(
                    409, "dataset_artifact_corrupt", "Immutable artifact digest differs"
                )
            if not (await self.get(principal, artifact.snapshot_id)).current_evidence_valid:
                raise ApplicationError(
                    409, "dataset_artifact_withdrawn", "Evidence changed during artifact read"
                )
            return artifact, content
