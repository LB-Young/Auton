"""Exercise merging after an authenticated artifact port; these are synthetic fixtures."""

import json
from types import SimpleNamespace
from typing import cast

import pytest
from test_context import USER

from auton.datasets.contracts import (
    DatasetArtifact,
    DatasetBuild,
    DatasetKind,
    DatasetSnapshot,
    DataSplit,
    ExportCommand,
    SourceProof,
    SubjectRef,
    TrainingExample,
)
from auton.datasets.ports import DatasetPort
from auton.kernel.ports import ApplicationError
from auton.training.contracts import TrainingPlanCommand
from auton.training.data import TrainingDataReader
from auton.training.decision_data import DecisionDataReader
from auton.training.dependencies import TrainingDependencies


def fixture_sources(kind: DatasetKind = "executor") -> tuple[TrainingDataReader, dict[str, object]]:
    snapshots: dict[str, DatasetSnapshot] = {}
    artifacts: dict[str, tuple[DatasetArtifact, bytes]] = {}
    sources: list[tuple[int, DataSplit]] = [(1, "train"), (2, "train"), (3, "validation")]
    for index, split in sources:
        identity = str(index) * 64
        example = TrainingExample(
            id=identity,
            kind=kind,
            family="fixture-" + str(index),
            origin_group="fixture-origin-" + str(index),
            split=split,
            group_id="fixture-group-" + str(index),
            normalized_input="fixture input",
            normalized_target="fixture output",
            input_fingerprints=(identity,),
            engineering_only=True,
            proofs=(
                SourceProof(
                    run_id=identity,
                    version=1,
                    goal_revision=1,
                    checkpoint_id=identity,
                    checkpoint_digest=identity,
                    source_digest=identity,
                    input_snapshot_id=identity,
                    source="test",
                ),
            ),
        )
        snapshot = DatasetSnapshot(
            id=identity,
            command=DatasetBuild(
                request_id="fixture-" + str(index),
                project_id="project-" + str(index),
                kind=kind,
                grant_id="a" * 64,
                subjects=(
                    SubjectRef(
                        run_id=identity,
                        expected_version=1,
                        family="fixture",
                        origin_group="fixture",
                        split=split,
                        review_id=identity if kind == "decision" else None,
                    ),
                ),
            ),
            config_digest="a" * 64,
            grant_digest="b" * 64,
            content_digest="c" * 64,
            examples=(example,),
            created_at=0,
            status="engineering_only",
        )
        command = ExportCommand(
            request_id="fixture-" + str(index),
            expected_content_digest=snapshot.content_digest,
            split=split,
            purpose="local_training" if split == "train" else "local_validation",
        )
        artifact = DatasetArtifact(
            id=identity,
            snapshot_id=identity,
            command=command,
            sha256=identity,
            size=1,
            example_count=1,
            manifest_digest=identity,
        )
        row: dict[str, object] = {"id": identity, "kind": kind}
        if kind == "decision":
            row.update(
                {
                    "input": {
                        "state": "Synthetic state " + str(index),
                        "question": {
                            "id": "continue",
                            "type": "boolean",
                            "point": "information_sufficiency",
                            "instructions": "Continue?",
                            "options": [],
                        },
                    },
                    "target": {"question_id": "continue", "type": "boolean", "selected_id": "yes"},
                }
            )
        artifacts[identity] = artifact, (json.dumps(row) + "\n").encode()
        snapshots[identity] = snapshot

    async def read(principal: object, identity: str) -> tuple[DatasetArtifact, bytes]:
        assert principal == USER
        return artifacts[identity]

    async def get(principal: object, identity: str) -> DatasetSnapshot:
        assert principal == USER
        return snapshots[identity]

    # The production artifact port checks ownership, qualification and original blob hashes.
    port = cast(DatasetPort, SimpleNamespace(read_artifact=read, get=get))
    deps = cast(TrainingDependencies, SimpleNamespace(datasets=port))
    reader = DecisionDataReader(deps) if kind == "decision" else TrainingDataReader(deps)
    return reader, {"artifacts": artifacts, "snapshots": snapshots}


def command(**changes: object) -> TrainingPlanCommand:
    return TrainingPlanCommand.model_validate(
        {
            "request_id": "aggregate",
            "project_id": "project-1",
            "base_model_id": "fixture-base",
            "train_artifact_id": "1" * 64,
            "additional_train_artifact_ids": ["2" * 64],
            "validation_artifact_id": "3" * 64,
            **changes,
        }
    )


async def test_multiple_conversations_require_explicit_scope_and_preserve_counts() -> None:
    reader, _ = fixture_sources()
    with pytest.raises(ApplicationError) as denied:
        await reader.read(USER, command())
    assert denied.value.code == "training_dataset_scope"
    inputs, manifests, examples, groups = await reader.read(
        USER, command(allow_cross_project_sources=True)
    )
    assert len(inputs["train"].splitlines()) == 2
    assert examples == {"train": 2, "validation": 1}
    assert groups == {"train": 2, "validation": 1}
    assert set(manifests) == {"train", "validation"}


async def test_duplicate_artifacts_and_duplicate_examples_cannot_inflate_dataset() -> None:
    reader, fixture = fixture_sources()
    with pytest.raises(ApplicationError) as duplicate:
        await reader.read(USER, command(additional_train_artifact_ids=["1" * 64]))
    assert duplicate.value.code == "training_duplicate_artifact"
    snapshots = cast(dict[str, DatasetSnapshot], fixture["snapshots"])
    second = snapshots["2" * 64]
    snapshots[second.id] = second.model_copy(update={"examples": snapshots["1" * 64].examples})
    with pytest.raises(ApplicationError) as duplicate_example:
        await reader.read(USER, command(allow_cross_project_sources=True))
    assert duplicate_example.value.code == "training_duplicate_example"


async def test_batch_decision_reader_uses_each_original_lineage() -> None:
    reader, _ = fixture_sources("decision")
    inputs, _, examples, groups = await reader.read(USER, command(allow_cross_project_sources=True))
    rows = [json.loads(line) for line in inputs["train"].splitlines()]
    assert [row["_lineage_group"] for row in rows] == ["fixture-group-1", "fixture-group-2"]
    assert examples["train"] == groups["train"] == 2
