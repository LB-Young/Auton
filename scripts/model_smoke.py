"""Explicit opt-in real DeepSeek protocol baseline; never part of CI."""

import asyncio
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from auton.constitution.config import ConstitutionConfig, Principal, Usage
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import SecretStoreFactory
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig
from auton.model.contracts import ModelMessage, ModelRequest, ToolSpec
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies


async def main() -> dict[str, object]:
    deps = RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))
    events = EventLogFactory().create(KernelConfig(data_directory=Path(".auton_local/smoke")))
    control = ConstitutionFactory().create(
        ConstitutionConfig(
            remote_providers=("deepseek",), budget=Usage(tokens=20000, cost_microusd=10000)
        ),
        ConstitutionDependencies(events, deps),
    )
    gateway = ModelGatewayFactory().create(
        ModelConfig(), GatewayDependencies(control, events, deps, SecretStoreFactory().create())
    )
    results = []
    async with AsyncExitStack() as stack:
        for resource in (events, control, gateway):
            stack.push_async_callback(resource.close)
            await resource.start()
        for model in ("deepseek-flash", "deepseek-v4-pro"):
            for mode in ("text", "json", "tools"):
                req = ModelRequest(
                    model_id=model,
                    request_id=str(uuid4()),
                    principal=Principal(owner="protocol-smoke", role="runtime"),
                    goal_id="smoke-" + str(uuid4()),
                    data_domain="public",
                    max_output_tokens=64,
                    messages=(
                        ModelMessage(
                            role="user",
                            content=(
                                "Reply with only the word OK."
                                if mode == "text"
                                else "Return a JSON object with key ok and boolean true."
                                if mode == "json"
                                else "Call echo with value equal to ok."
                            ),
                        ),
                    ),
                    output_format="json" if mode == "json" else "text",
                    tools=(
                        ToolSpec(
                            name="echo",
                            parameters={
                                "type": "object",
                                "properties": {"value": {"type": "string"}},
                                "required": ["value"],
                                "additionalProperties": False,
                            },
                        ),
                    )
                    if mode == "tools"
                    else (),
                    tool_choice="required" if mode == "tools" else "auto",
                )
                result = await gateway.generate(req)
                assert result.source == "remote" and result.finish_reason != "length"
                if mode == "json":
                    assert json.loads(result.content).get("ok") is True
                elif mode == "tools":
                    assert result.tool_calls[0].arguments.get("value") == "ok"
                else:
                    assert result.content.strip() == "OK"
                entry = {
                    "model_id": model,
                    "mode": mode,
                    "reported_model": result.reported_model,
                    "fingerprint": result.system_fingerprint,
                    "finish_reason": result.finish_reason,
                    "usage": result.usage.model_dump(),
                    "latency_ms": result.latency_ms,
                    "source": result.source,
                }
                results.append(entry)
                print(json.dumps(entry), flush=True)
    return {"timestamp": deps.now().isoformat(), "results": results}


if __name__ == "__main__":
    report = asyncio.run(main())
    path = Path("test-results/deepseek-smoke.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
