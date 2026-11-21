"""Portable workflow contracts and explicit worker fault injection; no model-quality claims."""

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from test_context import USER
from test_datasets import agent as agent
from test_datasets import assessment as assessment
from test_datasets import context as context
from test_datasets import datasets as datasets
from test_datasets import evolution as evolution
from test_datasets import reviewer as reviewer
from test_datasets import supervisor as supervisor

from auton.datasets.service import Datasets
from auton.kernel.ports import ApplicationError
from auton.training.backend import DockerTrainingBackend
from auton.training.contracts import (
    BaseModelSpec,
    TrainingConfig,
    TrainingControl,
    TrainingJob,
    TrainingJobCommand,
    TrainingPlanCommand,
)
from auton.training.dependencies import TrainingDependencies
from auton.training.factory import ExecutorTrainingFactory
from auton.training.ports import WorkerState
from auton.training.service import ExecutorTraining
from auton.training.worker import encode_record


class FixtureBackend:
    """Simulate control receipts only, never claim actual gradient/model execution."""

    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0
        self.states: dict[str, WorkerState] = {}
        self.directory: Path | None = None

    async def start(
        self, identity: str, job_directory: Path, base: Path, manifest_digest: str
    ) -> None:
        self.starts += 1
        self.directory = job_directory
        self.states[identity] = WorkerState(status="running")

    async def state(self, identity: str, manifest_digest: str) -> WorkerState:
        return self.states.get(identity, WorkerState(status="absent"))

    async def stop(self, identity: str, manifest_digest: str) -> None:
        self.stops += 1
        self.states[identity] = WorkerState(status="failed", reason="stopped")

    def checkpoint(self, job: TrainingJob, step: int = 1, complete: bool = False) -> None:
        assert self.directory
        output = self.directory / "output"
        folder_name = "step-" + str(step).zfill(8)
        folder = output / folder_name
        folder.mkdir()
        files = {}
        for name in ("adapter.safetensors", "state.safetensors"):
            content = b"synthetic checkpoint bytes for I/O/control tests only"
            (folder / name).write_bytes(content)
            files[name] = hashlib.sha256(content).hexdigest()
        checkpoint = {"step": step, "files": files, "manifest_digest": job.plan_digest}
        (output / "baseline.json").write_text("{}")
        # Match the real worker's atomic progress publication: the service reads in
        # a separate I/O thread and must never observe a partially written fixture.
        temporary = output / "progress.json.tmp"
        temporary.write_text(json.dumps({"checkpoint": checkpoint, "folder": folder_name}))
        temporary.replace(output / "progress.json")
        if complete:
            (output / "result.json").write_text(
                json.dumps(
                    {
                        "protocol": "auton-training-worker-v1",
                        "plan_digest": job.plan_digest,
                        "metrics": {"fixture_control_only": True},
                    }
                )
            )
            self.states[next(iter(self.states))] = WorkerState(status="succeeded")


@pytest.fixture
async def training(
    datasets: Datasets, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[ExecutorTraining, FixtureBackend]]:
    base = tmp_path / "base"
    base.mkdir()
    template = "fixture tool-aware template"
    (base / "config.json").write_text("{}")
    (base / "tokenizer_config.json").write_text(json.dumps({"chat_template": template}))
    (base / "model.safetensors").write_bytes(b"fixture only; not model weights")
    spec = BaseModelSpec(
        id="fixture-base",
        directory=base,
        repository="fixture/base",
        revision="a" * 40,
        license_reference="Synthetic fixture for workflow tests",
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in base.iterdir()},
        template_sha256=hashlib.sha256(template.encode()).hexdigest(),
    )
    config = TrainingConfig(
        directory=tmp_path / "training",
        backend="docker",
        image="fixture/worker@sha256:" + "b" * 64,
        base_models=(spec,),
        min_free_bytes=1048576,
    )
    service = ExecutorTrainingFactory().create(
        config,
        TrainingDependencies(
            datasets, datasets.deps.assets, datasets.deps.events, datasets.deps.runtime, True
        ),
    )
    assert isinstance(service, ExecutorTraining)
    backend = FixtureBackend()
    monkeypatch.setattr(service, "backend", backend)

    async def data(
        *args: object,
    ) -> tuple[dict[str, bytes], dict[str, str], dict[str, int], dict[str, int]]:
        return {"train": b'{"fixture":true}\n'}, {"train": "c" * 64}, {"train": 1}, {"train": 1}

    monkeypatch.setattr(service.data, "read", data)
    await service.start()
    yield service, backend
    await service.close()


async def wait_job(service: ExecutorTraining, identity: str, status: str) -> TrainingJob:
    for _ in range(300):
        job = await service.get(USER, identity)
        if job.status == status:
            return job
        if status == "running" and job.status == "failed":
            pytest.fail(job.reason)
        await asyncio.sleep(0.02)
    pytest.fail("Timed out waiting for worker control state: " + job.model_dump_json())


async def plan_job(service: ExecutorTraining, identity: str = "job-one") -> TrainingJob:
    plan = await service.plan(
        USER,
        TrainingPlanCommand(
            request_id="plan-" + identity,
            project_id="project",
            base_model_id="fixture-base",
            train_artifact_id="d" * 64,
            steps=2,
            engineering_probe=True,
        ),
    )
    assert plan.status == "ready", plan.blockers
    return await service.create(
        USER,
        TrainingJobCommand(
            request_id=identity, plan_id=plan.id, expected_plan_digest=plan.manifest_digest
        ),
    )


async def test_portable_plan_has_independent_data_thresholds_and_pinned_base(
    training: tuple[ExecutorTraining, FixtureBackend],
) -> None:
    service, _ = training
    standard = await service.plan(
        USER,
        TrainingPlanCommand(
            request_id="standard",
            project_id="project",
            base_model_id="fixture-base",
            train_artifact_id="d" * 64,
        ),
    )
    assert standard.status == "blocked"
    assert "insufficient_independent_validation_groups" in standard.blockers
    assert "insufficient_independent_anchor_groups" in standard.blockers
    spec = service.config.base_models[0]
    (spec.directory / "model.safetensors").write_bytes(b"changed")
    blocked = await service.plan(
        USER, standard.command.model_copy(update={"request_id": "changed-base"})
    )
    assert "training_base_digest_changed" in blocked.blockers


async def test_idempotent_job_candidate_only_and_source_withdrawal(
    training: tuple[ExecutorTraining, FixtureBackend], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, backend = training
    created = await plan_job(service)
    running = await wait_job(service, created.id, "running")
    assert (await service.create(USER, created.command)).id == created.id and backend.starts == 1
    backend.checkpoint(running, 2, True)
    done = await wait_job(service, created.id, "succeeded")
    assert done.completed_steps == 2
    bundle = (await service.bundles(USER, "project"))[0]
    assert (
        not bundle.quality_release_eligible
        and bundle.activation == "offline_candidate"
        and bundle.source == "test"
    )

    async def revoked(*args: object) -> Any:
        raise ApplicationError(409, "dataset_artifact_withdrawn", "withdrawn fixture")

    monkeypatch.setattr(service.data, "read", revoked)
    assert not (await service.bundles(USER, "project"))[0].source_current
    assert backend.starts == 1


async def test_cancel_checkpoint_resume_and_corruption_guard(
    training: tuple[ExecutorTraining, FixtureBackend],
) -> None:
    service, backend = training
    created = await plan_job(service)
    running = await wait_job(service, created.id, "running")
    backend.checkpoint(running)
    cancelled = await service.control(
        USER,
        running.id,
        TrainingControl(request_id="cancel", expected_version=running.version, action="cancel"),
    )
    assert cancelled.status == "cancelled" and cancelled.completed_steps == 1 and backend.stops >= 1
    for _ in range(100):
        if running.id not in service.tasks:
            break
        await asyncio.sleep(0.01)
    root = service.directory(cancelled)
    original = (root / "output/step-00000001/adapter.safetensors").read_bytes()
    (root / "output/step-00000001/adapter.safetensors").write_bytes(b"corrupt")
    with pytest.raises(ApplicationError) as corrupt:
        await service.control(
            USER,
            running.id,
            TrainingControl(
                request_id="bad-resume", expected_version=cancelled.version, action="resume"
            ),
        )
    assert corrupt.value.code == "training_checkpoint_corrupt"
    assert (await service.get(USER, running.id)).version == cancelled.version
    (root / "output/step-00000001/adapter.safetensors").write_bytes(original)
    resumed = await service.control(
        USER,
        running.id,
        TrainingControl(request_id="resume", expected_version=cancelled.version, action="resume"),
    )
    assert resumed.attempt == 1
    await wait_job(service, running.id, "running")
    assert backend.starts == 2


async def test_withdrawn_source_stops_running_worker(
    training: tuple[ExecutorTraining, FixtureBackend], monkeypatch: pytest.MonkeyPatch
) -> None:
    service, backend = training
    created = await plan_job(service)
    await wait_job(service, created.id, "running")

    async def revoked(*args: object) -> Any:
        raise ApplicationError(409, "dataset_artifact_withdrawn", "withdrawn fixture")

    monkeypatch.setattr(service.data, "read", revoked)
    failed = await wait_job(service, created.id, "failed")
    assert "training_source_invalid" in failed.reason and backend.stops >= 1
    assert backend.starts == 1


def test_docker_worker_has_isolated_mounts_limits_and_no_host_secrets(tmp_path: Path) -> None:
    config = TrainingConfig(backend="docker", image="registry/worker@sha256:" + "a" * 64)
    args = DockerTrainingBackend(config).create_arguments(
        "b" * 64, tmp_path / "job", tmp_path / "base", "c" * 64
    )
    assert args[args.index("--network") + 1] == "none" and "--read-only" in args
    assert "--cap-drop" in args and "--memory" in args and "--cpus" in args
    assert all(".env" not in a and "docker.sock" not in a for a in args)
    assert args[-3:] == ("-I", "/worker.py", "/input/manifest.json")


class FixtureTokenizer:
    def apply_chat_template(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        result = "".join(
            "<" + m["role"] + ">" + str(m.get("content") or m.get("tool_calls")) + "</end>"
            for m in messages
        )
        return result + ("<assistant>" if kwargs.get("add_generation_prompt") else "")

    def __call__(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "input_ids": list(range(len(text))),
            "offset_mapping": [(i, i + 1) for i in range(len(text))],
        }


def test_token_supervision_keeps_only_verified_assistant_and_refuses_truncation() -> None:
    record = {
        "id": "fixture",
        "kind": "executor",
        "input_message_count": 1,
        "loss_message_indices": [1],
        "tools": [],
        "messages": [
            {"role": "user", "content": "中文目标"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "call-one", "name": "file_write", "arguments": {"content": "hello"}}
                ],
            },
            {"role": "tool", "tool_call_id": "call-one", "content": "verified receipt"},
        ],
    }
    encoded = encode_record(record, FixtureTokenizer(), 1000)
    positions = [i for i, v in enumerate(encoded["labels"]) if v != -100]
    assert positions and min(positions) == len(encoded["prompt"])
    assert max(positions) < len(encoded["input_ids"]) - len("<tool>verified receipt</end>")
    with pytest.raises(ValueError, match="sequence_limit_no_truncation"):
        encode_record(record, FixtureTokenizer(), 10)
    with pytest.raises(ValueError, match="wrong_loss_mask"):
        encode_record({**record, "loss_message_indices": [0]}, FixtureTokenizer(), 1000)


async def test_worker_oom_and_disk_shortage_never_redispatch(
    training: tuple[ExecutorTraining, FixtureBackend], monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil
    from collections import namedtuple

    service, backend = training
    created = await plan_job(service, "oom-job")
    running = await wait_job(service, created.id, "running")
    backend.states[service.worker_id(running)] = WorkerState(status="failed", reason="oom")
    failed = await wait_job(service, created.id, "failed")
    assert failed.reason == "training_worker_oom"
    assert (await service.create(USER, created.command)).status == "failed" and backend.starts == 1
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(100, 100, 0))
    second = await plan_job(service, "disk-job")
    blocked = await wait_job(service, second.id, "failed")
    assert blocked.reason.startswith("training_disk_space") and backend.starts == 1


async def test_restart_preserves_interrupted_checkpoint_without_automatic_training(
    training: tuple[ExecutorTraining, FixtureBackend],
) -> None:
    service, backend = training
    created = await plan_job(service, "restart-job")
    running = await wait_job(service, created.id, "running")
    backend.checkpoint(running)
    for _ in range(200):
        if (await service.get(USER, created.id)).completed_steps == 1:
            break
        await asyncio.sleep(0.01)
    await service.close()
    await service.start()
    restored = await service.get(USER, created.id)
    assert (
        restored.status == "interrupted" and restored.checkpoint and restored.completed_steps == 1
    )
    assert backend.starts == 1


def test_template_tool_pair_and_unsupported_boundary_fail_closed() -> None:
    record = {
        "id": "fixture",
        "kind": "executor",
        "input_message_count": 1,
        "loss_message_indices": [1],
        "tools": [],
        "messages": [
            {"role": "user", "content": "goal"},
            {"role": "assistant", "tool_calls": [{"id": "one", "name": "write", "arguments": {}}]},
        ],
    }
    with pytest.raises(ValueError, match="truncated_tool_pair"):
        encode_record(record, FixtureTokenizer(), 1000)


async def test_output_budget_scan_tolerates_atomically_renamed_temporary_entries(
    training: tuple[ExecutorTraining, FixtureBackend],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _ = training
    job = TrainingJob(
        id="a" * 64,
        command=TrainingJobCommand(
            request_id="scan", plan_id="b" * 64, expected_plan_digest="c" * 64
        ),
        project_id="project",
        plan_digest="c" * 64,
        status="queued",
        created_at=0,
    )
    output = service.directory(job) / "output"

    class Vanished:
        def is_symlink(self) -> bool:
            return False

        def is_file(self) -> bool:
            return True

        def stat(self) -> Any:
            raise FileNotFoundError("temporary file renamed by worker")

    original = Path.rglob

    def scan(path: Path, pattern: str) -> Any:
        return iter((Vanished(),)) if path == output else original(path, pattern)

    monkeypatch.setattr(Path, "rglob", scan)
    assert service.read_progress(job) is None


def test_response_supervision_masks_all_prior_turns_and_has_no_fake_tool_pair() -> None:
    record: dict[str, Any] = {
        "id": "response-fixture",
        "kind": "executor",
        "input_message_count": 3,
        "loss_message_indices": [3],
        "tools": [],
        "messages": [
            {"role": "user", "content": "My name is Lee."},
            {"role": "assistant", "content": "I remember."},
            {"role": "user", "content": "What is my name?"},
            {"role": "assistant", "content": "Your name is Lee.", "tool_calls": []},
        ],
    }
    encoded = encode_record(record, FixtureTokenizer(), 2000)
    start = len(encoded["prompt"])
    assert all(label == -100 for label in encoded["labels"][:start])
    assert all(label != -100 for label in encoded["labels"][start:])
    assert encoded["target"]["content"] == "Your name is Lee."
    with pytest.raises(ValueError, match="sequence_limit_no_truncation"):
        encode_record(record, FixtureTokenizer(), 10)
    record["messages"][-1]["content"] = ""
    with pytest.raises(ValueError, match="invalid_response_target"):
        encode_record(record, FixtureTokenizer(), 2000)
