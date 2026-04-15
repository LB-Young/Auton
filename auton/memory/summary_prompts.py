"""memory/summary_prompts.py — 会话后摘要提示词（独立于 agent/subagent 体系）"""

from __future__ import annotations


# ─── 系统提示词 ────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM_PROMPT = (
    "你是专业的技术对话摘要助手，擅长从技术对话中提取最关键的非显而易见的信息。"
    "只输出纯文本，不要调用任何工具。"
    "摘要用于后续语义检索，应简洁精准——每条要点只写结论和理由，不写可从代码库直接查到的内容。"
    "每条要点末尾附引用标签 [↑msg:xxxxxxxx]（message_id 前 8 位）。"
)


# ─── 分段摘要 Prompt 模板 ───────────────────────────────────────────────────────

SESSION_SUMMARY_PROMPT_TEMPLATE = """\
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


def get_session_summary_prompt(
    session_id: str,
    start_idx: int,
    end_idx: int,
    conversation_text: str,
) -> str:
    """构建会话分段摘要 prompt。

    Args:
        session_id:         会话 ID
        start_idx:          起始事件索引
        end_idx:            结束事件索引
        conversation_text:  对话文本（由 build_conversation_text 生成）

    Returns:
        格式化后的 prompt 字符串
    """
    return SESSION_SUMMARY_PROMPT_TEMPLATE.format(
        session_id=session_id,
        start_idx=start_idx,
        end_idx=end_idx,
        count=end_idx - start_idx + 1,
        conversation_text=conversation_text,
    )


# ─── 对话文本构建 ──────────────────────────────────────────────────────────────

def build_conversation_text(events: list[dict]) -> str:
    """从事件列表提取可读对话文本，用于 LLM 摘要输入。

    只使用原始对话内容：用户消息、助手文本回复。
    排除 compact 压缩内容——摘要应基于真实对话，不引入二次压缩的噪声。
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
            a_id = ev.get("message_id", "")
            a_tag = f" #msg:{a_id[:8]}" if a_id else ""
            for block in ev.get("parts", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("content", "").strip()
                    if text:
                        if len(text) > 600:
                            text = text[:600] + "…（截断）"
                        parts.append(f"[助手{a_tag}] {text}")
                        break

    return "\n\n".join(parts)


def has_meaningful_content(events: list[dict]) -> bool:
    """检查事件列表是否包含有意义的对话内容（非空用户消息或助手回复）"""
    for ev in events:
        ev_type = ev.get("type", "")
        if ev_type == "user-message" and ev.get("content", "").strip():
            return True
        if ev.get("role") == "assistant":
            for block in ev.get("parts", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    if block.get("content", "").strip():
                        return True
    return False
