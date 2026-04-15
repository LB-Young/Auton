"""memory/compression_improver.py — 基于检索质量分析生成改进压缩提示

核心流程：
  RetrievalAnalytics → SummaryQualityAnalyzer.analyze() → QualityReport
  → CompressionImprover.generate_improvement_prompt()
  → 调用 LLM 生成更高质量的 SUMMARY.md

冷启动策略：
  历史 query 数量 < min_queries_for_analysis 时，使用静态 prompt，
  不依赖检索统计，保证第一个 session 也能正常工作。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .retrieval_analytics import RetrievalAnalytics


# ─── 质量报告 ──────────────────────────────────────────────────────────────────

@dataclass
class QualityReport:
    """单个 session 的 SUMMARY.md 检索质量报告"""

    session_id: str
    summary_hit_rate: float                       # 从 summary 回答的命中率
    no_jsonl_hit_rate: float                      # 不降级到 jsonl 的命中率（98% 目标）
    total_queries: int
    failed_count: int
    failed_by_msg: dict[str, list[str]]           # {msg_id: [未命中的 query 列表]}
    high_miss_msg_ids: list[str]                  # 高频 miss 的 msg_id（Top 10）
    high_freq_keywords: list[str]                 # 高频 query 关键词（Top 15）
    msg_stats: dict[str, dict[str, int]]


# ─── 质量分析器 ────────────────────────────────────────────────────────────────

class SummaryQualityAnalyzer:
    """从 RetrievalAnalytics 中分析 SUMMARY.md 的质量瓶颈。"""

    def __init__(self, analytics: "RetrievalAnalytics") -> None:
        self.analytics = analytics

    def analyze(self, session_id: str) -> QualityReport:
        """生成指定 session 的质量报告。

        Args:
            session_id: 目标 session ID

        Returns:
            QualityReport — 包含命中率、高频 miss msg_id、关键词等
        """
        failed = self.analytics.get_failed_queries(session_id)
        msg_stats = self.analytics.get_msg_id_stats()
        keywords = self.analytics.get_keyword_frequency(session_id)

        # 按 msg_id 聚合失败 query
        failed_by_msg: dict[str, list[str]] = {}
        for rec in failed:
            for mid in rec.hit_msg_ids or []:
                failed_by_msg.setdefault(mid, []).append(rec.query_text)

        high_miss_msg_ids = sorted(
            failed_by_msg.keys(),
            key=lambda m: len(failed_by_msg[m]),
            reverse=True,
        )[:10]

        return QualityReport(
            session_id=session_id,
            summary_hit_rate=self.analytics.get_summary_hit_rate(session_id),
            no_jsonl_hit_rate=self.analytics.get_no_jsonl_hit_rate(session_id),
            total_queries=self.analytics.total_count(session_id),
            failed_count=len(failed),
            failed_by_msg=failed_by_msg,
            high_miss_msg_ids=high_miss_msg_ids,
            high_freq_keywords=[k for k, _ in keywords[:15]],
            msg_stats=msg_stats,
        )


# ─── 压缩改进器 ────────────────────────────────────────────────────────────────

class CompressionImprover:
    """根据检索质量报告生成 SUMMARY.md 压缩改进提示。

    冷启动（历史 query < min_queries_for_analysis）时使用静态 prompt，
    数据充足后自动切换到数据驱动的改进 prompt。

    Args:
        analytics:                RetrievalAnalytics 实例
        analyzer:                 SummaryQualityAnalyzer 实例
        min_queries_for_analysis: 触发数据驱动改进的最小 query 数（默认 10）
    """

    def __init__(
        self,
        analytics: "RetrievalAnalytics",
        analyzer: SummaryQualityAnalyzer,
        min_queries_for_analysis: int = 10,
    ) -> None:
        self.analytics = analytics
        self.analyzer = analyzer
        self.min_queries_for_analysis = min_queries_for_analysis

    def generate_improvement_prompt(
        self,
        session_id: str,
        session_jsonl: list[dict],
        current_summary: str = "",
    ) -> str:
        """生成 SUMMARY.md 压缩提示。

        当历史数据不足时，使用静态 prompt；
        历史数据充足时，将分析报告注入 prompt 以精准改进。

        Args:
            session_id:     目标 session ID
            session_jsonl:  session.jsonl 的消息列表
            current_summary: 现有 SUMMARY.md 内容（用于增量更新）

        Returns:
            格式化的 prompt 字符串
        """
        total = self.analytics.total_count(session_id)
        if total < self.min_queries_for_analysis:
            return self._generate_static_prompt(session_jsonl, current_summary)

        report = self.analyzer.analyze(session_id)
        return self._generate_data_driven_prompt(report, session_jsonl, current_summary)

    # ─── 冷启动静态 prompt ─────────────────────────────────────────────────

    def _generate_static_prompt(
        self,
        session_jsonl: list[dict],
        current_summary: str,
    ) -> str:
        """冷启动阶段使用的静态 prompt（无检索数据时）。"""
        dialogue = self._format_jsonl(session_jsonl)
        summary_section = (
            f"\n## 当前 summary（增量更新基础）\n\n{current_summary}"
            if current_summary.strip()
            else ""
        )
        return f"""\
你是一个会话总结助手，请将对话内容浓缩为高检索命中率的结构化摘要。

## 格式要求

每条要点必须标注来源 msg_id（两层）：

```markdown
## <主题>

- [msg_id: <start_id>~<end_id>] 子论点1（msg_id-A），子论点2（msg_id-B, msg_id-C）
- [msg_id: <single_id>] 子论点3（msg_id-D）
```

**两层 msg_id 说明**：
- 外层 `[msg_id: start~end]`：标记这条要点对应的对话块范围
- 内层 `(msg_id-XXX)`：每个子论点精确引用的单条消息

## 总结原则

1. **具体优先于抽象**：保留文件名、函数名、变量名、具体数值、错误信息
2. **决策理由要写**：不仅写结论，写为什么这么做
3. **当前状态要精确**：代码停在哪个文件、哪一行、什么状态
4. **忽略机械调用**：纯工具调用细节（无结果的 Read/Glob/Bash）不需要记录

## 待总结的原始对话（session.jsonl）

{dialogue}
{summary_section}
"""

    # ─── 数据驱动改进 prompt ───────────────────────────────────────────────

    def _generate_data_driven_prompt(
        self,
        report: QualityReport,
        session_jsonl: list[dict],
        current_summary: str,
    ) -> str:
        """数据充足时使用的改进 prompt，将质量报告注入以精准改进。"""
        no_jsonl_hits = report.total_queries - report.failed_count
        dialogue = self._format_jsonl(session_jsonl)
        summary_section = (
            f"\n## 当前 summary（增量更新基础）\n\n{current_summary}"
            if current_summary.strip()
            else ""
        )
        return f"""\
你是一个会话总结助手，请将对话内容浓缩为结构化摘要。

## 质量目标

本次总结需要达到 **98% 检索命中率**——后续 query 应尽可能从本摘要回答，无需再读取原始 jsonl。

## 重要格式要求

每条要点必须标注来源 msg_id：

```markdown
## <主题>

- [msg_id: <start_id>~<end_id>] 子论点1（msg_id-A），子论点2（msg_id-B, msg_id-C）
```

**两层 msg_id**：外层 `[msg_id: ...]` 标记对话块，内层 `(msg_id-XXX)` 标记每个子论点引用的消息。

## 本 session 检索分析结果

### 命中率
- 不降级到 jsonl 的命中率：{report.no_jsonl_hit_rate:.0%}（{no_jsonl_hits}/{report.total_queries} 的 query 无需读 jsonl）
- 从 summary 回答的命中率：{report.summary_hit_rate:.0%}
- 总查询数：{report.total_queries}，失败数：{report.failed_count}

### 高频未命中的 msg_id（这些要点需要重点补强）

{self._format_high_miss_msg_ids(report)}

### 高频 query 关键词
以下关键词在真实 query 中出现频繁，总结时应优先覆盖：
{_keyword_hint_text(report.high_freq_keywords)}

## 总结原则

1. **两层 msg_id**：外层标对话块，内层标每个子论点
2. **具体优先于抽象**：保留文件名、函数名、变量名、具体数值、配置值、错误信息
3. **覆盖关键词**：上述高频关键词对应的知识点必须写入 summary
4. **决策理由要写**：不仅写结论，写为什么这么做
5. **当前状态要精确**：代码停在哪个文件、哪一行、什么状态
6. **忽略机械调用**：纯工具调用细节不需要记录

## 待总结的原始对话（session.jsonl）

{dialogue}
{summary_section}
"""

    # ─── 辅助方法 ──────────────────────────────────────────────────────────

    def _format_high_miss_msg_ids(self, report: QualityReport) -> str:
        if not report.high_miss_msg_ids:
            return "无失败记录。"
        lines = []
        for mid in report.high_miss_msg_ids:
            queries = report.failed_by_msg.get(mid, [])
            lines.append(f"- **{mid}**（{len(queries)} 条未命中）")
            for q in queries[:3]:
                lines.append(f'  - "{q}"')
        return "\n".join(lines)

    def _format_jsonl(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            mid = msg.get("msg_id", "")
            role = msg.get("role", "")
            content = str(msg.get("content", ""))[:300]
            lines.append(f"[{mid}] {role}: {content}")
        return "\n".join(lines)


def _keyword_hint_text(keywords: list[str]) -> str:
    if not keywords:
        return "（无数据）"
    return ", ".join(f"**{k}**" for k in keywords)
