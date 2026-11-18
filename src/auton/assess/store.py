import asyncio
import fcntl
import hashlib
import json
import os
from datetime import datetime
from typing import cast

import anyio
import apsw

from auton.assess.contracts import (
    PROTECTED_NORMALIZATION_REVISION,
    AssessConfig,
    BlindWindow,
    BlindWindowCommand,
    CaseBank,
    CaseInfo,
    EvalCase,
    ImportCases,
    normalize_protected_input,
)
from auton.constitution.config import Principal
from auton.kernel.events import Event
from auton.kernel.ports import ApplicationError, RuntimeDependencies
from auton.kernel.storage import EventLogPort, StorageError


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def key(owner: str, identity: str) -> str:
    return hashlib.sha256((owner + "\0" + identity).encode()).hexdigest()


def normalized(prompt: str) -> str:
    return normalize_protected_input(prompt)


class EvalStore:
    def __init__(
        self, config: AssessConfig, events: EventLogPort, runtime: RuntimeDependencies
    ) -> None:
        self.config, self.events, self.runtime = config, events, runtime
        self.db: apsw.Connection | None = None
        self.lease: int | None = None
        self.ready = False
        self.lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()

    def _open(self) -> None:
        self.config.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.config.directory / "evaluation.sqlite3"
        if self.config.directory.is_symlink() or path.is_symlink():
            raise ApplicationError(503, "eval_path_invalid", "Evaluation store cannot be a symlink")
        os.chmod(self.config.directory, 0o700)
        self.lease = os.open(
            self.config.directory / "store.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(self.lease)
            self.lease = None
            raise ApplicationError(
                503, "eval_store_owned", "Another service owns evaluation storage"
            ) from error
        self.db = apsw.Connection(str(path))
        os.chmod(path, 0o600)
        self.db.set_busy_timeout(1000)
        if int(self.db.pragma("user_version")) not in {0, 1}:
            raise ApplicationError(503, "eval_schema_incompatible", "Unsupported evaluation schema")
        self.db.pragma("journal_mode", "wal")
        self.db.pragma("synchronous", "full")
        with self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS documents (kind TEXT NOT NULL, owner TEXT NOT NULL, "
                "id TEXT NOT NULL, digest TEXT NOT NULL, document TEXT NOT NULL, "
                "created TEXT NOT NULL, PRIMARY KEY(kind,owner,id))"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS heads (owner TEXT PRIMARY KEY, revision TEXT NOT NULL)"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS window_uses (owner TEXT NOT NULL, "
                "window_id TEXT NOT NULL, "
                "request_id TEXT NOT NULL, PRIMARY KEY(owner,window_id,request_id))"
            )
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS split_locks (owner TEXT NOT NULL, kind TEXT NOT NULL, "
                "value TEXT NOT NULL, split TEXT NOT NULL, PRIMARY KEY(owner,kind,value))"
            )
            self.db.pragma("user_version", 1)

    async def start(self) -> None:
        if not self.ready:
            await anyio.to_thread.run_sync(self._open)
            self.ready = True

    async def close(self) -> None:
        self.ready = False

        def close() -> None:
            if self.db:
                self.db.close()
                self.db = None
            if self.lease is not None:
                os.close(self.lease)
                self.lease = None

        await anyio.to_thread.run_sync(close)

    def database(self) -> apsw.Connection:
        if not self.ready or self.db is None:
            raise ApplicationError(503, "eval_not_ready", "Evaluation storage unavailable")
        return self.db

    @staticmethod
    def user(principal: Principal) -> None:
        if principal.role != "user":
            raise ApplicationError(
                403,
                "evaluation_control_denied",
                "Only the user control plane may change or run protected evaluation",
            )

    async def get(self, kind: str, owner: str, identity: str) -> dict[str, object] | None:
        def read() -> dict[str, object] | None:
            row = (
                self.database()
                .execute(
                    "SELECT document,digest FROM documents WHERE kind=? AND owner=? AND id=?",
                    (kind, owner, identity),
                )
                .fetchone()
            )
            if row is None:
                return None
            value: dict[str, object] = json.loads(str(row[0]))
            if digest(value) != row[1]:
                raise ApplicationError(
                    409, "evaluation_document_corrupt", "Evaluation digest mismatch"
                )
            return value

        return await anyio.to_thread.run_sync(read)

    async def list(self, kind: str, owner: str) -> list[dict[str, object]]:
        def ids() -> list[str]:
            return [
                str(row[0])
                for row in self.database().execute(
                    "SELECT id FROM documents WHERE kind=? AND owner=? ORDER BY created,id",
                    (kind, owner),
                )
            ]

        result = []
        for identity in await anyio.to_thread.run_sync(ids):
            item = await self.get(kind, owner, identity)
            if item is not None:
                result.append(item)
        return result

    async def put(self, kind: str, owner: str, identity: str, data: dict[str, object]) -> None:
        document = json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        hashed = digest(data)

        def write() -> str:
            db = self.database()
            with db:
                old = db.execute(
                    "SELECT digest,created FROM documents WHERE kind=? AND owner=? AND id=?",
                    (kind, owner, identity),
                ).fetchone()
                if old:
                    if str(old[0]) != hashed:
                        raise ApplicationError(
                            409,
                            "evaluation_request_conflict",
                            "Evaluation identity has different immutable input",
                        )
                    return str(old[1])
                count = db.execute("SELECT COUNT(*) FROM documents").fetchone()
                assert count is not None
                if int(count[0]) >= self.config.max_documents:
                    raise ApplicationError(
                        429, "evaluation_store_limit", "Evaluation document limit reached"
                    )
                created = self.runtime.now().isoformat()
                db.execute(
                    "INSERT INTO documents VALUES(?,?,?,?,?,?)",
                    (kind, owner, identity, hashed, document, created),
                )
                return created
            raise ApplicationError(503, "evaluation_write_failed", "Evaluation commit failed")

        async with self.write_lock:
            created = await anyio.to_thread.run_sync(write)
        # Audit metadata only; protected case prompts/gold never enter the shared event journal.
        event = Event(
            event_id="assessment:" + key(owner, kind + ":" + identity),
            kind="assess.document",
            timestamp=datetime.fromisoformat(created),
            source="system",
            payload={"document_kind": kind, "document_id": identity, "digest": hashed},
        )
        try:
            await self.events.append([event])
        except StorageError:
            old = await self.events.lookup(event.event_id)
            if old is None or old.event.payload != event.payload:
                raise

    async def _revision(self, owner: str) -> str:
        def read() -> str:
            row = (
                self.database()
                .execute("SELECT revision FROM heads WHERE owner=?", (owner,))
                .fetchone()
            )
            return str(row[0]) if row else digest({})

        return await anyio.to_thread.run_sync(read)

    async def split_digest(self, owner: str, revision: str, split: str) -> str:
        bank = await self._bank(owner, revision)
        return digest({case.id: case.digest for case in bank.cases if case.split == split})

    async def _mapping(self, owner: str, revision: str) -> dict[str, str]:
        if revision == digest({}):
            return {}
        stored = await self.get("bank", owner, revision)
        if stored is None:
            raise ApplicationError(
                404, "evaluation_bank_missing", "Unknown immutable evaluation bank"
            )
        mapping = stored.get("cases")
        if not isinstance(mapping, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in mapping.items()
        ):
            raise ApplicationError(409, "evaluation_bank_corrupt", "Invalid case mapping")
        return cast(dict[str, str], mapping)

    async def protected_case(self, owner: str, case_id: str, revision: str) -> EvalCase:
        mapping = await self._mapping(owner, revision)
        value = await self.get("case", owner, mapping.get(case_id, ""))
        if value is None:
            raise ApplicationError(404, "evaluation_case_missing", "No case in this immutable bank")
        return EvalCase.model_validate(value)

    async def _bank(self, owner: str, revision: str, train_only: bool = False) -> CaseBank:
        mapping = await self._mapping(owner, revision)
        cases = []
        counts = {split: 0 for split in ("train", "development", "test", "meta")}
        for identity, hashed in sorted(mapping.items()):
            case = await self.protected_case(owner, identity, revision)
            if train_only and case.split != "train":
                continue
            counts[case.split] += 1
            cases.append(
                CaseInfo(
                    id=case.id,
                    family=case.family,
                    split=case.split,
                    kind=case.kind,
                    critical=case.critical,
                    digest=hashed,
                )
            )
        return CaseBank(revision=revision, cases=tuple(cases), counts=counts)

    async def bank(self, principal: Principal) -> CaseBank:
        return await self._bank(
            principal.owner, await self._revision(principal.owner), principal.role != "user"
        )

    async def read_case(
        self, principal: Principal, case_id: str, revision: str, purpose: str
    ) -> EvalCase:
        case = await self.protected_case(principal.owner, case_id, revision)
        if (
            case.split != "train"
            or purpose != "training"
            or principal.role not in {"training", "evolution", "user"}
        ):
            raise ApplicationError(
                403,
                "protected_holdout",
                "Protected prompts and gold are only available to the internal assessor",
            )
        return case

    async def import_cases(self, principal: Principal, command: ImportCases) -> CaseBank:
        self.user(principal)
        async with self.lock:
            old = await self.get("import", principal.owner, command.request_id)
            command_digest = digest(command.model_dump(mode="json"))
            if old:
                if old["command_digest"] != command_digest:
                    raise ApplicationError(
                        409, "evaluation_import_conflict", "Import id has different input"
                    )
                return await self._bank(principal.owner, str(old["revision"]))
            revision = await self._revision(principal.owner)
            if revision != command.expected_revision:
                raise ApplicationError(
                    409, "evaluation_bank_changed", "Refresh the case bank before changing it"
                )
            mapping = await self._mapping(principal.owner, revision)
            values = {
                identity: await self.protected_case(principal.owner, identity, revision)
                for identity in mapping
            }
            if len({case.id for case in command.cases}) != len(command.cases):
                raise ApplicationError(422, "duplicate_evaluation_case", "Duplicate case identity")
            values.update({case.id: case for case in command.cases})
            if (
                sum(case.split == "test" for case in values.values()) > 100
                or sum(case.split == "meta" for case in values.values()) > 500
            ):
                raise ApplicationError(
                    422,
                    "evaluation_split_capacity",
                    "Protected batches support at most 100 test and 500 meta cases",
                )
            if len(values) > self.config.max_cases:
                raise ApplicationError(429, "evaluation_case_limit", "Case limit reached")

            def locked() -> dict[tuple[str, str], str]:
                return {
                    (str(kind), str(value)): str(split)
                    for kind, value, split in self.database().execute(
                        "SELECT kind,value,split FROM split_locks WHERE owner=?", (principal.owner,)
                    )
                }

            groups = await anyio.to_thread.run_sync(locked)
            for case in values.values():
                for group in (
                    ("case_id", case.id),
                    ("family", case.family),
                    ("origin", case.origin_group),
                    ("prompt", digest(normalized(case.prompt))),
                ):
                    previous = groups.setdefault(group, case.split)
                    if previous != case.split:
                        raise ApplicationError(
                            409,
                            "evaluation_split_leak",
                            "Same family, origin or normalized task cannot cross splits",
                        )
            new_mapping = {
                identity: digest(case.model_dump(mode="json")) for identity, case in values.items()
            }
            new_revision = digest(new_mapping)
            for case in command.cases:
                await self.put(
                    "case", principal.owner, new_mapping[case.id], case.model_dump(mode="json")
                )

            # Reserve split assignments permanently; even superseded cases cannot migrate to train.
            def reserve_splits() -> None:
                db = self.database()
                with db:
                    db.executemany(
                        "INSERT OR IGNORE INTO split_locks VALUES(?,?,?,?)",
                        (
                            (principal.owner, kind, value, split)
                            for (kind, value), split in groups.items()
                        ),
                    )

            async with self.write_lock:
                await anyio.to_thread.run_sync(reserve_splits)
            for case in command.cases:
                if case.split in {"test", "meta"}:
                    await self._protect(principal.owner, case, new_mapping[case.id])
            await self.put("bank", principal.owner, new_revision, {"cases": new_mapping})
            # Advance head and import receipt in one transaction.
            receipt = {"command_digest": command_digest, "revision": new_revision}
            async with self.write_lock:

                def commit() -> None:
                    db = self.database()
                    with db:
                        row = db.execute(
                            "SELECT revision FROM heads WHERE owner=?", (principal.owner,)
                        ).fetchone()
                        current = str(row[0]) if row else digest({})
                        if current != revision:
                            raise ApplicationError(
                                409, "evaluation_bank_changed", "Concurrent bank update"
                            )
                        count = db.execute("SELECT COUNT(*) FROM documents").fetchone()
                        assert count is not None
                        if int(count[0]) >= self.config.max_documents:
                            raise ApplicationError(
                                429, "evaluation_store_limit", "Document limit reached"
                            )
                        db.execute(
                            "INSERT OR REPLACE INTO heads VALUES(?,?)",
                            (principal.owner, new_revision),
                        )
                        db.execute(
                            "INSERT INTO documents VALUES(?,?,?,?,?,?)",
                            (
                                "import",
                                principal.owner,
                                command.request_id,
                                digest(receipt),
                                json.dumps(receipt, sort_keys=True, separators=(",", ":")),
                                self.runtime.now().isoformat(),
                            ),
                        )

                await anyio.to_thread.run_sync(commit)
            return await self._bank(principal.owner, new_revision)

    async def _protect(self, owner: str, case: EvalCase, case_digest: str) -> None:
        from auton.agent.contracts import AgentRun, checkpoint_event_id

        source = await self.events.lookup("assessment:" + key(owner, "case:" + case_digest))
        assert source is not None
        marker = Event(
            event_id="assess-protected:" + key(owner, normalized(case.prompt)),
            kind="assess.protected_input",
            timestamp=source.event.timestamp,
            source="system",
            payload={
                "normalization_revision": PROTECTED_NORMALIZATION_REVISION,
                "owner_hash": hashlib.sha256(owner.encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(case.prompt.encode()).hexdigest(),
                "normalized_prompt_sha256": hashlib.sha256(
                    normalized(case.prompt).encode()
                ).hexdigest(),
                "split": case.split,
                "case_digest": case_digest,
                "family_hash": hashlib.sha256(case.family.encode()).hexdigest(),
                "origin_hash": hashlib.sha256(case.origin_group.encode()).hexdigest(),
            },
        )
        previous = await self.events.lookup(marker.event_id)
        if previous:
            if (
                previous.event.payload.get("split") != case.split
                or previous.event.payload.get("owner_hash")
                != hashlib.sha256(owner.encode()).hexdigest()
            ):
                raise ApplicationError(
                    409,
                    "evaluation_split_leak",
                    "Protected input was already locked to another split",
                )
            cutoff = previous.cursor
        else:
            try:
                receipt = await self.events.append([marker])
                cutoff = receipt.records[0].cursor
            except StorageError:
                observed = await self.events.lookup(marker.event_id)
                if observed is None or observed.event.payload != marker.payload:
                    raise
                cutoff = observed.cursor
        cursor, scanned = 0, 0
        while scanned < 100000:
            batch = await self.events.read(after=cursor, limit=1000)
            if not batch:
                break
            for row in batch:
                cursor = row.cursor
                scanned += 1
                if row.cursor >= cutoff:
                    return
                if row.event.kind != "agent.checkpoint" or not row.event.scope.run_id:
                    continue
                if row.event.event_id != checkpoint_event_id(owner, str(row.event.scope.run_id), 0):
                    continue
                run = AgentRun.model_validate(row.event.payload["run"])
                if normalized(run.command.goal) == normalized(case.prompt):
                    raise ApplicationError(
                        409,
                        "protected_case_already_observed",
                        "Observed actor tasks cannot be enrolled as fresh protected holdout",
                    )
            if len(batch) < 1000:
                break
        if scanned >= 100000:
            raise ApplicationError(
                409,
                "protected_enrollment_scan_limit",
                "Cannot prove a fresh protected input within the audit scan limit",
            )

    async def open_window(self, principal: Principal, command: BlindWindowCommand) -> BlindWindow:
        async with self.lock:
            return await self._open_window(principal, command)

    async def _open_window(self, principal: Principal, command: BlindWindowCommand) -> BlindWindow:
        self.user(principal)
        identity = key(principal.owner, command.request_id)
        committed = await self.get("window", principal.owner, identity)
        if committed:
            prior_window = BlindWindow.model_validate(committed)
            if (
                prior_window.bank_revision != command.bank_revision
                or prior_window.split != command.split
                or prior_window.purpose != command.purpose
                or prior_window.candidate_revision != command.candidate_revision
            ):
                raise ApplicationError(
                    409, "evaluation_window_conflict", "Window request has different input"
                )
            return prior_window
        if command.bank_revision != await self._revision(principal.owner):
            raise ApplicationError(
                409, "evaluation_bank_changed", "Window must bind current immutable bank"
            )
        bank = await self._bank(principal.owner, command.bank_revision)
        if not bank.counts[command.split]:
            raise ApplicationError(
                409, "empty_holdout", "No cases in the requested protected split"
            )
        identity = key(principal.owner, command.request_id)
        old = await self.get("window", principal.owner, identity)
        window = BlindWindow(
            id=identity,
            bank_revision=command.bank_revision,
            split=command.split,
            purpose=command.purpose,
            split_digest=await self.split_digest(
                principal.owner, command.bank_revision, command.split
            ),
            candidate_revision=command.candidate_revision,
            max_uses=self.config.max_window_uses,
        )
        if old and old != window.model_dump(mode="json"):
            raise ApplicationError(
                409, "evaluation_window_conflict", "Window request has different input"
            )
        # One window per candidate/bank/split prevents repeated adaptive test probing.
        for previous in await self.list("window", principal.owner):
            if (
                previous["split_digest"] == window.split_digest
                and previous["split"] == command.split
                and previous["candidate_revision"] == command.candidate_revision
                and previous["id"] != identity
            ):
                raise ApplicationError(
                    409,
                    "blind_window_already_opened",
                    "Rotate the protected bank before opening another window for this candidate",
                )
        await self.put("window", principal.owner, identity, window.model_dump(mode="json"))
        return window

    async def window_usage(self, owner: str, identity: str) -> int:
        def read() -> int:
            row = (
                self.database()
                .execute(
                    "SELECT COUNT(*) FROM window_uses WHERE owner=? AND window_id=?",
                    (owner, identity),
                )
                .fetchone()
            )
            assert row is not None
            return int(row[0])

        return await anyio.to_thread.run_sync(read)

    async def consume_window(
        self, owner: str, window_id: str, bank_revision: str, split: str, request_id: str
    ) -> None:
        value = await self.get("window", owner, window_id)
        if value is None:
            raise ApplicationError(
                403, "blind_window_required", "An explicit protected window is required"
            )
        window = BlindWindow.model_validate(value)
        current_revision = await self._revision(owner)
        current_digest = await self.split_digest(owner, current_revision, split)
        if (
            window.bank_revision != bank_revision
            or window.split != split
            or window.split_digest != current_digest
        ):
            raise ApplicationError(
                409, "blind_window_scope", "Protected split changed or window scope mismatch"
            )

        def consume() -> None:
            db = self.database()
            with db:
                head = db.execute("SELECT revision FROM heads WHERE owner=?", (owner,)).fetchone()
                if head is None or str(head[0]) != current_revision:
                    raise ApplicationError(
                        409, "evaluation_bank_changed", "Bank changed before reservation"
                    )
                if db.execute(
                    "SELECT 1 FROM window_uses WHERE owner=? AND window_id=? AND request_id=?",
                    (owner, window_id, request_id),
                ).fetchone():
                    return
                count = db.execute(
                    "SELECT COUNT(*) FROM window_uses WHERE owner=? AND window_id=?",
                    (owner, window_id),
                ).fetchone()
                assert count is not None
                used = int(count[0])
                if used >= window.max_uses:
                    raise ApplicationError(
                        409,
                        "blind_window_exhausted",
                        "Protected window is exhausted; automatic retesting is forbidden",
                    )
                db.execute("INSERT INTO window_uses VALUES(?,?,?)", (owner, window_id, request_id))

        async with self.write_lock:
            await anyio.to_thread.run_sync(consume)
