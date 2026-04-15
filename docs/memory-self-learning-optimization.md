# 摘要自学习优化方案

## 1. 背景与目标

### 1.1 当前问题

Agent 驱动的检索链路：

```
query 进入
  → agent 读取 MEMORY.md（每个summary.md的路径和主要内容需要在memory.md中用一句话说明。）
    → MEMORY 能回答？ → 直接回答
    → MEMORY 不够，需要更多细节？ → agent 读取 summary.md
      → summary 能回答？ → 回答
      → summary 不够？ → agent 降级读取 session.jsonl 原始消息 → 降级回答
```

当前 `summary.md` 质量不足，导致 agent 频繁降级到 jsonl。目标：**agent 在 98% 的情况下能从 summary.md 获得足够信息，无需读取 jsonl，或者能够从summary.md中清晰知道该读取session.jsonl文件的哪些msg_id**。

### 1.2 SUMMARY.md 的结构规范

SUMMARY.md 是**条目式**的，每条对应 jsonl 中的一段连续对话。每条有两个层级的 msg_id 标注。

**正确格式示例**：

```markdown
## 用户认证模块重构

- [msg_id: a1b2c3d4~c3d4e5f6] 重构了 user_service.py 的认证逻辑（msg_id-a1b2c3d4, msg_id-b2c3d4e5），将 Session 验证从同步改为异步（msg_id-c3d4e5f6）
- [msg_id: d4e5f6g7~e5f6g7h8] 修复了 token 刷新时序问题（msg_id-d4e5f6g7），原因为 refresh_token 和 access_token 同时过期未做缓冲（msg_id-e5f6g7h8）
- [msg_id: g7h8i9j0~i9j0k1l2] 采用 Redis Session 方案（msg_id-g7h8i9j0），TTL=300s（msg_id-h8i9j0k1），key 格式 user:session:{user_id}（msg_id-i9j0k1l2）
- [msg_id: l2m3n4o5~o5p6q7r8] 认证流程测试通过（msg_id-l2m3n4o5, msg_id-m3n4o5p6），但并发压测 QPS 下降 15%（msg_id-n4o5p6q7），待优化（msg_id-o5p6q7r8）

## Redis 连接池问题排查

- [msg_id: r8s9t0u1~t0u1v2w3] 问题：生产环境 Redis 连接超时（msg_id-r8s9t0u1），错误码 CLUSTER_DOWN（msg_id-s9t0u1v2），错误信息：max concurrent connections exceeded（msg_id-t0u1v2w3）
- [msg_id: u1v2w3x4~v2w3x4y5] 根因：max_clients=100 配置过小（msg_id-u1v2w3x4），实际峰值 320 并发连接（msg_id-v2w3x4y5）
- [msg_id: w3x4y5z6~z6a7b8c9] 解决方案：调大 max_clients 至 500（msg_id-w3x4y5z6, msg_id-x4y5z6a7），添加连接池熔断机制（msg_id-y5z6a7b8, msg_id-z6a7b8c9）
- [msg_id: a7b8c9d0~b8c9d0e1] 待验证：压测确认 500 是否足够（msg_id-a7b8c9d0），计划压到 1000 观察（msg_id-b8c9d0e1）
```

**格式规则**：

每条摘要的格式：`[msg_id: <外层范围>] <内容>`

内容中的两层 msg_id：
- **外层 `[msg_id: a1b2c3d4~c3d4e5f6]`**：标记这条摘要对应 session.jsonl 中的哪一段连续对话块
- **内层 `(msg_id-a1b2c3d4, msg_id-b2c3d4e5)`**：标记这段内容的每个子论点具体引用了哪条消息

压缩时，LLM 需要：
1. 将 jsonl 按交互块分组（每块通常 5-20 条 msg）可根据主题，长度，对话轮数确定；
2. 为每个块生成一条条目，外层标注块范围 `[msg_id: <start_uuid>~<end_uuid>]`
3. 内容中每个子论点用括号标注其引用的单条 msg_id，格式为 `(msg_id-<uuid>)` 或 `(msg_id-<uuid>, msg_id-<uuid>)`

**错误格式（不允许）**：

```markdown
- [msg_id: a1b2c3d4~c3d4e5f6] 重构了 user_service.py 的认证逻辑  ← 缺少内层 (msg_id) 引用
- [msg_id: a1b2c3d4~c3d4e5f6] 重构了（msg_id-a1b2c3d4），user_service（msg_id-b2c3d4e5），认证逻辑（msg_id-c3d4e5f6）  ← 引用太碎，内层引用应按论点粒度而非分词
```

### 1.3 session.jsonl 每条消息的格式

```python
# session.jsonl 中每条消息的格式
{
    "msg_id": "a1b2c3d4",
    "role": "user",          # "user" 或 "assistant"
    "content": "...",
    "timestamp": 1234567890,
}
```

### 1.4 优化目标

通过分析**哪些 query 命中了 summary**、**哪些 query 落到 jsonl**，反向驱动总结质量提升：

1. **提高召回率**：让 summary 包含 query 侧实际需要的知识点
2. **优化表达**：让 summary 使用 query 侧检索时的关键词和表达方式
3. **精准 msg_id**：每个要点都标注来源 msg_id，支持快速回溯

---

## 2. 核心组件

### 2.1 RetrievalAnalytics（检索分析）

记录每次检索的命中情况。

```python
@dataclass
class RetrievalRecord:
    query_id: str
    query_text: str                    # query 原文
    hit_source: str                    # "memory" | "summary" | "jsonl" | "none"
    hit_msg_ids: list[str] | None      # 命中的 msg_id 列表
    hit_content: str | None            # 命中的具体内容片段
    session_id: str
    timestamp: float


class RetrievalAnalytics:
    """记录每次检索的命中情况"""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.records: list[RetrievalRecord] = []

    def record(
        self,
        query_text: str,
        hit_source: str,
        hit_msg_ids: list[str] | None = None,
        hit_content: str | None = None,
        session_id: str = "",
    ):
        record = RetrievalRecord(
            query_id=str(uuid.uuid4())[:8],
            query_text=query_text,
            hit_source=hit_source,
            hit_msg_ids=hit_msg_ids,
            hit_content=hit_content,
            session_id=session_id,
            timestamp=time.time(),
        )
        self.records.append(record)
        self._persist()

    def get_summary_hit_rate(self, session_id: str) -> float:
        """从 summary 回答的命中率（不含从 memory 回答的情况）"""
        session_records = [r for r in self.records if r.session_id == session_id]
        if not session_records:
            return 0.0
        summary_hits = sum(1 for r in session_records if r.hit_source == "summary")
        return summary_hits / len(session_records)

    def get_no_jsonl_hit_rate(self, session_id: str) -> float:
        """不降级到 jsonl 的命中率（MEMORY + SUMMARY），即 98% 目标指标"""
        session_records = [r for r in self.records if r.session_id == session_id]
        if not session_records:
            return 0.0
        no_jsonl = sum(1 for r in session_records if r.hit_source in ("memory", "summary"))
        return no_jsonl / len(session_records)

    def get_failed_queries(self, session_id: str) -> list[RetrievalRecord]:
        """获取真正降级到 jsonl 的 query（不包含从 memory 直接回答的成功记录）"""
        return [
            r for r in self.records
            if r.session_id == session_id and r.hit_source == "jsonl"
        ]

    def get_msg_id_stats(self) -> dict[str, dict]:
        """
        统计各 msg_id 的命中情况。
        返回 {msg_id: {hit: n, miss: n}}
        """
        msg_stats: dict[str, dict] = {}
        for r in self.records:
            if r.hit_msg_ids:
                for msg_id in r.hit_msg_ids:
                    if msg_id not in msg_stats:
                        msg_stats[msg_id] = {"hit": 0, "miss": 0}
                    if r.hit_source == "summary":
                        msg_stats[msg_id]["hit"] += 1
                    else:
                        msg_stats[msg_id]["miss"] += 1
        return msg_stats

    def get_keyword_frequency(self, session_id: str) -> list[tuple[str, int]]:
        """提取降级到 jsonl 的 query 中的高频关键词（这些词是 summary 覆盖不足的信号）"""
        words: Counter = Counter()
        for r in self.records:
            if r.session_id == session_id and r.hit_source == "jsonl":
                tokens = re.findall(r'\w{3,}', r.query_text.lower())
                stop_words = {"the", "and", "for", "with", "this", "that", "what", "how", "why"}
                filtered = [w for w in tokens if w not in stop_words]
                words.update(filtered)
        return words.most_common(30)

    def _persist(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "query_id": r.query_id,
                "query_text": r.query_text,
                "hit_source": r.hit_source,
                "hit_msg_ids": r.hit_msg_ids,
                "hit_content": r.hit_content,
                "session_id": r.session_id,
                "timestamp": r.timestamp,
            }
            for r in self.records
        ]
        self.storage_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
```

### 2.2 SummaryQualityAnalyzer（总结质量分析器）

分析哪些 query 无法从 summary 回答，诊断失败原因。

```python
class SummaryQualityAnalyzer:
    def __init__(self, analytics: RetrievalAnalytics):
        self.analytics = analytics

    def analyze(self, session_id: str) -> QualityReport:
        failed = self.analytics.get_failed_queries(session_id)
        summary_hit_rate = self.analytics.get_summary_hit_rate(session_id)
        no_jsonl_hit_rate = self.analytics.get_no_jsonl_hit_rate(session_id)
        msg_stats = self.analytics.get_msg_id_stats()
        keywords = self.analytics.get_keyword_frequency(session_id)

        # 按 msg_id 聚合失败 query：哪些 msg_id 对应的要点被频繁 miss
        failed_by_msg: dict[str, list[str]] = {}
        for record in failed:
            if record.hit_msg_ids:
                for msg_id in record.hit_msg_ids:
                    if msg_id not in failed_by_msg:
                        failed_by_msg[msg_id] = []
                    failed_by_msg[msg_id].append(record.query_text)

        # 找出高频 miss 的 msg_id（这些 msg_id 对应的要点需要加强）
        high_miss_msg_ids = sorted(
            failed_by_msg.keys(),
            key=lambda m: len(failed_by_msg[m]),
            reverse=True
        )[:10]

        return QualityReport(
            session_id=session_id,
            summary_hit_rate=summary_hit_rate,
            no_jsonl_hit_rate=no_jsonl_hit_rate,
            total_queries=len([r for r in self.analytics.records if r.session_id == session_id]),
            failed_count=len(failed),
            failed_by_msg=failed_by_msg,
            high_miss_msg_ids=high_miss_msg_ids,
            high_freq_keywords=[k for k, _ in keywords[:15]],
            msg_stats=msg_stats,
        )
```

```python
@dataclass
class QualityReport:
    session_id: str
    summary_hit_rate: float          # 从 summary 回答的命中率
    no_jsonl_hit_rate: float         # 不降级到 jsonl 的命中率（98% 目标）
    total_queries: int
    failed_count: int
    failed_by_msg: dict[str, list[str]]   # {msg_id: [未命中的 query 列表]}
    high_miss_msg_ids: list[str]          # 高频 miss 的 msg_id
    high_freq_keywords: list[str]
    msg_stats: dict[str, dict]
```

### 2.3 CompressionImprover（压缩改进器）

根据质量报告生成压缩改进提示。

冷启动逻辑：当历史 query 数量不足 `min_queries_for_analysis` 时，使用静态 prompt，不注入分析报告。

```python
class CompressionImprover:
    def __init__(
        self,
        analytics: RetrievalAnalytics,
        analyzer: SummaryQualityAnalyzer,
        min_queries_for_analysis: int = 10,
    ):
        self.analytics = analytics
        self.analyzer = analyzer
        self.min_queries_for_analysis = min_queries_for_analysis

    def generate_improvement_prompt(
        self,
        session_id: str,
        session_jsonl: list[dict],
        current_summary: str,
    ) -> str:
        # 冷启动：历史数据不足时使用静态 prompt，不注入分析报告
        total_queries = len([
            r for r in self.analytics.records
            if r.session_id == session_id
        ])
        if total_queries < self.min_queries_for_analysis:
            return self._generate_static_prompt(session_jsonl, current_summary)

        report = self.analyzer.analyze(session_id)

        return f"""你是一个会话总结助手。请将对话内容浓缩为结构化摘要。

## 质量目标

本次总结需要达到 **98% 检索命中率**——后续 query 应尽可能从本摘要回答，无需再读取原始 jsonl。

## 重要格式要求

每条摘要是条目式的，**每个要点都必须标注来源 msg_id**：

```markdown
## <主题>

- [msg_id: a1b2c3d4~c3d4e5f6] 子论点1（msg_id-a1b2c3d4），子论点2（msg_id-b2c3d4e5, msg_id-c3d4e5f6）
- [msg_id: d4e5f6g7~e5f6g7h8] 子论点3（msg_id-d4e5f6g7），子论点4（msg_id-e5f6g7h8）
- [msg_id: g7h8i9j0] 子论点5（msg_id-g7h8i9j0）

## <另一个主题>

- [msg_id: r8s9t0u1~t0u1v2w3] 子论点6（msg_id-r8s9t0u1, msg_id-s9t0u1v2），子论点7（msg_id-t0u1v2w3）
- [msg_id: u1v2w3x4~v2w3x4y5] 子论点8（msg_id-u1v2w3x4），子论点9（msg_id-v2w3x4y5）
```

**每个 `-` 开头的要点**：外层 `[msg_id: ...]` 标记对话块，内层 `(msg_id-XXX)` 标记每个子论点引用的消息。

## 本 session 检索分析结果

### 命中率
- 不降级到 jsonl 的命中率：{report.no_jsonl_hit_rate:.0%}（{no_jsonl_hits}/{total} 的 query 无需读 jsonl）
- 其中从 summary 回答的命中率：{report.summary_hit_rate:.0%}
- 总查询数：{report.total_queries}，失败数：{report.failed_count}

### 高频未命中的 msg_id（这些 msg_id 对应的要点需要重点写）

{self._format_high_miss_msg_ids(report)}

### 高频 query 关键词
以下关键词在真实 query 中出现频繁，总结时应优先覆盖：
{keyword_hint_text(report.high_freq_keywords)}

## 总结原则

1. **两层 msg_id**：外层 `[msg_id: <start_uuid>~<end_uuid>]` 标记对话块，内层 `(msg_id-<uuid>)` 标记每个子论点引用的消息
2. **具体优先于抽象**：保留文件名、函数名、变量名、具体数值、配置值、错误信息
3. **覆盖关键词**：上述高频关键词对应的知识点必须写入 summary
4. **决策理由要写**：不仅写结论，写为什么这么做
5. **当前状态要精确**：代码停在哪个文件、哪一行、什么状态
6. **忽略机械调用**：纯工具调用细节（无结果的 Read/Glob/Bash）不需要记录

## 输出格式

```markdown
## <主题>

- [msg_id: <start_uuid>~<end_uuid>] 子论点1（msg_id-A），子论点2（msg_id-B, msg_id-C）
- [msg_id: <start_uuid>~<end_uuid>] 子论点3（msg_id-D）

## <另一个主题>

- [msg_id: <start_uuid>~<end_uuid>] 子论点4（msg_id-E），子论点5（msg_id-F）
```

## 待总结的原始对话（session.jsonl）

{self._format_jsonl(session_jsonl)}

---

## 当前 summary（如有，用于增量更新）

{current_summary}
""""

    def _generate_static_prompt(
        self,
        session_jsonl: list[dict],
        current_summary: str,
    ) -> str:
        """冷启动阶段使用的静态 prompt（无检索数据时）。

        不注入分析报告，仅要求 LLM 按格式规范生成带 msg_id 标注的摘要。
        """
        return f"""你是一个会话总结助手。请将对话内容浓缩为结构化摘要。

## 格式要求

每条要点必须标注来源 msg_id：

```markdown
## <主题>

- [msg_id: <start_id>~<end_id>] 子论点1（msg_id-A），子论点2（msg_id-B, msg_id-C）
```

**两层 msg_id 说明**：
- 外层 `[msg_id: start~end]`：标记这条要点对应的对话块范围
- 内层 `(msg_id-XXX)`：每个子论点精确引用的单条消息

## 总结原则

1. **具体优先于抽象**：保留文件名、函数名、变量名、具体数值、错误信息
2. **决策理由要写**：不仅写结论，写为什么这么做
3. **当前状态要精确**：代码停在哪个文件、哪一行、什么状态
4. **忽略机械调用**：纯工具调用细节不需要记录

## 待总结的原始对话（session.jsonl）

{self._format_jsonl(session_jsonl)}

---

## 当前 summary（如有，用于增量更新）

{current_summary}
"""

    def _format_high_miss_msg_ids(self, report: QualityReport) -> str:
        if not report.high_miss_msg_ids:
            return "无失败记录。"
        lines = []
        for msg_id in report.high_miss_msg_ids:
            queries = report.failed_by_msg.get(msg_id, [])
            lines.append(f"- **{msg_id}**（{len(queries)} 条未命中）")
            for q in queries[:3]:
                lines.append(f"  - \"{q}\"")
        return "\n".join(lines)

    def _format_jsonl(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            lines.append(f"[{msg['msg_id']}] {msg['role']}: {msg['content'][:300]}")
        return "\n".join(lines)


def keyword_hint_text(keywords: list[str]) -> str:
    if not keywords:
        return "（无数据）"
    return ", ".join(f"**{k}**" for k in keywords)
```

---

## 3. 数据流与触发时机

### 3.1 Agent 驱动的检索流程

检索是 **agent 主动决策** 的，不是自动检索链路：

```
query 进入
  → agent 读取 MEMORY.md（包含 summary.md 的说明和路径）
    → agent 判断是否需要读取 summary.md
      → 判断依据：MEMORY.md 中 summary.md 的内容是否能回答当前 query
      → 需要？→ agent 读取 summary.md → 回答
      → 不需要？→ 直接从 MEMORY 回答
```

**关键区别**：agent 自主决定是否读 summary.md，因此 analytics 的记录点是 agent **实际读取** summary.md 的时刻，而不是自动检索的时刻。

### 3.2 Hook 拦截实现

analytics 记录必须在工具调用层拦截，而**不能依赖 LLM 自行汇报**（LLM 不会主动告诉框架它读了哪个文件）。

拦截点：在 `Read` 工具（或等价的文件读取工具）执行后，根据读取的文件路径自动分类记录。

```python
class MemoryReadHook:
    """
    在 Read 工具调用完成后自动触发，根据读取的文件路径分类记录到 analytics。

    接入方式：在 tool_executor 的 post-execution hook 中注册此类。
    """

    def __init__(self, analytics: RetrievalAnalytics):
        self.analytics = analytics
        self._current_query: str = ""

    def set_current_query(self, query: str) -> None:
        """每轮对话开始时，由 processor 调用，记录当前 query 文本。"""
        self._current_query = query

    def on_tool_result(
        self,
        tool_name: str,
        tool_input: dict,
        result: str,
        session_id: str,
    ) -> None:
        """Read 工具执行后调用，根据文件路径分类记录。"""
        if tool_name not in ("Read", "read_file"):
            return
        path = tool_input.get("path", "")
        if not path:
            return

        if "SUMMARY.md" in path or "summary.md" in path:
            # agent 读取了 summary 文件
            referenced_ids = _extract_msg_ids_from_text(result)
            self.analytics.record(
                query_text=self._current_query,
                hit_source="summary",
                hit_msg_ids=referenced_ids or None,
                hit_content=result[:500],
                session_id=session_id,
            )
        elif "MEMORY.md" in path or "memory.md" in path:
            # agent 读取了 memory 索引即可回答（后续若不再读 summary/jsonl 则算 memory 命中）
            # 此处仅做标记，最终命中分类由 on_turn_end 决定
            pass
        elif path.endswith(".jsonl"):
            # agent 降级读取了原始 session 文件
            referenced_ids = _extract_msg_ids_from_path(path, result)
            self.analytics.record(
                query_text=self._current_query,
                hit_source="jsonl",
                hit_msg_ids=referenced_ids or None,
                hit_content=result[:500],
                session_id=session_id,
            )


def _extract_msg_ids_from_text(text: str) -> list[str]:
    """从工具返回内容中提取所有 msg_id 引用"""
    return re.findall(r"msg_id[-:]([a-zA-Z0-9\-]+)", text, re.IGNORECASE)


def _extract_msg_ids_from_path(path: str, content: str) -> list[str]:
    """从 jsonl 内容中提取 msg_id 字段"""
    ids = []
    for line in content.splitlines():
        try:
            obj = json.loads(line)
            if "msg_id" in obj:
                ids.append(obj["msg_id"])
        except (json.JSONDecodeError, TypeError):
            continue
    return ids
```

### 3.3 记录时机

当 agent 决定读取 summary.md 时，通过上述 `MemoryReadHook` 自动触发记录（框架层完成，无需 LLM 汇报）：

```python
# agent 读取 summary.md 后，注入日志记录逻辑
def on_agent_read_summary(
    session_id: str,
    query: str,
    summary_content: str,      # agent 实际看到的 summary 内容
    referenced_msg_ids: list[str],  # agent 在回复中引用的 msg_id
):
    """
    agent 读取 summary.md 后调用此函数记录日志。

    referenced_msg_ids：从 summary.md 中提取的，agent 回复中实际引用的 msg_id
    如果 agent 读取了 summary.md 但回复中未引用任何 msg_id，
    说明 summary.md 中的信息不够具体或匹配度不足
    """
    analytics.record(
        query_text=query,
        hit_source="summary",
        hit_msg_ids=referenced_msg_ids,
        hit_content=summary_content[:500],  # 记录 agent 读取的摘要片段
        session_id=session_id,
    )
```

当 agent 跳过 summary.md 直接回答时，记录为内存命中：

```python
def on_agent_answer_from_memory(
    session_id: str,
    query: str,
    memory_content: str,
):
    """agent 从 MEMORY 直接回答，无需读取 summary"""
    analytics.record(
        query_text=query,
        hit_source="memory",   # 从 MEMORY 回答，未读 summary
        hit_msg_ids=None,
        hit_content=memory_content[:500],
        session_id=session_id,
    )
```

当 agent 需要进一步读取 jsonl 时：

```python
def on_agent_read_jsonl(
    session_id: str,
    query: str,
    msg_ids: list[str],  # agent 读取的具体 msg_id 列表
    msg_content: str,
):
    """agent 无法从 summary 回答，降级读取 jsonl"""
    analytics.record(
        query_text=query,
        hit_source="jsonl",    # 落到 jsonl
        hit_msg_ids=msg_ids,
        hit_content=msg_content[:500],
        session_id=session_id,
    )
```

### 3.4 数据结构

```python
@dataclass
class SummaryEntry:
    topic: str          # 所属主题
    msg_range: str      # 外层 msg_id 范围，如 "a1b2c3d4~c3d4e5f6"
    content: str        # 要点内容（包含内层引用）
    inner_msg_ids: list[str]  # 内层 (msg_id-XXX) 引用的 msg_id 列表

    @property
    def all_msg_ids(self) -> list[str]:
        """外层范围 + 内层引用，合并去重"""
        outer_ids = self._parse_range(self.msg_range)
        return list(dict.fromkeys(outer_ids + self.inner_msg_ids))

    def _parse_range(self, msg_range: str) -> list[str]:
        # 兼容完整 UUID（含连字符），格式 "start_id~end_id" 或单个 id
        m = re.match(r"([a-zA-Z0-9\-]+)~([a-zA-Z0-9\-]+)", msg_range.strip())
        if m:
            return [m.group(1).lower(), m.group(2).lower()]
        return [msg_range.strip().lower()]

@dataclass
class RetrievalResult:
    hit: bool
    content: str | None
    msg_ids: list[str] | None   # 外层范围 + 内层引用的所有 msg_id
    topic: str | None
```

### 3.5 解析 summary.md 的 msg_id

summary.md 供 agent 人工阅读，解析逻辑用于提取 msg_id 供 analytics 记录：

```python
def parse_summary_for_analytics(summary: str) -> list[SummaryEntry]:
    """
    解析 summary.md 中的条目，提取外层和内层 msg_id。

    格式：
    ## <主题>
    - [msg_id: a1b2c3d4~c3d4e5f6] 子论点1（msg_id-a1b2c3d4），子论点2（msg_id-b2c3d4e5）

    返回每个要点（每个 - 行）作为一个 entry。
    内层 msg_id 提取为 best-effort：格式不完整时跳过单条，不影响整体解析。
    """
    entries = []
    topic = None

    # msg_id 允许字母、数字、连字符（兼容完整 UUID 格式）
    _MSG_ID_PATTERN = re.compile(
        r"\(msg_id-([a-zA-Z0-9\-]+)\)", re.IGNORECASE
    )

    for line in summary.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            topic = m.group(1).strip()
            continue

        m = re.match(r"^-\s+\[msg_id:\s*([^\]]+)\]\s*(.+)$", line)
        if m:
            outer_range = m.group(1).strip()
            content = m.group(2).strip()
            # 容错提取内层引用，允许 UUID 中带连字符
            inner_ids = [
                x.lower()
                for x in _MSG_ID_PATTERN.findall(content)
            ]
            entries.append(SummaryEntry(
                topic=topic or "",
                msg_range=outer_range,
                content=content,
                inner_msg_ids=inner_ids,
            ))

    return entries
```

### 3.6 压缩触发流程

```
会话进行中
  → agent 读取 MEMORY.md，判断是否需要读 summary.md
  → agent 读取 summary.md 时记录到 RetrievalAnalytics（实时）
  → agent 降级读 jsonl 时记录到 RetrievalAnalytics（实时）
  → 会话结束时触发压缩
        │
        ▼
  SummaryQualityAnalyzer.analyze(session_id)
        │ ◄── 分析失败原因，识别高频 miss 的 msg_id
        ▼
  CompressionImprover.generate_improvement_prompt()
        │ ◄── 生成带改进提示的压缩 prompt
        ▼
  调用压缩子 Agent，生成改进后的 SUMMARY.md
        │ ◄── 每个要点都标注两层 msg_id
        ▼
  新 summary 上线，等待下一轮检索数据验证
```

---

## 4. 独立压缩 Prompt 模板

```python
COMPRESSION_SYSTEM_PROMPT = """你是一个会话总结专家，专注于生成**高检索命中率**的摘要。

你的任务是将对话内容浓缩为条目式摘要，每个要点必须有外层和内层两层 msg_id 标注。

## 核心格式要求

每个要点的格式：
- [msg_id: msg-XXX~msg-YYY] 子论点1（msg_id-A），子论点2（msg_id-B, msg_id-C）

示例：
```markdown
## 用户认证模块重构

- [msg_id: a1b2c3d4~c3d4e5f6] 重构了 user_service.py 的认证逻辑（msg_id-a1b2c3d4, msg_id-b2c3d4e5），将 Session 验证从同步改为异步（msg_id-c3d4e5f6）
- [msg_id: d4e5f6g7~e5f6g7h8] 修复了 token 刷新时序问题（msg_id-d4e5f6g7），原因为 refresh_token 和 access_token 同时过期未做缓冲（msg_id-e5f6g7h8）

## Redis 连接池优化

- [msg_id: r8s9t0u1~t0u1v2w3] 问题：连接超时（msg_id-r8s9t0u1），错误码 CLUSTER_DOWN（msg_id-s9t0u1v2），max_clients 配置过小（msg_id-t0u1v2w3）
- [msg_id: u1v2w3x4~v2w3x4y5] 根因：max_clients=100（msg_id-u1v2w3x4），实际峰值 320 并发（msg_id-v2w3x4y5）
```

msg_id 必须精确到 session.jsonl 中对应的原始消息。多个连续消息用范围 `~` 分隔。

## 质量标准

1. **两层 msg_id**：外层 `[msg_id: <start_uuid>~<end_uuid>]` 标记对话块，内层 `(msg_id-<uuid>)` 标记每个子论点引用的消息
2. **具体性**：文件名、函数名、变量值、错误信息、行号必须保留
3. **关键词覆盖**：使用 query 侧可能搜索的关键词
4. **当前状态精确**：代码停在哪个文件、哪一行、什么状态
5. **忽略机械调用**：纯工具调用细节不需要记录
"""

COMPRESSION_USER_PROMPT_TEMPLATE = """## 待总结的原始对话（session.jsonl）

以下为该 session 的原始消息，请按格式要求生成摘要：

{dialogue_content}

---

## 当前摘要（如有）

本次为增量更新，基于现有摘要合并更新：

{current_summary}

---

## 检索质量报告

- **不降级到 jsonl 的命中率**：{no_jsonl_hit_rate:.0%}（{no_jsonl_hits}/{total_count} 无需读 jsonl）
- **从 summary 回答的命中率**：{summary_hit_rate:.0%}
- **高频未命中 msg_id**：
{high_miss_text}

---

## 本次总结要求

1. 将 jsonl 按交互块分组（每块通常 5-20 条 msg）
2. 每条要点的 msg_id 必须与实际内容对应
3. 增量更新：保留现有仍有效的内容，更新/替换有变化的部分
4. 重点改进高频未命中 msg_id 对应的要点内容
5. 确保关键词覆盖：{keywords}
"""
```

---

## 5. msg_id 追踪机制

压缩时正确追踪每个要点与原始消息的映射：

```python
class MsgIdAssigner:
    """
    将 jsonl 消息分组，并为每个分组分配 msg_id 范围。

    切块触发条件（满足任一即切）：
      1. 相邻消息时间间隔 > time_gap_threshold 秒
      2. 当前块消息数 >= max_block_size
    """

    def __init__(
        self,
        time_gap_threshold: int = 300,
        max_block_size: int = 20,
    ) -> None:
        self.time_gap_threshold = time_gap_threshold
        self.max_block_size = max_block_size

    def assign(self, messages: list[dict]) -> list[MsgBlock]:
        """
        将消息列表划分为交互块，每个块对应 summary 中的一条或多条要点。
        """
        blocks: list[MsgBlock] = []
        current_block: list[dict] = []
        last_timestamp = 0

        for msg in messages:
            ts = msg.get("timestamp", 0)
            time_gap = ts - last_timestamp if last_timestamp else 0
            should_cut = current_block and (
                time_gap > self.time_gap_threshold
                or len(current_block) >= self.max_block_size
            )
            if should_cut:
                blocks.append(self._finalize_block(current_block))
                current_block = []
            current_block.append(msg)
            last_timestamp = ts

        if current_block:
            blocks.append(self._finalize_block(current_block))

        return blocks

    def _finalize_block(self, messages: list[dict]) -> MsgBlock:
        first_id = messages[0]["msg_id"]
        last_id = messages[-1]["msg_id"]
        # 单条消息时范围只写一个 id，避免 "aaa~aaa" 冗余
        msg_range = first_id if first_id == last_id else f"{first_id}~{last_id}"
        return MsgBlock(
            msg_ids=[m["msg_id"] for m in messages],
            msg_range=msg_range,
            messages=messages,
        )
```

---

## 6. 可调参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `hit_rate_target` | 0.98 | 目标命中率 |
| `time_gap_threshold` | 300 | 交互间隙超过此秒数则划分新块 |
| `max_block_size` | 20 | 单个块最大消息数 |
| `min_queries_for_analysis` | 10 | 生成分析报告的最小 query 数 |
| `max_high_miss_display` | 10 | 改进提示中展示的最大高频 miss msg_id 数 |
| `analytics_retention_days` | 30 | analytics 数据保留天数 |

---

## 7. 实施优先级

**Phase 1（立即实现）**
- `RetrievalAnalytics` 数据结构与记录逻辑
- `MsgIdAssigner` msg_id 范围划分
- 在 `SessionRetrievalService` 中接入记录
- 独立压缩 Prompt 模板（静态版本）

**Phase 2（分析改进）**
- `SummaryQualityAnalyzer` 质量分析
- `CompressionImprover` 改进提示生成
- 压缩 Agent 接入分析报告

**Phase 3（持续优化）**
- 引入 embedding 相似度做精细化失败诊断
- 跨 session 聚合分析
- 自动调整块划分策略

---

## 8. 核心设计原则

- **每要点 msg_id**：每个 `-` 开头的要点都必须有 `[msg_id: ...]` 标注
- **数据驱动**：从真实检索数据学习 query 实际需要什么
- **快速回溯**：通过要点上的 msg_id 精确定位原始 jsonl 中的消息
- **反馈闭环**：检索命中/失败 → 分析原因 → 改进下次总结 → 验证命中率
- **独立组件**：压缩和分析均为 standalone 模块，不依赖主 Agent
