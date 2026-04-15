# Auton 上下文压缩与会话摘要优化方案

> 本文档定义 Auton 的**实时会话压缩**和**会话后摘要**两套独立系统的完整设计规范。
> 两者均独立于主 agent / subagent 体系，各自拥有专属的 prompt 和逻辑模块。
>
> **目标读者**：初级工程师（可直接照此文档实现）

---

## 一、现状分析与优化目标

### 1.1 现有系统的问题

| 模块 | 文件 | 问题 |
|---|---|---|
| 实时压缩 | `auton/agent/compact_prompts.py` | prompt 结构简单；无工具截断；尾部保护不精细 |
| 会话压缩 | `auton/agent/session.py` | 固定 150K token 阈值，不区分模型上下文长度；无 tool pair 边界对齐 |
| 记忆摘要 | `auton/memory/session_summarizer.py` | 仅规则提取（正则匹配），无 LLM 摘要；信息密度低 |
| 摘要生成 | `auton/memory/summary_generator.py` | prompt 与实时压缩耦合，未独立 |

### 1.2 优化目标

1. **实时压缩**：双阈值触发 + 智能工具截断 + tool pair 边界对齐 + 独立 prompt
2. **会话后摘要**：分 block LLM 摘要 + 结构化输出 + 独立 prompt + 语义检索友好
3. **完全解耦**：压缩/摘要均为 standalone 组件，不依赖主 agent 或 subagent 体系

---

## 二、实时会话压缩系统

### 2.1 触发条件

采用**双阈值触发**，任一满足即触发压缩：

```python
# 阈值常量（可配置）
ABSOLUTE_TOKEN_THRESHOLD = 150_000  # 固定 token 数（适用于 Claude 100K 等长上下文模型）
DEFAULT_THRESHOLD_PERCENT = 0.60     # 上下文窗口百分比（适用于短上下文模型）
```

```python
def should_compress(
    token_count: int,
    context_length: int,
    *,
    absolute_threshold: int = ABSOLUTE_TOKEN_THRESHOLD,
    percent_threshold: float = DEFAULT_THRESHOLD_PERCENT,
) -> bool:
    """
    判断是否需要触发压缩。

    两个条件满足任意一个即触发：
    1. token 数 >= 绝对阈值（默认 150,000）
    2. token 数 >= 上下文窗口 * 比例阈值

    Args:
        token_count: 当前消息列表的 token 数
        context_length: 模型上下文窗口长度
        absolute_threshold: 绝对 token 阈值
        percent_threshold: 上下文窗口比例

    Returns:
        True 如果需要压缩
    """
    percent_limit = int(context_length * percent_threshold)
    return token_count >= absolute_threshold or token_count >= percent_limit
```

**示例**：

| 模型 | 上下文窗口 | 绝对阈值 | 比例阈值 (60%) | 实际触发点 |
|---|---|---|---|---|
| Claude 100K | 100,000 | 150,000 | 60,000 | 60,000（比例先到） |
| Claude 200K | 200,000 | 150,000 | 120,000 | 120,000（比例先到） |
| GPT-4 Turbo 128K | 128,000 | 150,000 | 76,800 | 76,800（比例先到） |

### 2.2 消息保留策略

| 内容类型 | 策略 | 说明 |
|---|---|---|
| System Prompt | 始终保留 | 索引 0 的消息不参与压缩 |
| 首条用户消息 | 始终保留 | 用户原始意图，防止丢失 |
| 已有的 `[历史压缩]` 摘要 | 保留并作为上下文 | 增量压缩时前置拼接 |
| 尾部消息 | 按 40K token 保护 | 最近工作不丢失 |
| tool_call + tool_result pair | 永不切断 | 防止 API 报错；边界自动对齐 |
| 大输出工具（> 200 字符） | 截断为占位符 | pre-pass 阶段完成，无 LLM 调用 |
| 小输出工具（≤ 200 字符） | 保留完整 | 短命令/结果用户可能追问 |
| 用户文本消息 | 保留完整 | 理解意图的关键 |
| Assistant 文本回复 | 保留完整 | 技术决策和代码片段 |

### 2.3 压缩边界计算

压缩边界分为三段：

```
[stable_prefix] + [messages_to_compress] + [messages_to_keep]
     ↑                    ↑                       ↑
 system + 历史摘要      待 LLM 摘要              尾部保留
```

```python
from dataclasses import dataclass
from typing import Sequence


@dataclass
class CompressBoundary:
    """压缩边界计算结果"""
    stable_prefix: list["Message"]         # 头部稳定消息（system + 历史摘要）
    messages_to_compress: list["Message"]  # 待压缩的中间消息
    messages_to_keep: list["Message"]      # 尾部保留消息（按 token 预算）
    has_prior_summary: bool                # 是否有历史摘要（决定用 base 还是 incremental prompt）
    original_count: int = 0                # 原始消息数（用于日志）
    compressed_count: int = 0               # 实际压缩的消息数（用于日志）


def compute_compress_boundary(
    messages: list["Message"],
    *,
    protect_turns: int = 2,
    tail_token_budget: int = 40_000,
    min_tail_messages: int = 2,
) -> CompressBoundary:
    """
    计算压缩边界，将消息列表划分为三段。

    算法：
    1. 找出稳定前缀（system prompt + 连续的历史压缩摘要）
    2. 确定尾部起点（保留最近 protect_turns 轮用户对话）
    3. 若尾部 token 超出预算，自动缩减保留轮次
    4. 对齐 tool pair 边界

    Args:
        messages: 完整消息列表
        protect_turns: 保留最近几轮用户对话
        tail_token_budget: 尾部 token 上限
        min_tail_messages: 尾部最小消息数

    Returns:
        CompressBoundary 对象（不修改原始 messages）
    """
    total = len(messages)
    if total <= 2:
        return CompressBoundary(
            stable_prefix=list(messages),
            messages_to_compress=[],
            messages_to_keep=[],
            has_prior_summary=False,
            original_count=total,
            compressed_count=0,
        )

    # ── Step 1: 找稳定前缀 ────────────────────────────────────────────────
    stable_prefix_end = 1  # 至少包含 system prompt
    has_prior_summary = False
    while stable_prefix_end < total:
        msg = messages[stable_prefix_end]
        text = msg.get_text().strip()
        if msg.role == "system" and text.startswith("[历史压缩]"):
            stable_prefix_end += 1
            has_prior_summary = True
        else:
            break

    compressible_total = total - stable_prefix_end
    if compressible_total <= 1:
        return CompressBoundary(
            stable_prefix=list(messages[:stable_prefix_end]),
            messages_to_compress=[],
            messages_to_keep=list(messages[stable_prefix_end:]),
            has_prior_summary=has_prior_summary,
            original_count=total,
            compressed_count=0,
        )

    # ── Step 2: 确定尾部起点 ──────────────────────────────────────────────
    turn_starts = _find_real_user_turn_starts(messages, start=stable_prefix_end)
    preserved_turns = min(protect_turns, len(turn_starts)) if turn_starts else 0

    if preserved_turns > 0:
        tail_start = turn_starts[-preserved_turns]
    else:
        tail_start = max(stable_prefix_end + 1, total - min_tail_messages)

    # ── Step 3: 若尾部 token 超出预算，缩减保留轮次 ──────────────────────
    while tail_start > stable_prefix_end:
        recent_tokens = _estimate_tokens(messages[tail_start:])
        if recent_tokens <= tail_token_budget:
            break
        if preserved_turns > 1:
            preserved_turns -= 1
            tail_start = turn_starts[-preserved_turns]
        elif _contains_internal_messages(messages[tail_start:]):
            # 包含内部续上下文消息，不再缩减
            break
        else:
            tail_start = min(total - 1, tail_start + 1)

    # ── Step 4: 对齐 tool pair 边界 ──────────────────────────────────────
    tail_start = _align_boundary_backward(messages, tail_start)

    return CompressBoundary(
        stable_prefix=list(messages[:stable_prefix_end]),
        messages_to_compress=list(messages[stable_prefix_end:tail_start]),
        messages_to_keep=list(messages[tail_start:]),
        has_prior_summary=has_prior_summary,
        original_count=total,
        compressed_count=tail_start - stable_prefix_end,
    )


def _find_real_user_turn_starts(
    messages: Sequence["Message"],
    *,
    start: int = 0,
) -> list[int]:
    """
    返回真实用户轮次的起点索引。

    工具结果（[tool: xxx]）和命令结果（[command: xxx]）虽然以 user message
    形式写入 session，但不能作为新的"用户轮次"边界，否则会把最近一轮
    工具交互拆断。

    Args:
        messages: 消息列表
        start: 起始索引

    Returns:
        真实用户消息的索引列表
    """
    starts = []
    for idx in range(start, len(messages)):
        msg = messages[idx]
        if msg.role != "user":
            continue
        text = msg.get_text().strip()
        if text.startswith("[tool:") or text.startswith("[command:"):
            continue
        starts.append(idx)
    return starts


def _contains_internal_messages(messages: Sequence["Message"]) -> bool:
    """检查消息列表是否包含内部续上下文消息"""
    for msg in messages:
        if msg.role != "user":
            continue
        text = msg.get_text().strip()
        if text.startswith("[tool:") or text.startswith("[command:"):
            return True
    return False


def _align_boundary_backward(messages: list["Message"], idx: int) -> int:
    """
    将 compress_end 回拉到 tool pair 开始处。

    如果边界落在 tool result 中间（连续 tool 消息的末尾），
    回拉到 parent assistant 消息之前，确保整个 tool_call + tool_result
    group 都被包含在待压缩区域或待保留区域，不会被切断。
    """
    while idx > 0 and messages[idx - 1].role == "tool":
        idx -= 1
    return idx


def _estimate_tokens(messages: Sequence["Message"]) -> int:
    """估算消息列表的 token 数（简化版，使用字符数 / 4 + 固定 overhead）"""
    total = 0
    for msg in messages:
        total += len(msg.get_text()) // 4 + 10  # 10 = role/metadata overhead
        if hasattr(msg, "tool_calls"):
            for tc in msg.tool_calls or []:
                args = getattr(getattr(tc, "function", None), "arguments", "") or ""
                total += len(args) // 4
    return total
```

### 2.4 工具输出截断（Pre-pass）

在 LLM 摘要之前，先做一次无 LLM 调用的工具输出截断，节省 token 成本。

```python
TOOL_OUTPUT_PLACEHOLDER = "[工具输出已清理]"
TOOL_OUTPUT_THRESHOLD = 200  # 字符数，超过此长度截断


def prune_tool_results(
    messages: list["Message"],
    protect_tail_count: int = 15,
) -> tuple[list["Message"], int]:
    """
    将超过阈值的工具输出替换为占位符（无 LLM 调用）。

    从后往前遍历，保护最近 protect_tail_count 条消息不被截断，
    其余超过阈值的工具输出替换为占位符。

    Args:
        messages: 消息列表
        protect_tail_count: 尾部保留的工具结果数量

    Returns:
        (处理后的消息列表, 截断数量)
    """
    result = []
    pruned = 0
    prune_boundary = len(messages) - protect_tail_count

    for i, msg in enumerate(messages):
        if i < prune_boundary and msg.role == "tool":
            content = msg.get_text()
            if len(content) > TOOL_OUTPUT_THRESHOLD:
                pruned_msg = _replace_tool_with_placeholder(msg, TOOL_OUTPUT_PLACEHOLDER)
                result.append(pruned_msg)
                pruned += 1
                continue
        result.append(msg)

    return result, pruned


def _replace_tool_with_placeholder(msg: "Message", placeholder: str) -> "Message":
    """将工具消息的内容替换为占位符，返回新消息（不修改原消息）"""
    new_msg = Message(role="tool")
    new_msg._content = placeholder  # 直接设置内容
    new_msg._message_id = msg.message_id
    if hasattr(msg, "tool_call_id"):
        new_msg._tool_call_id = msg.tool_call_id
    return new_msg
```

### 2.5 Tool Pair 清理（Post-pass）

压缩后可能出现孤立的 tool_call 或 tool_result，需要清理以避免 API 报错。

```python
def sanitize_tool_pairs(messages: list[dict]) -> list[dict]:
    """
    修复压缩后的 orphaned tool_call / tool_result 对。

    两种失败模式：
    1. tool_result 引用了被压缩的 tool_call → 删除 orphaned result
    2. assistant message 有 tool_calls 但结果被压缩 → 插入 stub result

    Args:
        messages: 压缩后的消息列表（dict 格式）

    Returns:
        清理后的消息列表
    """
    # 收集所有存活的 tool_call id
    surviving_call_ids = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                cid = _get_tool_call_id(tc)
                if cid:
                    surviving_call_ids.add(cid)

    # 收集所有 tool_result 的 id
    result_call_ids = set()
    for msg in messages:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id", "")
            if cid:
                result_call_ids.add(cid)

    # 删除 orphaned tool_result
    orphaned_results = result_call_ids - surviving_call_ids
    if orphaned_results:
        messages = [
            m for m in messages
            if not (m.get("role") == "tool" and m.get("tool_call_id") in orphaned_results)
        ]

    # 插入 stub tool_result
    missing_results = surviving_call_ids - result_call_ids
    if missing_results:
        patched = []
        for msg in messages:
            patched.append(msg)
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    cid = _get_tool_call_id(tc)
                    if cid in missing_results:
                        patched.append({
                            "role": "tool",
                            "content": "[结果已压缩，详见上文摘要]",
                            "tool_call_id": cid,
                        })
        messages = patched

    return messages


def _get_tool_call_id(tc) -> str:
    """从 tool_call 中提取 id（支持 dict 和对象）"""
    if isinstance(tc, dict):
        return tc.get("id", "")
    return getattr(tc, "id", "") or ""
```

### 2.6 压缩主流程

```python
from dataclasses import dataclass


@dataclass
class CompressConfig:
    """实时会话压缩配置"""
    # 触发阈值（双阈值，任一满足即触发）
    token_threshold: int = 150_000
    threshold_percent: float = 0.60

    # 尾部保护
    protect_turns: int = 2
    tail_token_budget: int = 40_000

    # 工具输出截断
    tool_output_threshold: int = 200
    protect_tail_tool_results: int = 15

    # 摘要生成
    max_summary_tokens: int = 8192
    summary_temperature: float = 0.0

    # 防抖
    compression_cooldown_seconds: int = 60
    max_compressions_per_session: int = 10


class StandaloneCompressor:
    """
    独立压缩组件。

    使用方式：
        compressor = StandaloneCompressor(llm=llm_provider, config=CompressConfig())
        compressed_messages = await compressor.compress(messages, session_id="xxx")
    """

    def __init__(
        self,
        llm: "LLMProvider",
        config: CompressConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or CompressConfig()
        self._compression_count = 0
        self._last_compression_time: float | None = None
        self._logger = logger.bind(name="StandaloneCompressor")

    async def compress(
        self,
        messages: list["Message"],
        session_id: str,
    ) -> list["Message"]:
        """
        执行压缩。

        流程：
        1. 工具输出截断（pre-pass）
        2. 计算压缩边界
        3. 对齐 tool pair 边界
        4. LLM 生成摘要（base 或 incremental）
        5. 组装压缩后消息
        6. 清理 orphaned tool pairs（post-pass）

        Args:
            messages: 原始消息列表
            session_id: 会话 ID（用于日志）

        Returns:
            压缩后的消息列表
        """
        # 防抖检查
        if not self._can_compress():
            return messages

        # Phase 1: 工具输出截断
        pruned_messages, pruned_count = prune_tool_results(
            messages,
            protect_tail_count=self.config.protect_tail_tool_results,
        )
        if pruned_count > 0:
            self._logger.info(
                "pre-compression: pruned {} old tool result(s)",
                pruned_count,
            )

        # Phase 2: 计算压缩边界
        boundary = compute_compress_boundary(
            pruned_messages,
            protect_turns=self.config.protect_turns,
            tail_token_budget=self.config.tail_token_budget,
        )

        if boundary.is_empty:
            self._logger.info("nothing to compress")
            return messages

        # Phase 3: LLM 生成摘要
        if boundary.has_prior_summary:
            summary_text = await self._generate_incremental_summary(boundary, session_id)
        else:
            summary_text = await self._generate_base_summary(boundary, session_id)

        # Phase 4: 组装压缩后消息
        compressed = self._assemble_messages(boundary, summary_text)

        # Phase 5: 清理 orphaned tool pairs
        compressed = self._sanitize(compressed)

        self._compression_count += 1
        self._logger.info(
            "compressed session={} count={} original={} compressed={}",
            session_id,
            self._compression_count,
            boundary.original_count,
            len(compressed),
        )

        return compressed

    def _can_compress(self) -> bool:
        """检查是否可以压缩（防抖）"""
        if self._compression_count >= self.config.max_compressions_per_session:
            return False
        # 时间冷却检查（省略，import time）
        return True

    async def _generate_base_summary(
        self,
        boundary: CompressBoundary,
        session_id: str,
    ) -> str:
        """生成首次压缩摘要"""
        prompt = get_base_compact_prompt()
        return await self._call_llm(prompt, boundary, session_id)

    async def _generate_incremental_summary(
        self,
        boundary: CompressBoundary,
        session_id: str,
    ) -> str:
        """生成增量压缩摘要"""
        prompt = get_incremental_compact_prompt()
        return await self._call_llm(prompt, boundary, session_id)

    async def _call_llm(
        self,
        prompt: str,
        boundary: CompressBoundary,
        session_id: str,
    ) -> str:
        """调用 LLM 生成摘要"""
        from auton.agent.message import Message
        from auton.agent.types import LLMContext

        # 构建输入消息
        all_messages = boundary.build_llm_input()
        compact_request = Message(role="user")
        compact_request.add_text(prompt)
        all_messages.append(compact_request)

        ctx = LLMContext(
            session_id=session_id,
            messages=all_messages,
            tools=[],  # 压缩时禁止工具调用
            system_prompt=COMPACT_SYSTEM_PROMPT,
            model=self.llm.model_name,
            max_tokens=min(self.config.max_summary_tokens, self.llm.max_tokens),
            temperature=self.config.summary_temperature,
        )

        full_text = ""
        async for event in self.llm.stream(ctx):
            if event.type == "text_delta":
                full_text += getattr(event, "delta", "")

        if not full_text.strip():
            raise ValueError("LLM compact 调用未返回有效文本")

        return parse_compact_summary(full_text)

    def _assemble_messages(
        self,
        boundary: CompressBoundary,
        summary_text: str,
    ) -> list["Message"]:
        """组装压缩后的消息列表"""
        from auton.agent.message import Message

        full_summary = f"[历史压缩] {summary_text}"
        summary_msg = Message(role="system")
        summary_msg.add_text(full_summary)

        return (
            list(boundary.stable_prefix)
            + [summary_msg]
            + list(boundary.messages_to_keep)
        )

    def _sanitize(self, messages: list["Message"]) -> list["Message"]:
        """清理 orphaned tool pairs（转 dict 后调用 sanitize_tool_pairs，再转回 Message）"""
        # 简化实现：略过 dict 转换，实际使用时参照 2.5 节 sanitize_tool_pairs
        return messages
```

---

## 三、压缩 Prompt 设计（Standalone）

> 以下 prompt 独立于主 agent 和 subagent 体系，作为独立压缩服务使用。
> 文件位置：`auton/compress/prompts.py`

### 3.1 系统提示词

```python
COMPACT_SYSTEM_PROMPT = (
    "你是专业的技术对话压缩助手。"
    "你的任务是将一段对话压缩为一个结构化的摘要，"
    "保留所有对继续工作至关重要的信息。"
    "只输出纯文本，不要调用任何工具。"
)
```

### 3.2 禁用工具前言（防止 LLM 尝试工具调用）

```python
_NO_TOOLS_PREAMBLE = """\
严重警告：只输出纯文本，不要调用任何工具。
- 不要使用 Read、Bash、Grep、Edit、Write 或任何其他工具
- 对话上下文中已包含你需要的所有信息
- 你的完整输出必须是：一个 <analysis> 块，紧跟一个 <summary> 块

"""

_NO_TOOLS_TRAILER = (
    "\n\n提醒：不要调用任何工具。只输出纯文本 —— "
    "<analysis> 块加 <summary> 块。工具调用会被拒绝。"
)
```

### 3.3 首次压缩 Prompt

```python
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


def get_base_compact_prompt() -> str:
    """
    获取首次压缩提示词。

    用于没有历史摘要的首次压缩场景。
    """
    return (
        _NO_TOOLS_PREAMBLE
        + "你的任务是为当前对话创建详细的结构化摘要，重点关注用户的明确请求和助手的操作过程。"
        "摘要应当充分记录技术细节、代码模式和架构决策，以便在不丢失上下文的情况下继续工作。\n\n"
        + _ANALYSIS_INSTRUCTION
        + "\n\n"
        + _SUMMARY_STRUCTURE
        + "\n\n请根据对话内容，按照上述格式提供精确完整的摘要。"
        + _NO_TOOLS_TRAILER
    )
```

### 3.4 增量压缩 Prompt

```python
def get_incremental_compact_prompt() -> str:
    """
    获取增量压缩提示词。

    用于已有历史摘要的增量压缩场景。
    历史摘要作为 system 消息（[历史压缩] 前缀）已在输入消息中，
    LLM 需要将新增对话与历史摘要合并生成新的综合摘要。
    """
    return (
        _NO_TOOLS_PREAMBLE
        + "你的任务是更新对话摘要。你将看到：\n"
        "1. 之前的历史压缩摘要（以 [历史压缩] 开头的系统消息）\n"
        "2. 之后新增的对话轮次\n\n"
        "请将新增对话的内容整合到已有摘要中，生成一份完整的综合摘要。要求：\n"
        "- 保留历史摘要中所有重要的技术细节\n"
        "- 加入新增对话的关键信息\n"
        "- 更新"当前工作"和"待办事项"等时效性内容（以最新对话为准）\n"
        "- 如新对话与历史摘要有冲突，以新对话内容为准\n\n"
        + _ANALYSIS_INSTRUCTION
        + "\n\n"
        + _SUMMARY_STRUCTURE
        + "\n\n请基于历史摘要和新增对话，生成完整更新后的综合摘要。"
        + _NO_TOOLS_TRAILER
    )
```

### 3.5 输出解析

```python
import re


def parse_compact_summary(raw: str) -> str:
    """
    从 LLM 原始输出中解析摘要。

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
        text = f"对话摘要：\n{content}"

    # 清理多余空白行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

### 3.6 CompactBoundary.build_llm_input()

```python
class CompressBoundary:
    # ...（见 2.3 节）

    def build_llm_input(self) -> list["Message"]:
        """
        为 LLM 调用构建输入消息列表。

        增量压缩时：将 stable_prefix 中的历史摘要消息前置作为上下文，
        再拼接 messages_to_compress，让 LLM 能感知已有摘要并做增量更新。

        首次压缩时：仅返回 messages_to_compress。
        """
        if not self.has_prior_summary:
            return list(self.messages_to_compress)

        # 只取 stable_prefix 中标记为 [历史压缩] 的摘要消息作为上下文
        prior_summaries = [
            msg
            for msg in self.stable_prefix
            if msg.role == "system"
            and msg.get_text().strip().startswith("[历史压缩]")
        ]
        return prior_summaries + list(self.messages_to_compress)
```

---

## 四、会话后摘要系统

### 4.1 系统架构

```
Session 结束
    ↓
SessionSummarizer 读取 jsonl
    ↓
split_blocks() 识别 block 边界
    ↓
对每个 block：
    ├── 事件数 <= 10 → 规则提取摘要（快，无 LLM 调用）
    └── 事件数 > 10 → LLM 生成分段摘要
    ↓
追加到 SUMMARY.md
    ↓
蒸馏为 MEMORY.md 索引
```

### 4.2 Block 识别

```python
BLOCK_MARKERS = (
    "user-message",  # 新的用户消息 → 新 block
    "compact",       # 压缩事件 → 新 block
)


@dataclass
class Block:
    """从 jsonl 中提取的一个逻辑 block"""
    index: int                              # 序号（从 1 开始）
    messages: list[dict]                    # 该 block 的原始事件
    user_intent: str = ""                   # 用户意图
    agent_decisions: list[str] = field(default_factory=list)  # 关键决策
    involved_files: list[str] = field(default_factory=list)    # 涉及文件
    key_conclusions: list[str] = field(default_factory=list)   # 关键结论
    pending_todos: list[str] = field(default_factory=list)     # 待跟进


def split_blocks(events: list[dict]) -> list[Block]:
    """
    将事件流拆分为逻辑 block。

    规则：
      - 每个 user-message 开始一个新 block
      - 每个 compact 事件开始一个新 block
      - 一个 block 内包含：触发事件 + 后续所有 assistant/tool 事件
    """
    blocks: list[Block] = []
    current: list[dict] = []
    block_index = 0

    for event in events:
        ev_type = event.get("type", "")

        if ev_type in BLOCK_MARKERS:
            if current:
                block_index += 1
                blocks.append(_build_block(block_index, current))
                current = []

        current.append(event)

    # 最后一块
    if current:
        block_index += 1
        blocks.append(_build_block(block_index, current))

    return blocks


def _build_block(index: int, events: list[dict]) -> Block:
    """从事件列表构建 Block"""
    block = Block(index=index, messages=events)

    for msg in events:
        ev_type = msg.get("type", "")
        content = msg.get("content", "")

        if ev_type == "user-message" and not block.user_intent:
            block.user_intent = _extract_intent(content)

        elif ev_type == "assistant":
            text = _extract_text_from_assistant(msg)
            if text:
                block.agent_decisions.extend(_extract_decisions(text)[:3])
                block.key_conclusions.extend(_extract_conclusions(text)[:3])

        elif ev_type in ("tool-call", "tool_use"):
            tool = msg.get("tool", msg.get("name", ""))
            tool_input = msg.get("tool_input", {})
            if isinstance(tool_input, dict):
                path = tool_input.get("path", tool_input.get("file", ""))
                if path and isinstance(path, str):
                    block.involved_files.append(path)

    return block


def _extract_intent(text: str) -> str:
    """从用户消息中提取意图（简短摘要）"""
    text = text.strip()
    if len(text) > 100:
        return text[:100] + "…"
    return text


def _extract_text_from_assistant(msg: dict) -> str:
    """从 assistant 消息提取文本内容（跳过思考块）"""
    if isinstance(msg.get("content"), str):
        return msg["content"]
    parts = msg.get("parts", [])
    text_parts = []
    for part in parts:
        if isinstance(part, dict) and part.get("type") == "text":
            text_parts.append(part.get("content", ""))
        elif isinstance(part, dict) and part.get("type") == "reasoning":
            pass  # 跳过思考过程
    return " ".join(text_parts)


def _extract_decisions(text: str) -> list[str]:
    """从文本中提取决策性语句（正则匹配）"""
    decisions = []
    patterns = [
        r"决定\s*[：:]\s*([^\n。]+)",
        r"采用\s*([^\n。]+)\s*方案",
        r"选择\s*([^\n。]+)\s*方案",
        r"修改为\s*([^\n。]+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            decisions.append(m.group(1).strip())
    return decisions


def _extract_conclusions(text: str) -> list[str]:
    """从文本中提取结论性语句（正则匹配）"""
    conclusions = []
    patterns = [
        r"因此\s*([^\n。]+)",
        r"最终\s*([^\n。]+)",
        r"总结\s*[：:]\s*([^\n。]+)",
        r"得到\s*([^\n。]+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            conclusions.append(m.group(1).strip())
    return conclusions
```

---

## 五、会话摘要 Prompt 设计（Standalone）

> 文件位置：`auton/memory/summary_prompts.py`

### 5.1 系统提示词

```python
SUMMARY_SYSTEM_PROMPT = (
    "你是专业的技术对话摘要助手，擅长从技术对话中提取最关键的非显而易见的信息。"
    "只输出纯文本，不要调用任何工具。"
    "摘要用于后续语义检索，应简洁精准——每条要点只写结论和理由，不写可从代码库直接查到的内容。"
    "每条要点末尾附引用标签 [↑msg:xxxxxxxx]（message_id 前 8 位）。"
)
```

### 5.2 分段摘要 Prompt

```python
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
    """
    构建会话摘要 prompt。

    Args:
        session_id: 会话 ID
        start_idx: 起始事件索引
        end_idx: 结束事件索引
        conversation_text: 对话文本（由 build_conversation_text 生成）

    Returns:
        格式化后的 prompt
    """
    return SESSION_SUMMARY_PROMPT_TEMPLATE.format(
        session_id=session_id,
        start_idx=start_idx,
        end_idx=end_idx,
        count=end_idx - start_idx + 1,
        conversation_text=conversation_text,
    )
```

### 5.3 对话文本构建

```python
def build_conversation_text(events: list[dict]) -> str:
    """
    从事件列表提取可读对话文本，用于 LLM 摘要输入。

    只使用原始对话内容：用户消息、助手文本回复。
    排除 compact 压缩内容——摘要应基于真实对话元内容，不引入二次压缩的噪声。
    每条消息标注 message_id 前缀（前 8 位），供 LLM 生成引用标签时对应。
    截断：过长的助手回复（保留前 600 字符），避免 prompt 超长。
    """
    parts = []
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
            raw_parts = ev.get("parts", [])
            for block in raw_parts:
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
```

### 5.4 MEMORY.md 索引生成

每条 SUMMARY.md 段落对应一个 MEMORY.md 索引条目：

```python
def format_memory_entry(
    session_id: str,
    short_id: str,
    intent: str,
) -> str:
    """
    生成 MEMORY.md 索引条目。

    格式：- [SessionID] — 1句话描述（用户意图）

    Args:
        session_id: 完整 session ID
        short_id: 短 ID（前 8 位）
        intent: 用户意图

    Returns:
        索引条目字符串
    """
    return f"- [{short_id}] — {intent}"


def update_memory_index(
    memory_path: Path,
    session_id: str,
    intent: str,
) -> None:
    """
    追加索引条目到 MEMORY.md。

    如果 session 已存在索引条目，则更新；否则追加。

    Args:
        memory_path: MEMORY.md 路径
        session_id: 完整 session ID
        intent: 用户意图摘要
    """
    short_id = session_id[:8] if len(session_id) >= 8 else session_id
    entry = format_memory_entry(session_id, short_id, intent)

    if memory_path.exists():
        text = memory_path.read_text(encoding="utf-8")
        # 检查是否已有该 session 的条目
        pattern = re.compile(rf"- \[{re.escape(short_id)}\] — .+")
        if pattern.search(text):
            text = pattern.sub(entry, text)
        else:
            text += f"\n{entry}"
    else:
        text = f"# 记忆索引\n\n{entry}\n"

    memory_path.write_text(text, encoding="utf-8")
```

---

## 六、配置参数

### 6.1 CompressConfig

```python
@dataclass
class CompressConfig:
    """实时会话压缩配置"""

    # 触发阈值（双阈值，任一满足即触发）
    token_threshold: int = 150_000       # 绝对 token 数
    threshold_percent: float = 0.60      # 上下文窗口比例

    # 尾部保护
    protect_turns: int = 2               # 保留最近几轮用户对话
    tail_token_budget: int = 40_000      # 尾部 token 上限

    # 工具输出截断
    tool_output_threshold: int = 200     # 超过此字符数截断为占位符
    protect_tail_tool_results: int = 15   # 尾部保留的工具结果数量

    # 摘要生成
    max_summary_tokens: int = 8192        # 摘要最大 token 数
    summary_temperature: float = 0.0     # 摘要生成温度

    # 防抖
    compression_cooldown_seconds: int = 60  # 压缩后冷却时间
    max_compressions_per_session: int = 10  # 单会话最大压缩次数
```

### 6.2 SummaryConfig

```python
@dataclass
class SummaryConfig:
    """会话后摘要配置"""

    # Block 触发
    block_size_threshold: int = 10        # 超过此数量事件则用 LLM 摘要

    # 摘要生成
    max_conversation_tokens: int = 32_000  # 单次 LLM 摘要的最大对话 token
    summary_max_tokens: int = 4096         # 摘要输出最大 token

    # 输出路径
    summary_md_path: str = "SUMMARY.md"   # 分段摘要路径
    memory_md_path: str = "MEMORY.md"    # 索引路径
```

---

## 七、文件结构

```
auton/
├── compress/                              # 新增：独立压缩组件
│   ├── __init__.py
│   ├── config.py                         # CompressConfig 数据类
│   ├── boundary.py                       # 压缩边界计算（compute_compress_boundary）
│   ├── pruner.py                         # 工具输出截断（prune_tool_results）
│   ├── prompts.py                        # BASE_COMPACT / INCREMENTAL 提示词
│   ├── parser.py                         # 摘要输出解析（parse_compact_summary）
│   ├── sanitizer.py                       # Tool pair 清理（sanitize_tool_pairs）
│   └── compressor.py                      # 压缩主流程（StandaloneCompressor）
│
├── memory/
│   ├── session_summarizer.py             # [修改] Block 识别 + 规则提取（保留）
│   ├── summary_generator.py              # [修改] LLM 摘要生成（使用新 prompt）
│   ├── summary_prompts.py                # [新增] SESSION_SUMMARY 提示词
│   ├── memory_indexer.py                  # [新增] MEMORY.md 索引生成
│   └── config.py                         # [新增] SummaryConfig
```

### 7.1 导出接口（compress/__init__.py）

```python
"""Auton 独立压缩组件"""

from .config import CompressConfig
from .boundary import compute_compress_boundary, CompressBoundary
from .pruner import prune_tool_results, TOOL_OUTPUT_PLACEHOLDER
from .prompts import (
    COMPACT_SYSTEM_PROMPT,
    get_base_compact_prompt,
    get_incremental_compact_prompt,
    parse_compact_summary,
)
from .sanitizer import sanitize_tool_pairs
from .compressor import StandaloneCompressor

__all__ = [
    "CompressConfig",
    "CompressBoundary",
    "compute_compress_boundary",
    "prune_tool_results",
    "TOOL_OUTPUT_PLACEHOLDER",
    "COMPACT_SYSTEM_PROMPT",
    "get_base_compact_prompt",
    "get_incremental_compact_prompt",
    "parse_compact_summary",
    "sanitize_tool_pairs",
    "StandaloneCompressor",
]
```

---

## 八、迁移指南

### 8.1 废弃 / 重构

| 文件 | 处理方式 |
|---|---|
| `auton/agent/compact_prompts.py` | 内容迁移到 `auton/compress/prompts.py`，删除原文件 |
| `auton/agent/session.py` | 保留消息存储逻辑，压缩逻辑改用 `StandaloneCompressor` |
| `auton/memory/session_summarizer.py` | 保留 Block 识别，提取逻辑不变 |
| `auton/memory/summary_generator.py` | prompt 迁移到 `auton/memory/summary_prompts.py` |

### 8.2 兼容性接口

- `Session.add_user_message()` / `Session.add_assistant_message()` 接口不变
- `SessionStore.read_session()` / `SessionStore.write_session()` 接口不变
- `/compact` 命令行为不变，仅内部实现替换

### 8.3 Session.compact() 替换方案

```python
# 旧代码（auton/agent/session.py）
def compact(self, ...):
    preparation = self.prepare_compact(...)
    if preparation.is_empty:
        return CompactResult()
    summary_text = self._simple_truncate_summary(preparation)
    return self.apply_compact(summary_text, preparation)

# 新代码（auton/agent/session.py）
async def compact_async(self, llm: LLMProvider, ...):
    preparation = self.prepare_compact(...)
    if preparation.is_empty:
        return CompactResult()

    compressor = StandaloneCompressor(llm, config=self._get_compress_config())
    compressed_messages = await compressor.compress(self.messages, self.meta.session_id)
    # 应用压缩结果到 session
    ...
```

---

## 九、测试计划

### 9.1 单元测试

| 测试文件 | 测试场景 |
|---|---|
| `tests/unit/compress/test_boundary.py` | 压缩边界计算、tool pair 对齐、尾部 token 保护 |
| `tests/unit/compress/test_pruner.py` | 大输出截断（> 200 字符）、小输出保留、尾部保护 |
| `tests/unit/compress/test_sanitizer.py` | orphaned tool_result 删除、stub tool_result 插入 |
| `tests/unit/compress/test_parser.py` | `<analysis>` 去除、`<summary>` 提取、降级处理 |
| `tests/unit/compress/test_prompts.py` | base/incremental prompt 格式正确、占位符完整 |
| `tests/unit/memory/test_block_split.py` | block 边界识别（user-message、compact 事件） |
| `tests/unit/memory/test_summary_prompts.py` | 分段摘要 prompt 格式正确 |

### 9.2 集成测试

| 测试文件 | 测试场景 |
|---|---|
| `tests/integration/test_compress_full_flow.py` | 完整压缩流程：截断 → 边界 → LLM 摘要 → 组装 → 清理 |
| `tests/integration/test_double_threshold.py` | 绝对阈值和比例阈值分别触发 |
| `tests/integration/test_incremental_compress.py` | 二次压缩时历史摘要不被重复压缩 |
| `tests/integration/test_session_summary_flow.py` | session 结束后正确生成 SUMMARY.md 和 MEMORY.md |

### 9.3 关键测试用例（详细说明）

#### 9.3.1 test_boundary_protects_tool_pair

```python
def test_boundary_protects_tool_pair():
    """
    验证 compress_end 不会切断 tool_call + tool_result pair。

    场景：
        [user] 请查一下天气
        [assistant] 我来调用工具 → [tool_calls: weather]
        [tool] 天气：晴天 24 度
        [assistant] 今天晴天，24 度。

    期望：
        compress_end 不会落在 [tool] 和 [assistant] 之间，
        而是回拉到 [assistant] 之前，确保整个 pair 都被压缩或都被保留。
    """
    messages = _build_messages_with_tool_pair()
    boundary = compute_compress_boundary(messages, protect_turns=1)

    # compress_end 应该在 tool_result 之后
    # 即：整个 tool_call + tool_result + 后续 assistant 是一起被压缩或被保留的
    pass
```

#### 9.3.2 test_pruner_truncates_long_tool_output

```python
def test_pruner_truncates_long_tool_output():
    """
    验证超过 200 字符的工具输出被替换为占位符。
    """
    messages = _build_messages_with_tool_outputs({
        "long": "x" * 500,   # 应该被截断
        "short": "done",     # 应该保留
    })
    pruned, count = prune_tool_results(messages, protect_tail_count=0)

    assert count == 1  # 只有 1 个被截断
    assert "done" in pruned[1].get_text()  # 短输出保留
    assert TOOL_OUTPUT_PLACEHOLDER in pruned[0].get_text()  # 长输出被替换
```

#### 9.3.3 test_double_threshold_trigger

```python
async def test_double_threshold_trigger():
    """
    验证双阈值触发：绝对阈值和比例阈值满足任意一个即触发。
    """
    # 场景 1：绝对阈值先到
    session = _build_session(token_count=150_000, context_length=100_000)
    assert should_compress(150_000, 100_000) is True  # 绝对阈值

    # 场景 2：比例阈值先到（短上下文模型）
    session = _build_session(token_count=60_000, context_length=100_000)
    assert should_compress(60_000, 100_000) is True  # 60% * 100000 = 60000
```

---

## 十、优先级与实施顺序

| 优先级 | 任务 | 预计工作量 |
|---|---|---|
| P0 | 创建 `auton/compress/` 目录结构（__init__.py, config.py） | 1h |
| P0 | 实现 `auton/compress/boundary.py`（压缩边界计算） | 2h |
| P0 | 实现 `auton/compress/prompts.py`（prompt 独立化） | 1h |
| P0 | 实现 `auton/compress/parser.py`（输出解析） | 1h |
| P0 | 实现 `auton/compress/pruner.py`（工具输出截断） | 1h |
| P0 | 实现 `auton/compress/sanitizer.py`（tool pair 清理） | 2h |
| P0 | 实现 `auton/compress/compressor.py`（压缩主流程） | 3h |
| P0 | 实现 `should_compress()` 双阈值逻辑 | 1h |
| P1 | 创建 `auton/memory/summary_prompts.py`（摘要 prompt 独立化） | 1h |
| P1 | 实现 `auton/memory/memory_indexer.py`（MEMORY.md 索引） | 2h |
| P1 | 修改 `auton/agent/session.py` 使用新组件 | 2h |
| P2 | 单元测试覆盖（目标 80%+） | 4h |
| P2 | 集成测试 | 4h |
| P3 | 删除废弃文件，清理导入 | 1h |
