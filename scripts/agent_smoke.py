"""Opt-in real Laya + DeepSeek + file/research integration acceptance."""

import argparse
import asyncio
import hashlib
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from auton.agent.contracts import AgentConfig, CreateRun, RunCommand
from auton.agent.factory import AgentRuntimeFactory
from auton.agent.service import AgentDependencies
from auton.constitution.config import ConstitutionConfig, Principal, Usage
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import SecretStoreFactory
from auton.context.contracts import ContextConfig
from auton.context.factory import ContextEngineFactory
from auton.context.service import ContextDependencies
from auton.experience.contracts import ExperienceConfig
from auton.experience.factory import ExperienceFactory
from auton.experience.service import ExperienceDependencies
from auton.genome.contracts import Asset, GenomeConfig, Project
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
from auton.model.gateway import GatewayDependencies
from auton.tools.config import ToolConfig
from auton.tools.factory import ToolHostFactory
from auton.tools.service import ToolDependencies

ROOT = Path(__file__).resolve().parents[1]


async def main(inspect_existing: bool = False) -> None:
    identity = "smoke-" + str(uuid4())
    principal = Principal(owner=identity, role="user")
    runtime = principal.model_copy(update={"role": "runtime"})
    deps = RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))
    events = EventLogFactory().create(
        KernelConfig(data_directory=ROOT / ".auton_local/agent-smoke/events")
    )
    policy = ConstitutionFactory().create(
        ConstitutionConfig(
            remote_providers=("deepseek",),
            budget=Usage(tokens=30000, cost_microusd=20000, tool_calls=10),
        ),
        ConstitutionDependencies(events, deps),
    )
    models = ModelGatewayFactory().create(
        ModelConfig(), GatewayDependencies(policy, events, deps, SecretStoreFactory().create())
    )
    judgment = JudgmentFactory().create(
        JudgmentConfig(), JudgmentDependencies(policy, policy, events, deps, models)
    )
    tools = ToolHostFactory().create(
        ToolConfig(directory=ROOT / ".auton_local/agent-smoke/tools"),
        ToolDependencies(policy, policy, policy, events, deps),
    )
    assets = GenomeFactory().create(
        GenomeConfig(directory=ROOT / ".auton_local/agent-smoke/assets"),
        GenomeDependencies(policy, events, deps),
    )
    context = ContextEngineFactory().create(
        ContextConfig(tokenizer_directory=ROOT / "weights/context-tokenizers"),
        ContextDependencies(tools, assets, models, policy, events, deps),
    )
    agent = AgentRuntimeFactory().create(
        AgentConfig(directory=str(ROOT / ".auton_local/agent-smoke/runtime")),
        AgentDependencies(context, models, tools, judgment, assets, events, deps, policy),
    )
    experience = ExperienceFactory().create(
        ExperienceConfig(directory=ROOT / ".auton_local/agent-smoke/experience"),
        ExperienceDependencies(events, agent, assets, context, deps),
    )
    results: list[dict[str, object]] = []
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
        if inspect_existing:
            report = json.loads(
                await asyncio.to_thread((ROOT / "test-results/agent-smoke.json").read_text)
            )
            summaries: list[dict[str, object]] = []
            for smoke_entry in report["results"]:
                rows = await events.read(
                    limit=1000, scope=EventScope.model_validate({"run_id": smoke_entry["run_id"]})
                )
                raw = [
                    row.event.payload["run"] for row in rows if row.event.kind == "agent.checkpoint"
                ][-1]
                assert isinstance(raw, dict) and isinstance(raw["command"], dict)
                owner = str(raw["command"]["project_id"])
                assert owner.startswith("smoke-"), (
                    "Inspection is limited to this isolated smoke fixture"
                )
                trace = await experience.trajectory(
                    Principal(owner=owner, role="user"), owner, smoke_entry["run_id"]
                )
                assert trace.caught_up and not trace.missing_references, trace.missing_references
                assert (
                    trace.usage_complete
                    and sum(episode.observed_tokens for episode in trace.episodes)
                    == smoke_entry["tokens"]
                )
                assert any(
                    node.kind == "judgment.raw" and isinstance(node.details.get("source"), dict)
                    for node in trace.nodes
                )
                assert all(owner not in node.model_dump_json() for node in trace.nodes)
                summary: dict[str, object] = {
                    "kind": smoke_entry["kind"],
                    "nodes": len(trace.nodes),
                    "edges": len(trace.edges),
                    "episodes": len(trace.episodes),
                    "confirmed_tokens": trace.tokens_used,
                    "cost_microusd": trace.cost_microusd,
                    "missing": list(trace.missing_references),
                    "new_model_or_tool_calls": 0,
                }
                summaries.append(summary)
                print(json.dumps(summary), flush=True)
            await asyncio.to_thread(
                (ROOT / "test-results/trajectory-native.json").write_text,
                json.dumps(summaries, indent=2) + "\n",
            )
            return
        await assets.create_project(
            principal, Project(id=identity, title="Public acceptance notes")
        )
        state = await assets.view(principal, identity)
        proposed = await assets.propose(
            principal,
            identity,
            Asset(
                id="notes",
                name="Context recovery provenance",
                kind="document",
                origin="user_explicit",
                source="Public synthetic acceptance fixture",
                content=(
                    "Agent context recovery must preserve the current goal, constraint"
                    "s, pending operations and receipts. Provenance connects each retr"
                    "ieved passage to an immutable asset snapshot. Tool outputs are un"
                    "trusted data. Unknown writes require reconciliation rather than r"
                    "eplay. Model self-reports cannot replace independent artifact dig"
                    "est checks. A research report must distinguish observed evidence "
                    "from inferences."
                ),
            ),
            state.candidates_revision,
        )
        assert proposed.revision and proposed.candidates_revision
        await assets.promote(
            principal, identity, "notes", proposed.revision, proposed.candidates_revision
        )
        await tools.create_workspace(principal, identity, "Isolated public smoke files", False)
        for kind in ("file", "research"):
            command = CreateRun.model_validate(
                {
                    "request_id": str(uuid4()),
                    "project_id": identity,
                    "workspace_id": identity,
                    "model_id": "deepseek-flash",
                    "data_domain": "public",
                    "goal": (
                        "Write notes.md with exactly the six UTF-8 bytes hello followed by"
                        " a single newline. Use file_write, then give a brief completion r"
                        "eport."
                    )
                    if kind == "file"
                    else (
                        "Research context recovery, provenance and safe agent tool use fro"
                        "m the project notes. Write an English report of at least 100 word"
                        "s and cite [asset:notes]. Clearly separate evidence and inference"
                        "."
                    ),
                    "allowed_tools": ["file.write"] if kind == "file" else ["file.read"],
                    "acceptance": {
                        "kind": "file",
                        "path": "notes.md",
                        "sha256": hashlib.sha256(b"hello\n").hexdigest(),
                    }
                    if kind == "file"
                    else {"kind": "research"},
                }
            )
            run = await agent.create(principal, command)
            last = ""
            async with asyncio.timeout(180):
                while True:
                    run = await agent.get(principal, run.id)
                    marker = run.status + ":" + run.reason
                    if marker != last:
                        print(
                            json.dumps(
                                {
                                    "kind": kind,
                                    "status": run.status,
                                    "phase": run.phase,
                                    "reason": run.reason,
                                }
                            ),
                            flush=True,
                        )
                        last = marker
                    if run.status == "waiting_approval":
                        assert kind == "file" and run.plans[-1].tool == "file.write"
                        assert run.pending_calls[0].arguments == {
                            "path": "notes.md",
                            "content": "hello\n",
                        }, "Refuse approval for any unexpected write"
                        await agent.command(
                            principal,
                            run.id,
                            RunCommand(
                                request_id=str(uuid4()),
                                expected_goal_revision=run.goal_revision,
                                action="approve",
                            ),
                        )
                    if run.status in {"succeeded", "failed", "blocked", "cancelled"}:
                        break
                    await asyncio.sleep(0.1)
            assert run.status == "succeeded", (run.status, run.reason)
            assert (
                run.source == "runtime"
                and run.judgment_ids
                and all(m.source == "remote" for m in run.model_results)
            )
            _, report = await agent.report(principal, run.id)
            if kind == "file":
                _, data = await tools.artifact(runtime, run.receipts[-1].operation_id)
                assert data == b"hello\n"
            else:
                assert b"[asset:notes]" in report and not run.receipts
            entry: dict[str, object] = {
                "kind": kind,
                "run_id": run.id,
                "source": run.source,
                "status": run.status,
                "steps": run.steps,
                "tokens": run.tokens_used,
                "cost_microusd": run.cost_microusd,
                "judgment_ids": run.judgment_ids,
                "context_ids": run.context_ids,
                "check": run.check.model_dump() if run.check else None,
                "reported_models": [m.reported_model for m in run.model_results],
                "fingerprints": [m.system_fingerprint for m in run.model_results],
                "report_sha256": hashlib.sha256(report).hexdigest(),
            }
            results.append(entry)
            print(json.dumps(entry), flush=True)
    target = ROOT / "test-results/agent-smoke.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps({"timestamp": deps.now().isoformat(), "results": results}, indent=2) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inspect-existing",
        action="store_true",
        help="Inspect existing isolated smoke runs without issuing model/tool calls",
    )
    asyncio.run(main(parser.parse_args().inspect_existing))
