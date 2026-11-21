"""One coordinator, durable CAS jobs, and fenced worker acknowledgements."""

import asyncio
from typing import Any

from auton.constitution.config import Principal
from auton.kernel.documents import VersionedDocumentStore
from auton.kernel.ports import ApplicationError
from auton.operations.contracts import BackgroundJob, OperationsConfig
from auton.operations.dependencies import OperationsDependencies

TERMINAL = {"succeeded", "failed", "cancelled", "attention"}


class JobQueue:
    def __init__(
        self, store: VersionedDocumentStore, config: OperationsConfig, deps: OperationsDependencies
    ) -> None:
        self.store, self.config, self.deps = store, config, deps
        self.lock = asyncio.Lock()

    async def jobs(self, owner: str, project: str | None = None) -> tuple[BackgroundJob, ...]:
        return tuple(
            BackgroundJob.model_validate(v)
            for v in await self.store.list("job", owner)
            if project is None or v["project_id"] == project
        )

    async def get(self, owner: str, identity: str) -> BackgroundJob:
        value = await self.store.get("job", owner, identity)
        if value is None:
            raise ApplicationError(404, "background_job_missing", "No owned background job")
        return BackgroundJob.model_validate(value)

    async def add(self, owner: str, job: BackgroundJob) -> BackgroundJob:
        async with self.lock:
            value = await self.store.get("job", owner, job.id)
            if value:
                return BackgroundJob.model_validate(value)
            if (
                sum(j.status not in TERMINAL for j in await self.jobs(owner))
                >= self.config.max_queued_jobs
            ):
                raise ApplicationError(
                    429, "background_queue_full", "Bounded background queue is full"
                )
            await self.store.put("job", owner, job.id, job.model_dump(mode="json"), None)
            return job

    async def save(
        self,
        owner: str,
        job: BackgroundJob,
        token: str | None = None,
        request_id: str | None = None,
        request_command: object = None,
        **changes: Any,
    ) -> BackgroundJob:
        async with self.lock:
            current = await self.get(owner, job.id)
            if current.version != job.version or (
                token is not None
                and (
                    current.lease_token != token
                    or current.lease_until <= self.deps.runtime.now().timestamp()
                )
            ):
                raise ApplicationError(
                    409,
                    "background_stale_lease",
                    "Expired/replaced worker cannot acknowledge or alter a job",
                )
            result = BackgroundJob.model_validate(
                {**job.model_dump(), **changes, "version": job.version + 1}
            )
            await self.store.put(
                "job",
                owner,
                job.id,
                result.model_dump(mode="json"),
                job.version,
                request_id,
                request_command,
            )
            return result

    async def claim(self, principal: Principal, identity: str) -> BackgroundJob | None:
        async with self.lock:
            job = await self.get(principal.owner, identity)
            now = self.deps.runtime.now().timestamp()
            if (
                job.status in TERMINAL
                or job.next_due > now
                or (job.lease_token and job.lease_until > now)
            ):
                return None
            result = job.model_copy(
                update={
                    "version": job.version + 1,
                    "status": "leased",
                    "lease_token": self.deps.runtime.new_id(),
                    "lease_until": now + self.config.lease_seconds,
                    "attempts": job.attempts + (0 if job.external_id else 1),
                }
            )
            await self.store.put(
                "job", principal.owner, job.id, result.model_dump(mode="json"), job.version
            )
            return result


class JobQueueFactory:
    def create(
        self, config: OperationsConfig, deps: OperationsDependencies, store: VersionedDocumentStore
    ) -> JobQueue:
        return JobQueue(store, config, deps)
