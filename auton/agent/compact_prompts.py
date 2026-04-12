"""Agent Compact Prompts — LLM 会话压缩提示词

参考 Claude Code 的 compact 实现（services/compact/prompt.ts），
适配 Auton 的消息格式与中文场景。

压缩策略：
  - BASE 压缩：第一次压缩，无历史摘要，对所有中间消息全量摘要
  - 增量压缩：待压缩段中存在已有 [历史压缩] 摘要，将其与新增轮次
              合并送入 LLM，生成新的综合摘要（rolling summary）

LLM 输出格式：
  <analysis>...</analysis>   ← 思考草稿，parse 时去除
  <summary>...</summary>     ← 最终摘要，parse 后保留
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .message import Message
    from .types import LLMContext
    from ..llm.base import LLMProvider


# ─── 系统提示词 ────────────────────────────────────────────────────────────────

COMPACT_SYSTEM_PROMPT = (
    "你是专业的对话摘要助手，擅长从技术对话中提取结构化信息。"
    "只输出纯文本，不要调用任何工具。"
)

# ─── 禁用工具前言（防止 LLM 在压缩时尝试工具调用）──────────────────────────────

_NO_TOOLS_PREAMBLE = """\
严重警告：只输出纯文本，不要调用任何工具。
- 不要使用 Read、Bash、Grep、Write 或任何其他工具
- 对话上下文中已包含你需要的所有信息
- 工具调用会被拒绝，你只有这一次输出机会
- 你的完整输出必须是：一个 <analysis> 块，紧跟一个 <summary> 块

"""

_NO_TOOLS_TRAILER = (
    "\n\n提醒：不要调用任何工具。只输出纯文本 —— "
    "<analysis> 块加 <summary> 块。工具调用会被拒绝。"
)

# ─── 分析指令（思考草稿，帮助 LLM 提高摘要质量）────────────────────────────────

_ANALYSIS_INSTRUCTION = """\
在给出最终摘要之前，请用 <analysis> 标签包裹你的分析过程，确保覆盖所有必要的要点：

1. 按时间顺序分析对话的每个部分，对每个部分仔细识别：
   - 用户的明确请求和意图
   - 助手处理请求的方式与思路
   - 关键决策、技术概念和代码模式
   - 具体细节：文件名、完整代码片段、函数签名、文件修改
   - 遇到的错误及修复方式
   - 用户的具体反馈（尤其是要求改变方向的部分）
2. 检查技术准确性和完整性。"""

# ─── 摘要格式模板 ──────────────────────────────────────────────────────────────

_SUMMARY_STRUCTURE = """\
你的摘要应包含以下部分：

1. 主要请求和意图：详细记录用户的所有明确请求和意图
2. 关键技术概念：列出所有重要的技术概念、技术栈和框架
3. 涉及的文件和代码：列举被查看、修改或创建的具体文件（含完整代码片段）
4. 错误和修复：列出遇到的错误及修复方式，以及用户的具体反馈
5. 问题解决：记录已解决的问题和正在进行的调试工作
6. 全部用户消息：列出所有非工具结果的用户消息（对理解意图至关重要）
7. 待办事项：列出明确被要求但尚未完成的任务
8. 当前工作：精确描述本次压缩前正在进行的工作（含文件名和代码片段）
9. 下一步（可选）：与最近工作直接相关的下一步，必须附带对话原文引用

输出格式：

<analysis>
[你的分析过程，确保覆盖所有要点]
</analysis>

<summary>
1. 主要请求和意图：
   [详细描述]

2. 关键技术概念：
   - [概念1]
   - [概念2]

3. 涉及的文件和代码：
   - [文件名]
     - [重要性说明]
     - [关键代码片段]

4. 错误和修复：
   - [错误描述]：[修复方式]

5. 问题解决：
   [描述]

6. 全部用户消息：
   - [消息1]
   - [消息2]

7. 待办事项：
   - [任务1]

8. 当前工作：
   [精确描述]

9. 下一步（可选）：
   [下一步及原文引用]
</summary>"""

# ─── 完整压缩提示词（无历史摘要，首次压缩）──────────────────────────────────────

_BASE_COMPACT_BODY = f"""\
你的任务是为当前对话创建详细的结构化摘要，重点关注用户的明确请求和助手的操作过程。
摘要应当充分记录技术细节、代码模式和架构决策，以便在不丢失上下文的情况下继续工作。

{_ANALYSIS_INSTRUCTION}

{_SUMMARY_STRUCTURE}

请根据对话内容，按照上述格式提供精确完整的摘要。"""

# ─── 增量压缩提示词（已有历史摘要，合并新增轮次）────────────────────────────────

_INCREMENTAL_COMPACT_BODY = f"""\
你的任务是更新对话摘要。你将看到：
1. 之前的历史压缩摘要（以 [历史压缩] 开头的系统消息）
2. 之后新增的对话轮次

请将新增对话的内容整合到已有摘要中，生成一份完整的综合摘要。要求：
- 保留历史摘要中所有重要的技术细节
- 加入新增对话的关键信息
- 更新"当前工作"和"待办事项"等时效性内容（以最新对话为准）
- 如新对话与历史摘要有冲突，以新对话内容为准

{_ANALYSIS_INSTRUCTION}

{_SUMMARY_STRUCTURE}

请基于历史摘要和新增对话，生成完整更新后的综合摘要。"""


def get_compact_prompt() -> str:
    """获取完整压缩提示词（首次压缩，无历史摘要）"""
    return _NO_TOOLS_PREAMBLE + _BASE_COMPACT_BODY + _NO_TOOLS_TRAILER


def get_incremental_compact_prompt() -> str:
    """获取增量压缩提示词（已有历史摘要，合并新增轮次）"""
    return _NO_TOOLS_PREAMBLE + _INCREMENTAL_COMPACT_BODY + _NO_TOOLS_TRAILER


# ─── 输出解析 ─────────────────────────────────────────────────────────────────

def parse_compact_summary(raw: str) -> str:
    """从 LLM 原始输出中解析摘要。

    - 去除 <analysis> 思考草稿（仅用于提升质量，无信息价值）
    - 提取 <summary> 内容，格式化为可读文本
    - 若无 <summary> 标签，直接返回清理后的全文（降级处理）
    """
    text = raw

    # 去除 <analysis> 块（贪婪匹配，跨行）
    text = re.sub(r"<analysis>[\s\S]*?</analysis>", "", text, flags=re.DOTALL)

    # 提取 <summary> 内容
    summary_match = re.search(r"<summary>([\s\S]*?)</summary>", text, re.DOTALL)
    if summary_match:
        content = summary_match.group(1).strip()
        text = re.sub(
            r"<summary>[\s\S]*?</summary>",
            f"对话摘要：\n{content}",
            text,
            flags=re.DOTALL,
        )

    # 清理多余空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── LLM 调用助手（供 SessionProcessor 和 CompactCommand 共用）──────────────────

async def generate_compact_summary(
    llm: "LLMProvider",
    session_id: str,
    messages_to_summarize: list["Message"],
    *,
    has_prior_summary: bool = False,
) -> str:
    """调用 LLM 生成压缩摘要。

    Args:
        llm: LLM Provider 实例
        session_id: 当前会话 ID（用于构建 LLMContext）
        messages_to_summarize: 待摘要的消息列表（已包含历史摘要上下文，若有）
        has_prior_summary: 是否存在历史压缩摘要（决定使用哪套提示词）

    Returns:
        解析后的摘要文本（去除 <analysis> 草稿）

    Raises:
        ValueError: LLM 未返回有效文本
    """
    from .message import Message
    from .types import LLMContext

    prompt = (
        get_incremental_compact_prompt()
        if has_prior_summary
        else get_compact_prompt()
    )

    # 将压缩请求作为最后一条 user 消息追加
    compact_request = Message(role="user")
    compact_request.add_text(prompt)
    all_messages = list(messages_to_summarize) + [compact_request]

    ctx = LLMContext(
        session_id=session_id,
        messages=all_messages,
        tools=[],  # 压缩时禁止工具调用
        system_prompt=COMPACT_SYSTEM_PROMPT,
        model=llm.model_name,
        # 摘要最多 8192 token，避免超过模型限制
        max_tokens=min(8192, llm.max_tokens),
        temperature=0.0,
    )

    full_text = ""
    async for event in llm.stream(ctx):
        if event.type == "text_delta":
            full_text += getattr(event, "delta", "")

    if not full_text.strip():
        raise ValueError("LLM compact 调用未返回有效文本")

    return parse_compact_summary(full_text)
