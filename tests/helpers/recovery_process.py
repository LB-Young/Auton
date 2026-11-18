"""Two independent OS processes exercise the public runtime/recovery ports."""

import asyncio
import hashlib
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from auton.agent.contracts import Acceptance, AgentConfig, CreateRun, RunCommand
from auton.agent.factory import AgentRuntimeFactory
from auton.agent.service import AgentDependencies
from auton.constitution.config import ConstitutionConfig, Principal
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import SecretStoreFactory
from auton.context.contracts import ContextConfig
from auton.context.factory import ContextEngineFactory
from auton.context.service import ContextDependencies
from auton.experience.contracts import ExperienceConfig, RecoveryCommand
from auton.experience.factory import ExperienceFactory
from auton.experience.service import ExperienceDependencies
from auton.genome.contracts import GenomeConfig, Project
from auton.genome.factory import GenomeFactory
from auton.genome.service import GenomeDependencies
from auton.judgment.config import JudgmentConfig
from auton.judgment.factory import JudgmentFactory
from auton.judgment.service import JudgmentDependencies
from auton.kernel.config import KernelConfig
from auton.kernel.events import EventScope
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies, ModelGateway
from auton.tools.config import ToolConfig
from auton.tools.contracts import ToolReceipt
from auton.tools.factory import ToolHostFactory
from auton.tools.service import ToolDependencies


async def main(root: Path, phase: str) -> None:
    user = Principal(owner="restart-contract-fixture", role="user")
    clock = RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))
    events = EventLogFactory().create(KernelConfig(data_directory=root / "events"))
    policy = ConstitutionFactory().create(
        ConstitutionConfig(), ConstitutionDependencies(events, clock)
    )
    models = ModelGatewayFactory().create(
        ModelConfig(backend="mock", fixture_scenario="agent_acceptance"),
        GatewayDependencies(policy, events, clock, SecretStoreFactory().create()),
    )
    judgment = JudgmentFactory().create(
        JudgmentConfig(backend="mock"), JudgmentDependencies(policy, policy, events, clock, models)
    )
    tools = ToolHostFactory().create(
        ToolConfig(directory=root / "tools"),
        ToolDependencies(policy, policy, policy, events, clock),
    )
    assets = GenomeFactory().create(
        GenomeConfig(directory=root / "assets"), GenomeDependencies(policy, events, clock)
    )
    context = ContextEngineFactory().create(
        ContextConfig(), ContextDependencies(tools, assets, models, policy, events, clock)
    )
    agent = AgentRuntimeFactory().create(
        AgentConfig(directory=str(root / "agent")),
        AgentDependencies(context, models, tools, judgment, assets, events, clock, policy),
    )
    experience = ExperienceFactory().create(
        ExperienceConfig(directory=root / "experience"),
        ExperienceDependencies(events, agent, assets, context, clock),
    )
    async with AsyncExitStack() as stack:
        for resource in (
            events,
            policy,
            models,
            judgment,
            tools,
            assets,
            context,
            agent,
            experience,
        ):
            stack.push_async_callback(resource.close)
            await resource.start()
        state_path = root / "state.json"
        if phase in {"prepare", "crash"}:
            await assets.create_project(
                user, Project(id="project", title="Process restart contract")
            )
            await tools.create_workspace(user, "workspace", "Process files", False)
            assert isinstance(models, ModelGateway)
            reached, release = asyncio.Event(), asyncio.Event()
            original = models.provider.stream
            from collections.abc import AsyncGenerator

            from auton.model.config import ModelSpec
            from auton.model.contracts import ModelChunk, ModelRequest

            async def gate(
                request: ModelRequest, spec: ModelSpec
            ) -> AsyncGenerator[ModelChunk, None]:
                if phase == "prepare" and any(m.role == "tool" for m in request.messages):
                    reached.set()
                    await release.wait()
                async for chunk in original(request, spec):
                    yield chunk

            models.provider.stream = gate  # type: ignore[method-assign]
            if phase == "crash":
                execute = tools.execute

                async def crash_after_ack(
                    principal: Principal, operation_id: str, approval_id: str | None = None
                ) -> ToolReceipt:
                    receipt = await execute(principal, operation_id, approval_id)
                    assert receipt.outcome == "succeeded" and receipt.artifact
                    current = await agent.get(user, run.id)
                    await asyncio.to_thread(
                        state_path.write_text,
                        json.dumps(
                            {
                                "run": current.id,
                                "operation": operation_id,
                                "version": current.version,
                                "crashed": True,
                            }
                        ),
                    )
                    os._exit(0)  # Test child only: no graceful cleanup/checkpoint after receipt.

                tools.execute = crash_after_ack  # type: ignore[method-assign]
            run = await agent.create(
                user,
                CreateRun(
                    request_id="restart-run",
                    project_id="project",
                    workspace_id="workspace",
                    model_id="fixture-model",
                    goal="Write hello newline to notes.md",
                    allowed_tools=("file.write",),
                    acceptance=Acceptance(
                        kind="file", path="notes.md", sha256=hashlib.sha256(b"hello\n").hexdigest()
                    ),
                ),
            )
            async with asyncio.timeout(20):
                while True:
                    run = await agent.get(user, run.id)
                    if run.status == "waiting_approval":
                        await agent.command(
                            user,
                            run.id,
                            RunCommand(
                                request_id="approve-write",
                                expected_goal_revision=1,
                                action="approve",
                            ),
                        )
                    if reached.is_set():
                        break
                    await asyncio.sleep(0.01)
                await agent.command(
                    user,
                    run.id,
                    RunCommand(request_id="pause-safe", expected_goal_revision=1, action="pause"),
                )
                release.set()
                while True:
                    run = await agent.get(user, run.id)
                    if run.status == "paused":
                        break
                    await asyncio.sleep(0.01)
            assert len(run.receipts) == 1 and run.receipts[0].artifact
            await asyncio.to_thread(
                state_path.write_text,
                json.dumps(
                    {
                        "run": run.id,
                        "operation": run.receipts[0].operation_id,
                        "version": run.version,
                    }
                ),
            )
        else:
            saved = json.loads(await asyncio.to_thread(state_path.read_text))
            run = await agent.get(user, saved["run"])
            assert run.status == ("blocked" if saved.get("crashed") else "paused")
            assert run.version == saved["version"] + int(bool(saved.get("crashed")))
            view = await experience.trajectory(user, "project", run.id, "recovery")
            assert view.recovery_available and view.checkpoint, view.recovery_reasons
            await experience.recover(
                user,
                "project",
                run.id,
                RecoveryCommand(
                    request_id="recover-process",
                    expected_version=run.version,
                    expected_goal_revision=1,
                    checkpoint_event_id=view.checkpoint.event_id,
                ),
            )
            async with asyncio.timeout(20):
                while True:
                    run = await agent.get(user, run.id)
                    if run.status in {"succeeded", "failed", "blocked"}:
                        break
                    await asyncio.sleep(0.01)
            assert run.status == "succeeded", run.reason
            assert (
                len(run.receipts) == 1
                and run.receipts[0].operation_id == saved["operation"]
                and run.receipts[0].attempt == 1
            )
            rows = await events.read(
                limit=1000, scope=EventScope.model_validate({"operation_id": saved["operation"]})
            )
            assert sum(row.event.kind == "tool.started" for row in rows) == 1
            print(json.dumps({"status": run.status, "tool_dispatches": 1, "source": run.source}))


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2]))
