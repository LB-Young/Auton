"""Summary Generator — LLM 驱动的会话分段摘要

摘要定位：用于后续新 query 的语义召回，每条摘要对应 session.jsonl 中的一段事件。

设计原则（参考 Claude Code session-memory 的信息密度要求）：
  - 信息完整：包含所有对新 query 可能有用的关键内容（请求、决策、文件、错误、命令）
  - 可检索：摘要文本本身即为语义搜索的语料
  - 有锚点：每条摘要标注来源事件在 session.jsonl 中的行范围，便于追溯

SUMMARY.md 格式：
  # 会话摘要索引 — {scope}

  ## 段落 001 — 会话 abc12345（事件 0–44，sessions/abc12345.jsonl 第 1–45 行）
  **主要请求**：...
  **关键技术内容**：...
  **涉及的文件与代码**：...
  **决策与结论**：...
  **错误与修正**：...（若无则省略）
  **命令与工作流**：...（若无则省略）
  **待处理事项**：...（若无则省略）

  ## 段落 002 — 会话 abc12345（事件 45–89，sessions/abc12345.jsonl 第 46–90 行）
  ...
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..llm.base import LLMProvider


# ─── LLM 提示词 ──────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = (
    "你是专业的技术对话摘要助手，擅长从技术对话中提取最关键的非显而易见的信息。"
    "只输出纯文本，不要调用任何工具。"
    "摘要用于后续语义检索，应简洁精准——每条要点只写结论和理由，不写可从代码库直接查到的内容。"
    "每条要点末尾附引用标签 [↑msg:xxxxxxxx]（message_id 前 8 位）。"
)

_SUMMARY_PROMPT_TEMPLATE = """\
严重警告：只输出纯文本，不要调用任何工具。

会话 {session_id} 的对话片段（事件 {start_idx}–{end_idx}，共 {count} 条）：

<conversation>
{conversation_text}
</conversation>

**引用规则**：每条要点末尾加 [↑msg:xxxxxxxx]；涉及多条则 [↑msg:aaa, msg:bbb]。

**不要写入摘要的内容**（可从代码库推导，写了也是噪声）：
- 文件路径、函数名、代码结构（grep 可查）
- shell 命令和工作流（可重跑）
- 通用技术描述（查文档即可）

**输出格式（4 个字段，每字段 1–4 条要点，没有则写"无"）**：

**请求摘要**：
[用户提出了什么，一句话每条，突出意图而非措辞]

**关键决策**：
[选了什么方案、为什么、放弃了什么——非显然的判断才值得记]

**错误与教训**：
[出了什么问题、如何修复、为何之前的做法不对——避免重蹈覆辙]

**待处理**：
[明确提出但未完成的事项]
"""


# ─── 对话文本提取（独立实现避免循环导入；只取原始对话，不含 compact 内容）────────

def _build_conversation_text(events: list[dict]) -> str:
    """从事件列表提取可读对话文本，用于 LLM 摘要输入。

    只使用原始对话内容：用户消息、助手文本回复。
    排除 compact 压缩内容——摘要应基于真实对话元内容，不引入二次压缩的噪声。
    每条消息标注 message_id 前缀（前 8 位），供 LLM 生成引用标签时对应。
    截断：过长的助手回复（保留前 600 字符），避免 prompt 超长。
    """
    parts: list[str] = []
    for ev in events:
        ev_type = ev.get("type", "")
        msg_id = ev.get("message_id", "")
        id_tag = f" #msg:{msg_id[:8]}" if msg_id else ""

        if ev_type == "user-message":
            content = ev.get("content", "").strip()
            if content:
                parts.append(f"[用户{id_tag}] {content}")

        elif ev.get("role") == "assistant":
            # 助手消息的 message_id 在顶层字段
            a_id = ev.get("message_id", "")
            a_tag = f" #msg:{a_id[:8]}" if a_id else ""
            # 从 parts 数组中提取 text 块（Message.to_dict 格式）
            raw_parts = ev.get("parts", [])
            for block in raw_parts:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("content", "").strip()
                    if text:
                        if len(text) > 600:
                            text = text[:600] + "…（截断）"
                        parts.append(f"[助手{a_tag}] {text}")
                        break  # 每条助手消息只取第一段文字

    return "\n\n".join(parts)


def _has_meaningful_content(events: list[dict]) -> bool:
    """检查事件列表是否包含有意义的对话内容（非空用户消息或助手回复）。"""
    for ev in events:
        ev_type = ev.get("type", "")
        if ev_type == "user-message" and ev.get("content", "").strip():
            return True
        if ev.get("role") == "assistant":
            # Message.to_dict() 格式：parts 数组，TextPart.content 字段
            for block in ev.get("parts", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    if block.get("content", "").strip():
                        return True
    return False


# ─── 摘要条目格式化 ───────────────────────────────────────────────────────────

def _count_existing_segments(summary_path: Path) -> int:
    """统计 SUMMARY.md 中已有的段落数（用于新段落编号）。"""
    if not summary_path.exists():
        return 0
    text = summary_path.read_text(encoding="utf-8")
    return len(re.findall(r"^## 段落 \d+", text, re.MULTILINE))


def get_last_summarized_idx(summary_path: Path, session_id: str) -> int:
    """从 SUMMARY.md 读取该 session 已摘要到的最大事件索引（end_idx）。

    返回值含义与 _last_summarized_idx 相同：
      -1  → 该 session 尚未被摘要过，下次应从索引 0 开始
      N   → 事件 0–N 已摘要，下次应从 N+1 开始

    设计目的：使 start_idx 可从持久化文件（SUMMARY.md）中恢复，
    解耦对进程内状态（processor._last_summarized_idx）的依赖。
    Web 模式下每次请求都创建新 processor，进程内状态每次都从 -1 重置，
    依赖此函数才能避免重复摘要已处理的事件。

    解析逻辑：匹配 session_id 对应的段落头（含 short_id 前 8 位），
    取最后一个匹配段落的 end_idx。
    """
    if not summary_path.exists():
        return -1

    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    text = summary_path.read_text(encoding="utf-8")

    # 格式: ## 段落 NNN — 会话 abc12345（事件 M–N，...）
    pattern = re.compile(
        rf"## 段落 \d+ — 会话 {re.escape(short_id)}（事件 \d+–(\d+)，",
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        return -1

    # 取最大的 end_idx（不一定是最后一条，防止乱序）
    return max(int(m) for m in matches)


def _format_summary_entry(
    segment_idx: int,
    session_id: str,
    start_idx: int,
    end_idx: int,
    summary_text: str,
) -> str:
    """将 LLM 输出格式化为 SUMMARY.md 的一个段落条目。

    每条包含：
      - 段落编号和来源定位（会话 ID + 事件范围 + jsonl 行范围）
      - LLM 生成的结构化摘要正文
    """
    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    start_line = start_idx + 1  # 事件索引 0 → 第 1 行
    end_line = end_idx + 1

    header = (
        f"## 段落 {segment_idx:03d} — 会话 {short_id}"
        f"（事件 {start_idx}–{end_idx}，"
        f"sessions/{session_id}.jsonl 第 {start_line}–{end_line} 行）"
    )
    return f"{header}\n\n{summary_text.strip()}\n"


# ─── LLM 调用 ────────────────────────────────────────────────────────────────

async def _call_llm_for_summary(
    llm: "LLMProvider",
    session_id: str,
    conversation_text: str,
    start_idx: int,
    end_idx: int,
) -> str:
    """调用 LLM 生成对话片段的结构化摘要。

    Returns:
        摘要文本（纯文本，无工具调用）

    Raises:
        ValueError: LLM 未返回有效文本
    """
    from ..agent.message import Message
    from ..agent.types import LLMContext

    prompt = _SUMMARY_PROMPT_TEMPLATE.format(
        session_id=session_id,
        start_idx=start_idx,
        end_idx=end_idx,
        count=end_idx - start_idx + 1,
        start_line=start_idx + 1,
        end_line=end_idx + 1,
        conversation_text=conversation_text,
    )

    user_msg = Message(role="user")
    user_msg.add_text(prompt)

    ctx = LLMContext(
        session_id=session_id,
        messages=[user_msg],
        tools=[],
        system_prompt=_SUMMARY_SYSTEM_PROMPT,
        model=llm.model_name,
        max_tokens=min(4096, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    if not full_text.strip():
        raise ValueError("LLM 摘要调用未返回有效文本")

    return full_text.strip()


# ─── 核心接口：生成并追加摘要 ─────────────────────────────────────────────────

async def generate_and_append_summary(
    llm: "LLMProvider",
    session_id: str,
    events: list[dict],
    start_idx: int,
    summary_path: Path,
    scope: str = "",
) -> int:
    """为 events[start_idx:] 生成 LLM 摘要并追加到 SUMMARY.md。

    Args:
        llm: LLM Provider 实例
        session_id: 当前会话 ID
        events: session jsonl 全部事件列表
        start_idx: 本次摘要起始事件索引（上次摘要结束后的下一条）
        summary_path: SUMMARY.md 的绝对路径
        scope: 标题说明（项目路径或日期）

    Returns:
        新的 last_summarized_idx（即 len(events) - 1）；
        若无需摘要则返回 start_idx - 1（不变）。
    """
    end_idx = len(events) - 1
    if start_idx > end_idx:
        return start_idx - 1

    events_slice = events[start_idx:]
    if not _has_meaningful_content(events_slice):
        return start_idx - 1

    conversation_text = _build_conversation_text(events_slice)
    if not conversation_text.strip():
        return start_idx - 1

    # 生成 LLM 摘要
    summary_text = await _call_llm_for_summary(
        llm, session_id, conversation_text, start_idx, end_idx
    )

    # 确定段落编号（基于已有段落数 + 1）
    segment_idx = _count_existing_segments(summary_path) + 1
    entry = _format_summary_entry(segment_idx, session_id, start_idx, end_idx, summary_text)

    # 写入 SUMMARY.md
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    if not summary_path.exists():
        scope_line = f"_{scope}_\n\n" if scope else ""
        header = (
            f"# 会话摘要索引\n\n"
            f"{scope_line}"
            "_每条摘要对应 session.jsonl 中的一段事件，"
            "包含关键信息用于后续语义检索。_\n\n"
        )
        summary_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n" + entry)

    return end_idx
