"""Explicit local Laya baseline, including semantic mistakes; never downloads during inference."""

import asyncio
import json
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from auton.constitution.config import ConstitutionConfig, Principal
from auton.constitution.factory import ConstitutionDependencies, ConstitutionFactory
from auton.constitution.secrets import SecretStoreFactory
from auton.judgment.config import JudgmentConfig
from auton.judgment.contracts import JudgmentRequest
from auton.judgment.factory import JudgmentFactory
from auton.judgment.questions import JudgmentQuestionsFactory
from auton.judgment.service import JudgmentDependencies
from auton.kernel.config import KernelConfig
from auton.kernel.factory import EventLogFactory
from auton.kernel.ports import RuntimeDependencies
from auton.model.config import ModelConfig
from auton.model.factory import ModelGatewayFactory
from auton.model.gateway import GatewayDependencies

CASES = (
    ("arithmetic", "请计算 1 加 1，只返回结果。", "small_2b"),
    ("extract", "从文本“姓名：小王，年龄：20岁”提取年龄，仅返回数字。", "small_2b"),
    (
        "architecture",
        "设计支持百万并发的多租户数据库：比较一致性、分片、故障恢复和成本，给出迁移方案。",
        "strong",
    ),
    (
        "debug",
        "分析分布式任务系统在网络分区后重复扣款的根因，并设计可证明的幂等与补偿机制。",
        "strong",
    ),
    (
        "english_simple",
        "Extract the email from: Contact us at hello@example.test. Return only the address.",
        "small_2b",
    ),
    (
        "english_complex",
        (
            "Design a fault tolerant distributed transaction protocol. "
            "Prove safety under network partitions."
        ),
        "strong",
    ),
)


async def main() -> dict[str, object]:
    deps = RuntimeDependencies(now=lambda: datetime.now(UTC), new_id=lambda: str(uuid4()))
    events = EventLogFactory().create(
        KernelConfig(data_directory=Path(".auton_local/judgment-smoke"))
    )
    control = ConstitutionFactory().create(
        ConstitutionConfig(), ConstitutionDependencies(events, deps)
    )
    models = ModelGatewayFactory().create(
        ModelConfig(),
        GatewayDependencies(
            control, events, deps, SecretStoreFactory().create(Path("/tmp/auton-nonexistent.env"))
        ),
    )
    judgment = JudgmentFactory().create(
        JudgmentConfig(), JudgmentDependencies(control, control, events, deps, models)
    )
    records = []
    async with AsyncExitStack() as stack:
        for resource in (events, control, models, judgment):
            stack.push_async_callback(resource.close)
            await resource.start()
        for name, state, expected in CASES:
            result = await judgment.decide(
                JudgmentRequest(
                    request_id=str(uuid4()),
                    principal=Principal(owner="local-baseline"),
                    goal_id="baseline-" + str(uuid4()),
                    state=state,
                    questions=JudgmentQuestionsFactory().create(),
                )
            )
            tier = next(a.selected_id for a in result.answers if a.question_id == "executor")
            record = {
                "case": name,
                "expected_tier": expected,
                "tier_correct": tier == expected,
                "expected_sufficient": "yes",
                "result": result.model_dump(mode="json"),
            }
            records.append(record)
            print(
                json.dumps(
                    {
                        "case": name,
                        "tier": tier,
                        "correct": tier == expected,
                        "latency_ms": result.latency_ms,
                    }
                ),
                flush=True,
            )
        # Stable IDs remain the output contract when options are reordered. Record actual changes.
        questions = JudgmentQuestionsFactory().create()
        tier_question = questions[1]
        reordered = tier_question.model_copy(
            update={"options": tuple(reversed(tier_question.options))}
        )
        result = await judgment.decide(
            JudgmentRequest(
                request_id=str(uuid4()),
                principal=Principal(owner="local-baseline"),
                goal_id="reorder-" + str(uuid4()),
                state=CASES[0][1],
                questions=(reordered,),
            )
        )
        records.append({"case": "option_reorder", "result": result.model_dump(mode="json")})
    return {
        "timestamp": deps.now().isoformat(),
        "records": records,
        "automatic_application_enabled": False,
        "limitation": "Small hand-labelled smoke set, not a held-out task-quality benchmark.",
    }


if __name__ == "__main__":
    report = asyncio.run(main())
    path = Path("test-results/laya-smoke.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
