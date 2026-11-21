from auton.kernel.ports import ApplicationError


class EvolutionJobs:
    """Shared event-loop admission; release on human-wait boundaries, never fake a lease."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.active: set[str] = set()

    def acquire(self, identity: str) -> None:
        if identity in self.active:
            return
        if len(self.active) >= self.limit:
            raise ApplicationError(429, "evolution_busy", "Another evolution job is active")
        self.active.add(identity)

    def release(self, identity: str) -> None:
        self.active.discard(identity)
