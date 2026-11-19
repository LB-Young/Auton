import hashlib
from pathlib import Path

import anyio

from auton.constitution.config import Principal
from auton.datasets.contracts import DatasetArtifact
from auton.kernel.documents import digest
from auton.kernel.ports import ApplicationError
from auton.training.contracts import ENCODER_CHOICE_TEMPLATE, BaseModelSpec, TrainingPlanCommand
from auton.training.dependencies import TrainingDependencies


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            value.update(block)
    return value.hexdigest()


def verify_base(spec: BaseModelSpec) -> str:
    root = spec.directory.resolve()
    if spec.directory.is_symlink() or not root.is_dir():
        raise ApplicationError(
            409, "training_base_missing", "Configure a verified local base model"
        )
    if "config.json" not in spec.files or "tokenizer_config.json" not in spec.files:
        raise ApplicationError(
            409, "training_base_manifest_incomplete", "Pin model and tokenizer configuration"
        )
    actual_files = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ApplicationError(409, "training_base_symlink", "Base files must not be symlinks")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if (
                path.suffix not in {".safetensors", ".json", ".txt", ".model", ".jinja"}
                and relative != "LICENSE"
            ):
                raise ApplicationError(
                    409, "training_unsafe_base_format", "No remote code or pickle weights"
                )
            actual_files.add(relative)
    if actual_files != set(spec.files) or not any(n.endswith(".safetensors") for n in actual_files):
        raise ApplicationError(
            409, "training_base_manifest_incomplete", "Every mounted base file must be pinned"
        )
    for name, expected in spec.files.items():
        if not (root / name).resolve().is_relative_to(root) or file_digest(root / name) != expected:
            raise ApplicationError(409, "training_base_digest_changed", "Base file digest differs")
    import json

    tokenizer = json.loads((root / "tokenizer_config.json").read_text())
    template = (
        ENCODER_CHOICE_TEMPLATE
        if spec.architecture == "encoder_choice"
        else tokenizer.get("chat_template")
    )
    if (
        not isinstance(template, str)
        or hashlib.sha256(template.encode()).hexdigest() != spec.template_sha256
    ):
        raise ApplicationError(
            409, "training_template_changed", "Pin the actual tool-aware chat template"
        )
    return digest(spec.model_dump(mode="json", exclude={"directory"}))


class TrainingDataReader:
    def __init__(self, deps: TrainingDependencies, kind: str = "executor") -> None:
        self.deps = deps
        self.kind = kind
        self.base_cache: dict[str, tuple[tuple[tuple[str, int, int, int, int], ...], str]] = {}

    async def read(
        self, principal: Principal, command: TrainingPlanCommand
    ) -> tuple[dict[str, bytes], dict[str, str], dict[str, int], dict[str, int]]:
        inputs: dict[str, bytes] = {}
        manifests: dict[str, str] = {}
        examples: dict[str, int] = {}
        groups: dict[str, int] = {}
        assigned: dict[str, str] = {}
        for scope in ("train", "validation", "replay", "anchor"):
            identity = getattr(command, scope + "_artifact_id")
            if identity is None:
                continue
            artifact, content = await self.deps.datasets.read_artifact(principal, identity)
            self.validate_artifact(artifact, scope)
            snapshot = await self.deps.datasets.get(principal, artifact.snapshot_id)
            if (
                snapshot.command.project_id != command.project_id
                or snapshot.command.kind != self.kind
            ):
                raise ApplicationError(
                    409,
                    "training_dataset_scope",
                    "Training needs owned data with exactly matching supervision kind",
                )
            selected = [e for e in snapshot.examples if e.split == artifact.command.split]
            for example in selected:
                prior = assigned.get(example.group_id)
                if prior and prior != scope:
                    raise ApplicationError(
                        409,
                        "training_evaluation_overlap",
                        "Train, validation, replay and anchor groups must be independent",
                    )
                assigned[example.group_id] = scope
            inputs[scope] = content
            manifests[scope] = digest(
                {"artifact": artifact.model_dump(mode="json"), "snapshot": snapshot.content_digest}
            )
            examples[scope] = len(selected)
            groups[scope] = len({e.group_id for e in selected})
        return inputs, manifests, examples, groups

    def validate_artifact(self, artifact: DatasetArtifact, scope: str) -> None:
        if artifact.command.split != ("train" if scope == "train" else "validation"):
            raise ApplicationError(
                409, "training_wrong_split", "Evaluation data must not carry training permission"
            )

    async def base(self, spec: BaseModelSpec) -> str:
        def verified() -> str:
            def signature() -> tuple[tuple[str, int, int, int, int], ...]:
                if spec.directory.is_symlink() or not spec.directory.is_dir():
                    raise ApplicationError(
                        409, "training_base_missing", "Configure a verified base model"
                    )
                values = []
                for p in sorted(spec.directory.rglob("*")):
                    if p.is_symlink():
                        raise ApplicationError(
                            409, "training_base_symlink", "Base paths cannot be symlinks"
                        )
                    stat = p.stat()
                    values.append(
                        (
                            str(p.relative_to(spec.directory)),
                            stat.st_ino,
                            stat.st_size,
                            stat.st_mtime_ns,
                            stat.st_ctime_ns,
                        )
                    )
                return tuple(values)

            before = signature()
            identity = digest(spec.model_dump(mode="json"))
            cached = self.base_cache.get(identity)
            if cached and cached[0] == before:
                return cached[1]
            result = verify_base(spec)
            if signature() != before:
                raise ApplicationError(
                    409,
                    "training_base_changed_during_verification",
                    "Base changed during verification",
                )
            self.base_cache[identity] = before, result
            return result

        return await anyio.to_thread.run_sync(verified)
