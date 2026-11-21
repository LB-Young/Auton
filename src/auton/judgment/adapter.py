import asyncio
import json
import os
import sys

from pydantic import JsonValue

from auton.judgment.config import JudgmentConfig
from auton.judgment.contracts import DecisionSource, JudgmentInfo, JudgmentRequest
from auton.kernel.ports import ApplicationError

POINTS = ("information_sufficiency", "executor_tier", "tool_domain", "skill_match")


class LayaAdapter:
    def __init__(self, config: JudgmentConfig) -> None:
        self.config = config
        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._health = "not_loaded"

    async def start(self) -> None:
        pass  # Optional native runtime is loaded only for an explicit decision request.

    async def close(self) -> None:
        process, self.process = self.process, None
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()

    def info(self) -> JudgmentInfo:
        return JudgmentInfo.model_validate(
            {
                "backend": "laya",
                "checkpoint": "convaiinnovations/laya/multilingual",
                "revision": self.config.revision,
                "health": self._health
                if (self.config.directory / "manifest.json").is_file()
                else "weights_missing",
                "decision_points": POINTS,
            }
        )

    async def _load(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return
        if not (self.config.directory / "manifest.json").is_file():
            raise ApplicationError(
                503, "weights_missing", "Download the pinned local Laya checkpoint"
            )
        # No inherited API keys/proxies; Hugging Face/Transformers may only use local files.
        env = {
            key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "TMPDIR") if key in os.environ
        }
        env.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            USE_TF="0",
            TOKENIZERS_PARALLELISM="false",
            OMP_NUM_THREADS="4",
            MKL_NUM_THREADS="4",
        )
        self.process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "auton.judgment.worker",
            str(self.config.directory.resolve()),
            self.config.device,
            self.config.revision,
            str(self.config.max_tokens),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            limit=262144,
        )
        assert self.process.stdout
        async with asyncio.timeout(self.config.load_timeout_seconds):
            value = json.loads(await self.process.stdout.readline())
        if value.get("ready") is not True or value.get("runtime") != "laya-0.3.20":
            raise ApplicationError(
                503, "local_model_load_failed", "Local Laya runtime could not load"
            )

    async def predict(
        self, request: JudgmentRequest
    ) -> tuple[DecisionSource, dict[str, JsonValue]]:
        async with self._lock:
            try:
                await self._load()
                assert self.process and self.process.stdin and self.process.stdout
                payload = {
                    "state": request.state,
                    "questions": {q.id: q.wire() for q in request.questions},
                }
                self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
                await self.process.stdin.drain()
                async with asyncio.timeout(self.config.timeout_seconds):
                    value = json.loads(await self.process.stdout.readline())
                if not isinstance(value.get("raw"), dict):
                    raise ApplicationError(
                        503, "local_inference_failed", "Local Laya inference failed"
                    )
                self._health = "available"
                return DecisionSource(
                    provider="laya",
                    repository="convaiinnovations/laya",
                    revision=self.config.revision,
                    subfolder="multilingual",
                    runtime_version="laya-0.3.20",
                    device=self.config.device,
                    max_tokens=self.config.max_tokens,
                    source="local",
                ), value["raw"]
            except BaseException as error:
                self._health = "unavailable"
                await self.close()
                if isinstance(error, TimeoutError):
                    raise ApplicationError(
                        503, "judgment_timeout", "Local decision timed out"
                    ) from error
                if isinstance(error, (ValueError, BrokenPipeError, ConnectionError)):
                    raise ApplicationError(
                        503, "judgment_unavailable", "Local decision worker failed"
                    ) from error
                raise


class MockJudgmentAdapter:
    def __init__(self, config: JudgmentConfig) -> None:
        self.config = config

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def info(self) -> JudgmentInfo:
        return JudgmentInfo(
            backend="mock",
            checkpoint="synthetic",
            revision="fixture-v1",
            health="test_fixture",
            decision_points=POINTS,
        )

    async def predict(
        self, request: JudgmentRequest
    ) -> tuple[DecisionSource, dict[str, JsonValue]]:
        answers: dict[str, JsonValue] = {}
        for q in request.questions:
            if q.type == "boolean":
                answers[q.id] = {"type": "noul", "noul": 0.8, "answer_confidence": 0.8}
            else:
                ids = (
                    [option.id for option in q.options]
                    if q.type == "choice"
                    else [str(i) for i in range(len(q.options))]
                )
                answers[q.id] = {
                    "type": q.type,
                    "choice": ids[0],
                    "probabilities": {key: 1.0 if i == 0 else 0.0 for i, key in enumerate(ids)},
                    "answer_confidence": 1.0,
                    **({"score": 0.0} if q.type == "score" else {}),
                }
        return DecisionSource(
            provider="mock",
            repository="synthetic",
            revision="fixture-v1",
            subfolder="none",
            runtime_version="synthetic-v1",
            device="none",
            max_tokens=1024,
            source="test",
        ), {"answers": answers}
