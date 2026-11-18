import hashlib

from auton.assess.contracts import EvalCase


class SeedCaseFactory:
    def create(self) -> tuple[EvalCase, ...]:
        # Authored public training examples. They are never declared blind test/meta or human gold.
        return (
            EvalCase(
                id="seed-exact-file",
                family="seed-exact-file",
                origin_group="seed-exact-file",
                split="train",
                prompt="Write exactly hello followed by a newline to notes.md.",
                kind="file",
                target_path="notes.md",
                expected_sha256=hashlib.sha256(b"hello\n").hexdigest(),
                source="benchmark",
                data_domain="public",
            ),
            EvalCase(
                id="seed-citation-review",
                family="seed-citation-review",
                origin_group="seed-citation-review",
                split="train",
                prompt="Summarize the supplied project evidence and cite retained source IDs.",
                kind="research",
                source="benchmark",
                data_domain="public",
            ),
        )
