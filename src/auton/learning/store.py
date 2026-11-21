import anyio

from auton.kernel.documents import VersionedDocumentStore


class LearningStore(VersionedDocumentStore):
    async def owners(self) -> tuple[str, ...]:
        def read() -> tuple[str, ...]:
            return tuple(
                str(row[0])
                for row in self.database().execute(
                    "SELECT DISTINCT owner FROM heads WHERE kind='conversation' ORDER BY owner"
                )
            )

        return await anyio.to_thread.run_sync(read)
