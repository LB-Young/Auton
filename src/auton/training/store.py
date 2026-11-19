import anyio

from auton.kernel.documents import VersionedDocumentStore


class TrainingStore(VersionedDocumentStore):
    async def owners(self) -> tuple[str, ...]:
        def read() -> tuple[str, ...]:
            return tuple(
                str(r[0]) for r in self.database().execute("SELECT DISTINCT owner FROM heads")
            )

        return await anyio.to_thread.run_sync(read)
