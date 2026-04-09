"""问候语生成（本地收集 + 模型生成）。"""

from __future__ import annotations

from ..agent.message import Message
from ..agent.types import LLMContext
from ..core.logging import get_logger
from ..llm.base import LLMProvider
from .greeting_context import GreetingContext

DEFAULT_GREETING = "你好！我是 Auton。有什么我可以帮你的吗？"

log = get_logger("cli.greeting")


def _format_list(items: list[str], empty: str) -> str:
    if not items:
        return empty
    return "\n".join(f"- {item}" for item in items)


def build_greeting_prompt(ctx: GreetingContext) -> str:
    return f"""
你是 Auton 的启动问候生成器。请基于输入事实，输出一段专业、简洁、友好的中文问候语。

硬性要求：
1. 输出最多 8 行，避免冗长。
2. 如果"近两天回顾"完全为空，输出简短通用问候，不要强行编造回顾。
3. 如果有回顾内容，先简要回顾，再给出"我可以帮你做什么"。
4. 不要询问项目模式，不要使用标题，不要输出 YAML/JSON，不要解释规则。

输入事实：
- 当前目录：{ctx.cwd}
- 当前目录是否已有项目历史：{ctx.has_project_history}
- 今天：{ctx.today.isoformat()}
- 昨天：{ctx.yesterday.isoformat()}

近两天 dates 记忆片段：
{_format_list(ctx.date_memory_snippets, "- （无）")}

近两天项目记忆片段（来自 project_modify.md 关联项目）：
{_format_list(ctx.project_memory_snippets, "- （无）")}
""".strip()


async def generate_greeting(llm: LLMProvider, ctx: GreetingContext, session_id: str) -> str:
    prompt = build_greeting_prompt(ctx)
    user_msg = Message(role="user")
    user_msg.add_text(prompt)
    llm_ctx = LLMContext(
        session_id=session_id,
        messages=[user_msg],
        tools=[],
        system_prompt="你只负责输出最终问候语正文，不要输出思考过程。",
        model=llm.model_name,
        max_tokens=min(llm.max_tokens, 512),
        temperature=min(max(llm.temperature, 0.1), 0.7),
    )

    chunks: list[str] = []
    try:
        async for event in llm.stream(llm_ctx):
            event_type = getattr(event, "type", "")
            if event_type == "text_delta":
                chunks.append(getattr(event, "delta", ""))
            elif event_type == "text_finish":
                full_text = getattr(event, "full_text", "")
                if full_text and not chunks:
                    chunks.append(full_text)
    except Exception as exc:  # pragma: no cover - exercised via unit test
        log.warning("failed to generate greeting via LLM: %s", exc)
        return DEFAULT_GREETING

    greeting = "".join(chunks).strip()
    if not greeting:
        return DEFAULT_GREETING
    return greeting
