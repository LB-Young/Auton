"""Module-owned namespace over the public versioned document storage capability."""

from auton.decision_review.contracts import DecisionReviewConfig
from auton.kernel.documents import VersionedDocumentStore
from auton.kernel.documents import digest as digest
from auton.kernel.documents import key as key
from auton.kernel.ports import RuntimeDependencies
from auton.kernel.storage import EventLogPort


class ReviewStore(VersionedDocumentStore):
    def __init__(
        self,
        config: DecisionReviewConfig,
        events: EventLogPort,
        runtime: RuntimeDependencies,
        test: bool,
    ) -> None:
        super().__init__(config, events, runtime, test, "decision_review")
