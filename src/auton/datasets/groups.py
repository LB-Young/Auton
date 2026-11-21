"""Persistent split locks plus explicit lexical duplicate heuristics, not embeddings."""

from dataclasses import dataclass

import anyio
from pydantic import Field

from auton.constitution.config import Principal
from auton.datasets.contracts import DataSplit, TrainingExample
from auton.datasets.store import DatasetStore, digest
from auton.kernel.ports import ApplicationError
from auton.model.contracts import Contract


class GroupRecord(Contract):
    id: str
    version: int = 0
    split: DataSplit
    tokens: tuple[str, ...]
    normalized_inputs: tuple[str, ...] = Field(max_length=2000)
    heuristic_revision: str = "lexical-char5-jaccard-092-v1"


@dataclass(frozen=True)
class GroupAssignment:
    examples: tuple[TrainingExample, ...]
    updates: tuple[GroupRecord, ...]
    rejected_ids: tuple[str, ...]


def shingles(text: str) -> frozenset[str]:
    return frozenset(text[i : i + 5] for i in range(max(0, len(text) - 4)))


class SplitGroupPolicy:
    def assign(
        self, examples: tuple[TrainingExample, ...], existing: tuple[GroupRecord, ...]
    ) -> GroupAssignment:
        if len(existing) > 2000:
            raise ApplicationError(
                429,
                "dataset_group_capacity",
                "Review group retention before adding more split assignments",
            )
        parents = list(range(len(existing) + len(examples)))

        def root(i: int) -> int:
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return i

        def union(a: int, b: int) -> None:
            parents[root(a)] = root(b)

        nodes: list[tuple[set[str], tuple[str, ...], DataSplit, str | None]] = []
        for prior in existing:
            nodes.append(
                (
                    set((*prior.tokens, "root:" + prior.id)),
                    prior.normalized_inputs,
                    prior.split,
                    prior.id,
                )
            )
        for example in examples:
            tokens = {
                *example.lineage_tokens,
                *("input:" + f for f in example.input_fingerprints),
                "family:" + example.family,
                "origin:" + example.origin_group,
                "text:" + digest(example.normalized_input),
            }
            if example.kind == "executor" and len(example.normalized_target) >= 80:
                tokens.add("target:" + digest(example.normalized_target))
            nodes.append((tokens, (example.normalized_input,), example.split, None))
        seen: dict[str, int] = {}
        seen_text: dict[str, int] = {}
        text_sets: list[tuple[str, frozenset[str], int]] = []
        for i, (tokens, texts, _, _) in enumerate(nodes):
            for token in tokens:
                if token in seen:
                    union(i, seen[token])
                else:
                    seen[token] = i
            for text in texts:
                if text in seen_text:
                    union(i, seen_text[text])
                    continue
                seen_text[text] = i
                # A bounded deterministic heuristic. Family/origin/DAG and exact
                # fingerprints remain authoritative even when lexical similarity misses.
                if len(text) < 80:
                    continue
                sketch = shingles(text)
                for previous, other, j in text_sets:
                    if min(len(text), len(previous)) / max(len(text), len(previous)) < 0.9:
                        continue
                    denominator = len(sketch | other)
                    if denominator and len(sketch & other) / denominator >= 0.92:
                        union(i, j)
                text_sets.append((text, sketch, i))
        components: dict[int, list[int]] = {}
        for i in range(len(nodes)):
            components.setdefault(root(i), []).append(i)
        assigned: list[TrainingExample] = []
        updates: list[GroupRecord] = []
        rejected: list[str] = []
        for indices in components.values():
            positions = [i - len(existing) for i in indices if i >= len(existing)]
            if not positions:
                continue
            if len({nodes[i][2] for i in indices}) != 1:
                rejected.extend(examples[p].id for p in positions)
                continue
            old_ids = [existing[i].id for i in indices if i < len(existing)]
            component_tokens = tuple(sorted({t for i in indices for t in nodes[i][0]}))
            identity = min(old_ids) if old_ids else digest(component_tokens)
            assert identity is not None
            old = next((r for r in existing if r.id == identity), None)
            texts = tuple(sorted({t for i in indices for t in nodes[i][1]}))
            if len(texts) > 2000:
                raise ApplicationError(
                    429, "dataset_group_member_limit", "Bounded independence group exceeded"
                )
            split = nodes[indices[0]][2]
            value = GroupRecord(
                id=identity,
                version=old.version + 1 if old else 0,
                split=split,
                tokens=component_tokens,
                normalized_inputs=texts,
            )
            if (
                not old
                or old.tokens != value.tokens
                or old.normalized_inputs != value.normalized_inputs
            ):
                updates.append(value)
            assigned.extend(
                examples[p].model_copy(update={"group_id": identity}) for p in positions
            )
        return GroupAssignment(tuple(assigned), tuple(updates), tuple(rejected))


class GroupLedger:
    def __init__(self, store: DatasetStore, policy: SplitGroupPolicy) -> None:
        self.store, self.policy = store, policy

    async def existing(self, principal: Principal) -> tuple[GroupRecord, ...]:
        return tuple(
            GroupRecord.model_validate(v) for v in await self.store.list("group", principal.owner)
        )

    async def assign(
        self, principal: Principal, examples: tuple[TrainingExample, ...], commit: bool
    ) -> GroupAssignment:
        existing = await self.existing(principal)
        result = await anyio.to_thread.run_sync(self.policy.assign, examples, existing)
        if commit:
            for update in result.updates:
                await self.store.put(
                    "group",
                    principal.owner,
                    update.id,
                    update.model_dump(mode="json"),
                    update.version - 1 if update.version else None,
                )
        return result


class GroupPolicyFactory:
    def create(self) -> SplitGroupPolicy:
        return SplitGroupPolicy()
