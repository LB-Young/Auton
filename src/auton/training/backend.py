"""A digest-pinned, network-free worker. No host shell commands or inherited secrets."""

import asyncio
import json
from pathlib import Path

from auton.kernel.ports import ApplicationError
from auton.training.contracts import TrainingConfig
from auton.training.ports import TrainingBackendPort, WorkerState


class DisabledBackend:
    async def start(
        self, identity: str, job_directory: Path, base: Path, manifest_digest: str
    ) -> None:
        raise ApplicationError(
            503, "training_backend_disabled", "Configure a training worker backend"
        )

    async def state(self, identity: str, manifest_digest: str) -> WorkerState:
        return WorkerState(status="absent")

    async def stop(self, identity: str, manifest_digest: str) -> None:
        return None


class DockerTrainingBackend:
    def __init__(self, config: TrainingConfig) -> None:
        self.config = config

    async def command(self, *arguments: str, missing_ok: bool = False) -> str:
        try:
            process = await asyncio.create_subprocess_exec(
                "docker",
                *arguments,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"},
            )
            try:
                output, error = await asyncio.wait_for(process.communicate(), 30)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise ApplicationError(
                    503, "training_worker_timeout", "Worker control timed out"
                ) from None
        except FileNotFoundError:
            raise ApplicationError(
                503, "training_worker_unavailable", "Docker CLI is unavailable"
            ) from None
        if len(output) + len(error) > 100000:
            raise ApplicationError(
                503, "training_worker_response_limit", "Oversized control response"
            )
        if process.returncode and not missing_ok:
            raise ApplicationError(
                503, "training_worker_control_failed", "Worker control failed; inspect deployment"
            )
        return output.decode() if process.returncode == 0 else ""

    def name(self, identity: str) -> str:
        return "auton-train-" + identity

    async def state(self, identity: str, manifest_digest: str) -> WorkerState:
        output = await self.command("container", "inspect", self.name(identity), missing_ok=True)
        if not output:
            # Distinguish missing container from a failed daemon/connection.
            await self.command("info", "--format", "{{.ServerVersion}}")
            return WorkerState(status="absent")
        state = json.loads(output)[0]
        if state.get("Config", {}).get("Labels", {}).get("auton.manifest") != manifest_digest:
            raise ApplicationError(
                409, "training_worker_identity_conflict", "Worker has another frozen manifest"
            )
        observed = state["State"]
        if observed["Running"]:
            return WorkerState(status="running")
        if observed["Status"] == "created":
            return WorkerState(status="absent", reason="created_not_started")
        return WorkerState(
            status="succeeded" if observed["ExitCode"] == 0 else "failed",
            reason="oom"
            if observed.get("OOMKilled")
            else "worker_exit_" + str(observed["ExitCode"]),
        )

    def create_arguments(
        self, identity: str, job: Path, base: Path, manifest: str
    ) -> tuple[str, ...]:
        # Paths come only from operator config/private staging, never an API shell fragment.
        if any(any(c in str(p) for c in (",", "\n", "\x00")) for p in (job, base)):
            raise ApplicationError(
                409, "training_invalid_mount", "Unsupported mount path characters"
            )
        worker = (
            Path(__file__)
            .with_name("decision_worker.py" if self.config.workload == "decision" else "worker.py")
            .resolve()
        )
        arguments = [
            "create",
            "--pull",
            "never",
            "--log-driver",
            "none",
            "--name",
            self.name(identity),
            "--label",
            "auton.manifest=" + manifest,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "64",
            "--memory",
            str(self.config.memory_mb) + "m",
            "--memory-swap",
            str(self.config.memory_mb) + "m",
            "--cpus",
            str(self.config.cpus),
            "--user",
            "65534:65534",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=256m,mode=1777",
            "--mount",
            f"type=bind,src={job / 'input'},dst=/input,readonly",
            "--mount",
            f"type=bind,src={job / 'output'},dst=/output",
            "--mount",
            f"type=bind,src={base},dst=/base,readonly",
            "--mount",
            f"type=bind,src={worker},dst=/worker.py,readonly",
            "--env",
            "HF_HUB_OFFLINE=1",
            "--env",
            "TRANSFORMERS_OFFLINE=1",
            "--env",
            "HF_HOME=/tmp/hf",
            "--env",
            "HOME=/tmp",
        ]
        if self.config.workload == "decision":
            for filename, destination in (
                ("worker.py", "/common.py"),
                ("decision_metrics.py", "/decision_metrics.py"),
            ):
                arguments.extend(
                    (
                        "--mount",
                        f"type=bind,src={Path(__file__).with_name(filename).resolve()},dst={destination},readonly",
                    )
                )
        if self.config.device == "cuda":
            arguments.extend(("--gpus", "all"))
        arguments.extend(
            (
                "--entrypoint",
                "python",
                self.config.image,
                "-I",
                "/worker.py",
                "/input/manifest.json",
            )
        )
        return tuple(arguments)

    async def start(
        self, identity: str, job_directory: Path, base: Path, manifest_digest: str
    ) -> None:
        state = await self.state(identity, manifest_digest)
        if state.status == "running":
            return
        if state.status in {"succeeded", "failed"}:
            raise ApplicationError(
                409, "training_worker_already_finished", "Never replay a terminal worker"
            )
        if state.reason != "created_not_started":
            await self.command(
                *self.create_arguments(identity, job_directory, base, manifest_digest)
            )
        await self.command("start", self.name(identity))

    async def stop(self, identity: str, manifest_digest: str) -> None:
        state = await self.state(identity, manifest_digest)
        if state.status == "running":
            await self.command("stop", "--time", "5", self.name(identity))
        # Keep the terminal container identity as an idempotency fence until operator retention.


class TrainingBackendFactory:
    def create(self, config: TrainingConfig) -> TrainingBackendPort:
        return DockerTrainingBackend(config) if config.backend == "docker" else DisabledBackend()
