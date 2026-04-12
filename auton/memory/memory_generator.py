"""Memory Generator — LLM 驱动的项目长期记忆生成

设计原则（对齐 Claude Code memoryTypes.ts）：
  只存无法从代码库推导出的知识。代码结构、文件路径、命令、git 历史这些
  都可以直接搜索，不该进 memory。真正有价值的是：

  - feedback   用户对 Auton 行为的纠正和认可（带"为何"，避免重犯）
  - project    项目当前目标、决策背景、时间节点（不写代码本身）
  - user       用户背景、偏好、专业水平（帮助个性化回应）
  - reference  外部系统指针（Jira/Notion/Slack 等位置）

  两种模式：
  - 项目模式（MEMORY.md）：LLM 按上述 4 类提取并维护，每次会话结束后更新
  - 日期模式（memory.md）：LLM 从当天对话中提取最值得记住的 3–5 条经验
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agent.types import LLMContext
    from ..llm.base import LLMProvider


# ─── 项目 MEMORY.md 模板 ─────────────────────────────────────────────────────

PROJECT_MEMORY_TEMPLATE = """\
# 项目记忆

_只记录无法从代码库直接查到的知识。代码结构/文件路径/命令不在此处。_

## 行为反馈
_用户纠正或确认了哪些行为方式？每条格式：规则 → **为何**：原因 → **适用场景**：_

## 项目状态
_当前目标、关键决策背景、重要节点。不写代码本身，只写"为什么这样做"。_

## 用户背景
_用户的角色、专业水平、偏好风格。_

## 外部资源
_Jira、Notion、Slack、Grafana 等外部系统的指针（在哪找什么）。_
"""

# 每节内容上限（字符数）
_MAX_SECTION_CHARS = 1500
# 整个 MEMORY.md 上限（约 4000 token）
_MAX_TOTAL_CHARS = 8000

_MEMORY_SYSTEM_PROMPT = (
    "你是项目长期记忆维护助手，专门提取无法从代码库推导出的非显然知识。"
    "只输出纯文本，不要调用任何工具。"
    "严格保持章节标题和斜体说明行不变，只更新章节正文。"
)


# ─── 工具函数 ────────────────────────────────────────────────────────────────

def _extract_conversation_text(events: list[dict]) -> str:
    """从 session events 列表中提取原始对话文本（用户消息 + 助手文本回复）。

    只使用真实对话内容，排除 compact 压缩内容——记忆更新应基于原始对话元内容。
    """
    lines: list[str] = []
    for ev in events:
        ev_type = ev.get("type", "")

        if ev_type == "user-message":
            content = ev.get("content", "").strip()
            if content:
                lines.append(f"[用户] {content}")

        elif ev.get("role") == "assistant":
            # Message.to_dict() 格式：parts 数组，TextPart.content 字段
            for block in ev.get("parts", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("content", "").strip()
                    if text:
                        if len(text) > 800:
                            text = text[:800] + "…（截断）"
                        lines.append(f"[助手] {text}")
                        break

    return "\n\n".join(lines)


def _analyze_section_sizes(content: str) -> dict[str, int]:
    """分析 MEMORY.md 各章节的字符数。"""
    sections: dict[str, int] = {}
    current_section = ""
    current_chars = 0
    for line in content.splitlines():
        if line.startswith("## "):
            if current_section:
                sections[current_section] = current_chars
            current_section = line
            current_chars = 0
        else:
            current_chars += len(line) + 1
    if current_section:
        sections[current_section] = current_chars
    return sections


def _build_size_warning(content: str) -> str:
    """生成章节大小超限提醒。"""
    sizes = _analyze_section_sizes(content)
    total = sum(sizes.values())
    warnings: list[str] = []

    if total > _MAX_TOTAL_CHARS:
        warnings.append(
            f"\n\n**注意**：整个 MEMORY.md 当前约 {total} 字符，超过上限 {_MAX_TOTAL_CHARS}。"
            "请适当精简内容，保留最关键信息，尤其是【当前状态】和【错误与修正】章节。"
        )

    oversized = [
        f"- [{sec}] 约 {n} 字符（上限 {_MAX_SECTION_CHARS}）"
        for sec, n in sizes.items()
        if n > _MAX_SECTION_CHARS
    ]
    if oversized:
        warnings.append(
            "\n**以下章节超出单节上限，请精简**：\n" + "\n".join(oversized)
        )

    return "".join(warnings)


# ─── 项目 MEMORY.md 更新提示词 ───────────────────────────────────────────────

def get_project_memory_update_prompt(
    current_memory: str,
    conversation_text: str,
    project_name: str,
    session_id: str,
) -> str:
    """构造用于更新项目 MEMORY.md 的 LLM 提示词。"""
    size_warning = _build_size_warning(current_memory) if current_memory else ""

    prompt = f"""\
严重警告：只输出纯文本，不要调用任何工具。你的输出将直接写入 MEMORY.md 文件。

项目：{project_name}  会话：{session_id}  时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}

当前 MEMORY.md：
<current_memory>
{current_memory if current_memory else "(尚不存在，从模板创建)"}
</current_memory>

本次会话对话：
<session_conversation>
{conversation_text if conversation_text else "(无有效对话)"}
</session_conversation>

**记忆提取规则**（核心原则：只存无法从代码库推导的知识）：

【必须写入】
- 行为反馈：用户纠正了 Auton 的某个行为（"别这样"、"不要 X"）→ 写入规则 + 为何 + 适用场景
- 行为反馈：用户确认了某个非显然做法（"对，就这样"、"很好"）→ 同样记录，避免以后退回
- 项目状态：当前目标/里程碑/重要决策背景（而非代码实现）
- 用户背景：角色、专业水平、偏好（有新信息时才更新）
- 外部资源：新出现的外部系统/文档/工单指针

【绝对不写】以下内容可从代码库直接查到，写了是噪声：
- 文件路径、函数名、类名、代码结构
- shell 命令、工作流步骤
- 通用技术概念（语言特性、框架文档）
- git 历史、commit 内容

**操作要求**：
1. 从会话中识别符合"必须写入"的内容，整合到对应章节
2. 章节标题（## 开头）和斜体说明行（_xxx_）必须原样保留，不增删
3. 每节控制在 {_MAX_SECTION_CHARS} 字符以内，精简过时内容
4. 若某章节本次会话没有新内容，保持原样不动
5. 输出完整 MEMORY.md，从第一行到最后一行
{size_warning}

直接输出完整 MEMORY.md，不要包含任何解释："""
    return prompt


# ─── LLM 调用：更新项目 MEMORY.md ───────────────────────────────────────────

async def update_project_memory(
    llm: "LLMProvider",
    session_id: str,
    events: list[dict],
    memory_path: Path,
    project_name: str = "",
) -> bool:
    """使用 LLM 更新（或创建）项目 MEMORY.md。

    Args:
        llm: LLM Provider 实例
        session_id: 当前会话 ID
        events: session jsonl 事件列表
        memory_path: MEMORY.md 的绝对路径
        project_name: 项目名称（用于提示词标题）

    Returns:
        True 表示更新成功，False 表示失败或内容为空
    """
    from ..agent.message import Message
    from ..agent.types import LLMContext

    conversation_text = _extract_conversation_text(events)
    if not conversation_text.strip():
        return False

    # 读取已有 MEMORY.md（若存在）
    current_memory = (
        memory_path.read_text(encoding="utf-8")
        if memory_path.exists()
        else PROJECT_MEMORY_TEMPLATE
    )

    prompt = get_project_memory_update_prompt(
        current_memory=current_memory,
        conversation_text=conversation_text,
        project_name=project_name or str(memory_path.parent.parent.name),
        session_id=session_id,
    )

    # 构造请求消息
    user_msg = Message(role="user")
    user_msg.add_text(prompt)

    ctx = LLMContext(
        session_id=session_id,
        messages=[user_msg],
        tools=[],
        system_prompt=_MEMORY_SYSTEM_PROMPT,
        model=llm.model_name,
        max_tokens=min(4096, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    updated_content = full_text.strip()
    if not updated_content:
        return False

    # 安全校验：确保输出包含必要的章节头（防止 LLM 输出乱码）
    required_sections = ["## 行为反馈", "## 项目状态"]
    if not all(sec in updated_content for sec in required_sections):
        return False

    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(updated_content + "\n", encoding="utf-8")
    return True


# ─── 日期 memory.md：LLM 提取当天最值得记住的经验 ──────────────────────────

_DATE_MEMORY_SYSTEM_PROMPT = (
    "你是经验提取助手，专门从技术对话中提炼最值得长期记忆的非显然知识。"
    "只输出纯文本，不要调用任何工具。"
    "内容要极度精炼：每条一句话，写结论+原因，不写过程。"
)

_DATE_MEMORY_PROMPT_TEMPLATE = """\
严重警告：只输出纯文本，不要调用任何工具。

以下是今天某个会话的对话内容：

<conversation>
{conversation_text}
</conversation>

请提取 1–5 条最值得长期记住的经验或教训。

**提取标准**（只记符合下列任一条的）：
- 用户纠正了某个错误做法（为何错 + 正确做法）
- 确认了某个非显然的决策（为何这样选）
- 遇到了容易踩的坑（原因 + 避免方法）
- 学到了某个重要的设计原则或约束

**绝对不写**：
- 文件路径、函数名（可搜索）
- 命令或工作流步骤（可重跑）
- 已完成的任务列表（无后续价值）
- 通用技术介绍

**输出格式**（直接列条目，不要标题和解释）：
- [一句话结论，写清楚"什么情况下"+"应该怎样"+"为何"]

示例：
- 记忆更新不应存代码结构，那些可以 grep 到，存了只是噪声
- 技能目录用 ~/.auton/skill（单数），用复数路径会找不到文件
"""


async def make_date_memory_entry_llm(
    llm: "LLMProvider",
    session_id: str,
    events: list[dict],
    started_at: float | None = None,
) -> str:
    """使用 LLM 从会话中提取最值得记住的经验，生成日期 memory.md 条目。"""
    from ..agent.message import Message
    from ..agent.types import LLMContext

    ts = started_at or time.time()
    time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
    short_id = session_id[:8] if len(session_id) >= 8 else session_id

    conversation_text = _extract_conversation_text(events)
    if not conversation_text.strip():
        return ""

    prompt = _DATE_MEMORY_PROMPT_TEMPLATE.format(
        conversation_text=conversation_text
    )

    user_msg = Message(role="user")
    user_msg.add_text(prompt)

    ctx = LLMContext(
        session_id=session_id,
        messages=[user_msg],
        tools=[],
        system_prompt=_DATE_MEMORY_SYSTEM_PROMPT,
        model=llm.model_name,
        max_tokens=min(1024, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    bullets = full_text.strip()
    if not bullets:
        return ""

    return (
        f"\n## 会话 {short_id} ({time_str})\n"
        f"{bullets}\n"
    )


def _make_date_memory_entry_simple(
    session_id: str,
    events: list[dict],
    started_at: float | None = None,
) -> str:
    """简单模板生成日期 memory.md 条目（LLM 不可用时的降级实现）。"""
    ts = started_at or time.time()
    time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
    short_id = session_id[:8] if len(session_id) >= 8 else session_id

    user_messages: list[str] = []
    for ev in events:
        if ev.get("type") == "user-message":
            content = ev.get("content", "").strip()
            if content and content not in user_messages:
                user_messages.append(content)

    if user_messages:
        main_request = "；".join(user_messages[:2])
        if len(main_request) > 120:
            main_request = main_request[:120] + "…"
    else:
        main_request = "（无有效对话）"

    return (
        f"\n## 会话 {short_id} ({time_str})\n"
        f"- {main_request}\n"
    )


async def append_date_memory_entry(
    session_id: str,
    events: list[dict],
    memory_path: Path,
    llm: "LLMProvider | None" = None,
    today: date | None = None,
    started_at: float | None = None,
) -> None:
    """将会话经验提取条目写入日期 memory.md。

    - 优先使用 LLM 提取有价值的经验。
    - LLM 不可用时降级为简单模板。
    - 若该 session 已有条目（mid-session 触发），则替换原有条目。
    """
    d = today or date.today()
    short_id = session_id[:8] if len(session_id) >= 8 else session_id

    if llm is not None:
        try:
            entry = await make_date_memory_entry_llm(llm, session_id, events, started_at)
        except Exception:
            entry = _make_date_memory_entry_simple(session_id, events, started_at)
    else:
        entry = _make_date_memory_entry_simple(session_id, events, started_at)

    if not entry:
        return

    memory_path.parent.mkdir(parents=True, exist_ok=True)

    if not memory_path.exists():
        header = (
            f"# 日期记忆 — {d.isoformat()}\n\n"
            "_记录当日对话中最值得长期记住的非显然经验与教训。_\n"
        )
        memory_path.write_text(header + entry, encoding="utf-8")
        return

    existing = memory_path.read_text(encoding="utf-8")

    # 若该 session 已有条目，替换整块
    marker = f"## 会话 {short_id}"
    if marker in existing:
        pattern = re.compile(
            rf"(## 会话 {re.escape(short_id)}.*?)(?=\n## 会话 |\Z)",
            re.DOTALL,
        )
        updated = pattern.sub(entry.lstrip("\n"), existing)
        memory_path.write_text(updated, encoding="utf-8")
    else:
        with open(memory_path, "a", encoding="utf-8") as f:
            f.write(entry)
