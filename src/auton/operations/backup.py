"""Owner-scoped, checksummed operations snapshots; restore is paused and non-destructive."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from auton.constitution.config import Principal
from auton.kernel.documents import VersionedDocumentStore, digest, key
from auton.kernel.ports import ApplicationError
from auton.operations.contracts import (
    BackgroundJob,
    BackupCommand,
    BackupManifest,
    OperationsAlert,
    OperationsConfig,
    RestoreCommand,
    Schedule,
    TelemetryBaseline,
    TelemetrySample,
)
from auton.operations.dependencies import OperationsDependencies


class OperationsBackups:
    def __init__(
        self, config: OperationsConfig, deps: OperationsDependencies, store: VersionedDocumentStore
    ) -> None:
        self.config, self.deps, self.store = config, deps, store

    def path(self, principal: Principal, identity: str) -> Path:
        root = self.config.directory / "backups"
        owner = root / key(principal.owner, "backup-owner")
        for folder in (root, owner):
            if folder.is_symlink():
                raise ApplicationError(
                    409, "backup_path_invalid", "Backup path cannot be a symlink"
                )
            folder.mkdir(exist_ok=True, mode=0o700)
            folder.chmod(0o700)
        path = owner / (identity + ".json")
        if path.is_symlink():
            raise ApplicationError(409, "backup_path_invalid", "Backup file cannot be a symlink")
        return path

    def read(self, path: Path) -> tuple[dict[str, Any], bytes]:
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("backup size")
            raw = path.read_bytes()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("backup type")
            return value, raw
        except (OSError, ValueError) as error:
            raise ApplicationError(
                409, "backup_invalid", "Backup is missing, corrupt or oversized"
            ) from error

    async def create(self, principal: Principal, command: BackupCommand) -> BackupManifest:
        identity = key(principal.owner, "backup:" + command.request_id)
        path = self.path(principal, identity)
        if not path.exists():
            db = self.store.database()
            with db:
                documents = list(
                    db.execute(
                        "SELECT kind,id,version,payload,digest,created FROM documents "
                        "WHERE owner=? ORDER BY kind,id,version",
                        (principal.owner,),
                    )
                )
                heads = list(
                    db.execute(
                        "SELECT kind,id,version FROM heads WHERE owner=? ORDER BY kind,id",
                        (principal.owner,),
                    )
                )
                receipts = list(
                    db.execute(
                        "SELECT id,kind,document_id,digest FROM receipts WHERE owner=? ORDER BY id",
                        (principal.owner,),
                    )
                )
                samples = list(
                    db.execute(
                        "SELECT project,id,created,payload FROM ops_samples WHERE "
                        "owner=? ORDER BY created,id",
                        (principal.owner,),
                    )
                )
            body: dict[str, Any] = {
                "schema": "auton-operations-backup-v1",
                "id": identity,
                "owner_key": key(principal.owner, "backup-owner"),
                "config_digest": self.config.digest,
                "created_at": self.deps.runtime.now().timestamp(),
                "documents": documents,
                "heads": heads,
                "receipts": receipts,
                "samples": samples,
            }
            raw = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
            if len(raw) > 32 * 1024 * 1024:
                raise ApplicationError(
                    429, "backup_size_limit", "Operations backup exceeds bounded size"
                )
            temporary = path.with_suffix(".tmp")
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        body, raw = self.read(path)
        if (
            body.get("owner_key") != key(principal.owner, "backup-owner")
            or body.get("id") != identity
        ):
            raise ApplicationError(
                409, "backup_scope_invalid", "Backup belongs to another owner/request"
            )
        return BackupManifest(
            id=identity,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes=len(raw),
            config_digest=body["config_digest"],
            records=len(body["documents"]),
            created_at=body["created_at"],
        )

    async def restore(self, principal: Principal, command: RestoreCommand) -> BackupManifest:
        body, raw = self.read(self.path(principal, command.backup_id))
        if (
            not command.confirm_empty_target
            or hashlib.sha256(raw).hexdigest() != command.expected_sha256
            or body.get("schema") != "auton-operations-backup-v1"
            or body.get("id") != command.backup_id
            or body.get("owner_key") != key(principal.owner, "backup-owner")
            or body.get("config_digest") != self.config.digest
        ):
            raise ApplicationError(
                409,
                "backup_restore_denied",
                "Exact owned compatible backup and empty-target confirmation required",
            )
        db = self.store.database()
        if db.execute("SELECT 1 FROM heads WHERE owner=? LIMIT 1", (principal.owner,)).fetchone():
            raise ApplicationError(
                409, "backup_target_not_empty", "Restore never overwrites existing owned state"
            )
        validators: dict[
            str,
            type[Schedule] | type[BackgroundJob] | type[OperationsAlert] | type[TelemetryBaseline],
        ] = {
            "schedule": Schedule,
            "job": BackgroundJob,
            "alert": OperationsAlert,
            "baseline": TelemetryBaseline,
        }
        projects = set()
        seen = set()
        try:
            for kind, identity, version, payload, checksum, _created in body["documents"]:
                value = json.loads(payload)
                if kind == "control":
                    if (
                        set(value) != {"id", "version", "paused"}
                        or type(value["paused"]) is not bool
                    ):
                        raise ValueError("control schema")
                elif kind in validators:
                    parsed = validators[kind].model_validate(value)
                    projects.add(parsed.project_id)
                else:
                    raise ValueError("unknown backup namespace")
                if (
                    value["id"] != identity
                    or value["version"] != version
                    or digest(value) != checksum
                    or not 0 <= version < 65536
                    or (kind, identity, version) in seen
                ):
                    raise ValueError("document digest/version")
                seen.add((kind, identity, version))
            for kind, identity, version in body["heads"]:
                if (kind, identity, version) not in seen:
                    raise ValueError("missing head")
            for project, identity, created, payload in body["samples"]:
                sample = TelemetrySample.model_validate_json(payload)
                if (
                    sample.id != identity
                    or sample.project_id != project
                    or sample.created_at != created
                ):
                    raise ValueError("sample identity")
                projects.add(project)
            for _, kind, identity, _ in body["receipts"]:
                if not any(k == kind and i == identity for k, i, _ in seen):
                    raise ValueError("receipt identity")
        except (ValueError, KeyError, TypeError) as error:
            raise ApplicationError(
                409, "backup_payload_invalid", "Backup graph/schema/digest is inconsistent"
            ) from error
        for project in projects:
            await self.deps.assets.resolve(principal, project)
        # Preserve original history and stable upstream IDs, but advance each head
        # beyond any already-audited version. A stale backup must not collide with
        # the surviving kernel journal when a worker is next acknowledged.
        head_versions = {(kind, identity): version for kind, identity, version in body["heads"]}
        control_id = key(principal.owner, "control")
        prefix_map = {
            self.store.namespace + ":" + key(principal.owner, kind + ":" + identity) + ":": (
                kind,
                identity,
            )
            for kind, identity in {*head_versions, ("control", control_id)}
        }
        cursor = 0
        for _ in range(1000):
            page = await self.deps.events.read(after=cursor, limit=1000)
            if not page:
                break
            cursor = page[-1].cursor
            for stored in page:
                prefix, separator, suffix = stored.event.event_id.rpartition(":")
                pair = prefix_map.get(prefix + separator)
                if pair is not None and suffix.isdigit():
                    head_versions[pair] = max(head_versions.get(pair, -1), int(suffix))
        else:
            raise ApplicationError(
                429,
                "backup_journal_scan_limit",
                "Restore needs an offline bounded journal migration",
            )
        now = self.deps.runtime.now().timestamp()
        restored_rows = []
        restored_heads = []
        lookup = {
            (k, i, v): (payload, checksum, created)
            for k, i, v, payload, checksum, created in body["documents"]
        }
        for kind, identity, original_version in body["heads"]:
            if kind == "control" and identity == control_id:
                continue
            payload, _, _ = lookup[(kind, identity, original_version)]
            value = json.loads(payload)
            version = head_versions[(kind, identity)] + 1
            if version >= 65536:
                raise ApplicationError(
                    429, "backup_version_limit", "Restored document needs an offline migration"
                )
            value["version"] = version
            restored_rows.append((kind, identity, version, json.dumps(value), digest(value), now))
            restored_heads.append((kind, identity, version))
        version = head_versions.get(("control", control_id), -1) + 1
        control = {"id": control_id, "version": version, "paused": True}
        with db:
            if db.execute(
                "SELECT 1 FROM heads WHERE owner=? LIMIT 1", (principal.owner,)
            ).fetchone():
                raise ApplicationError(
                    409, "backup_target_not_empty", "Concurrent state prevents restore"
                )
            for kind, identity, v, payload, checksum, created in body["documents"]:
                db.execute(
                    "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                    (kind, principal.owner, identity, v, payload, checksum, created),
                )
            for kind, identity, v, payload, checksum, created in restored_rows:
                db.execute(
                    "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                    (kind, principal.owner, identity, v, payload, checksum, created),
                )
            for kind, identity, v in restored_heads:
                db.execute(
                    "INSERT INTO heads VALUES(?,?,?,?)", (kind, principal.owner, identity, v)
                )
            for request, kind, identity, checksum in body["receipts"]:
                db.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?,?)",
                    (principal.owner, request, kind, identity, checksum),
                )
            for project, identity, created, payload in body["samples"]:
                db.execute(
                    "INSERT INTO ops_samples VALUES(?,?,?,?,?)",
                    (principal.owner, project, identity, created, payload),
                )
            db.execute(
                "INSERT INTO documents VALUES(?,?,?,?,?,?,?)",
                (
                    "control",
                    principal.owner,
                    control_id,
                    version,
                    json.dumps(control),
                    digest(control),
                    now,
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO heads VALUES(?,?,?,?)",
                ("control", principal.owner, control_id, version),
            )
        return BackupManifest(
            id=command.backup_id,
            sha256=command.expected_sha256,
            bytes=len(raw),
            config_digest=self.config.digest,
            records=len(body["documents"]),
            created_at=body["created_at"],
        )
