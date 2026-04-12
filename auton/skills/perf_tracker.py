"""Skills Performance Tracker — 追踪、分析、优化触发

核心职责：
  - 为每个 Skill 维护 SKILL_PERF.json（统计元数据）
  - 为每个 Skill 维护 fragments_index.jsonl（调用片段引用索引）
  - 每次调用结束时更新累积统计和 7 日窗口统计
  - 判断是否满足优化触发条件

数据文件位置：
  ~/.auton/skill/<skill-name>/SKILL_PERF.json
  ~/.auton/skill/<skill-name>/fragments_index.jsonl
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from .types import SkillPerfConfig

if TYPE_CHECKING:
    from .types import Skill


# ─── 公共数据类 ──────────────────────────────────────────────────────────────


@dataclass
class SkillPerfStats:
    """聚合统计数据（从 SKILL_PERF.json 读取）"""
    total_invocations: int
    successful_invocations: int
    failed_invocations: int
    success_rate: float
    avg_tool_calls: float
    avg_turns: float
    avg_duration_ms: float
    last_invocation: str | None


@dataclass
class SkillPerfRecord:
    """单条调用历史记录（从 fragments_index.jsonl 解析）"""
    fragment_id: str
    session_id: str
    skill_name: str
    trigger: str                    # "auto" | "manual"
    query: str
    tool_calls_count: int
    llm_turns: int
    duration_ms: float
    success: bool
    error_message: str | None
    timestamp: float
    session_path: Path | None = None
    line_start: int = 0
    line_end: int = 0


# ─── 内部数据结构 ─────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _default_perf_dict(skill_name: str) -> dict:
    return {
        "skill_name": skill_name,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "thresholds": {
            "success_rate_min": 0.70,
            "avg_tool_calls_max": 15,
            "avg_turns_max": 5,
        },
        "cumulative": {
            "total_invocations": 0,
            "successful_invocations": 0,
            "failed_invocations": 0,
            "success_rate": 0.0,
            "avg_tool_calls": 0.0,
            "avg_turns": 0.0,
            "avg_duration_ms": 0.0,
            "last_invocation": None,
        },
        "window_7d": {
            "total_invocations": 0,
            "successful_invocations": 0,
            "success_rate": 0.0,
            "avg_tool_calls": 0.0,
            "avg_turns": 0.0,
            "alert_triggered": False,
        },
        "alert": {
            "enabled": True,
            "last_alert_at": None,
            "alert_count": 0,
        },
    }


# ─── 主类 ─────────────────────────────────────────────────────────────────────


class SkillPerfTracker:
    """Skill 性能追踪器。

    用法（由 SessionProcessor Week-2 集成）::

        tracker = SkillPerfTracker(skill)
        fragment_id = tracker.record_invocation_start(
            trigger="auto", query="帮我调试 Python", turn_index=3
        )
        # ... 执行工具、LLM 轮次 ...
        tracker.record_invocation_end(
            fragment_id=fragment_id,
            session_id="abc123",
            turn_index=3,
            tool_calls_count=7,
            llm_turns=2,
            duration_ms=8500,
            success=True,
            error_message=None,
            session_path=Path("~/.auton/memory/.../abc123.jsonl"),
            line_start=42,
            line_end=89,
        )
        should, reason = tracker.should_optimize()
    """

    PERF_FILE = "SKILL_PERF.json"
    FRAGMENTS_INDEX = "fragments_index.jsonl"
    WINDOW_DAYS = 7

    def __init__(self, skill: "Skill") -> None:
        self.skill = skill
        self._perf_path = skill.skill_dir / self.PERF_FILE
        self._fragments_path = skill.skill_dir / self.FRAGMENTS_INDEX
        self._logger = logger.bind(name="SkillPerfTracker", skill=skill.name)
        self._ensure_init()

    # ─── 初始化 ────────────────────────────────────────────────────────────────

    def _ensure_init(self) -> None:
        """首次调用时创建 SKILL_PERF.json（若不存在）。"""
        if not self._perf_path.exists():
            self._perf_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_perf(_default_perf_dict(self.skill.name))
            self._logger.debug("initialized SKILL_PERF.json")

    # ─── 运行时记录 API ────────────────────────────────────────────────────────

    def record_invocation_start(
        self,
        trigger: str,
        query: str,
        turn_index: int,
    ) -> str:
        """Skill 被注入 context 时调用，返回 fragment_id。

        Args:
            trigger: "auto"（LLM 自动）或 "manual"（用户显式）
            query: 本轮用户请求文本
            turn_index: 当前 session 中的轮次索引

        Returns:
            fragment_id（供后续 record_invocation_end 使用）
        """
        ms = int(time.time() * 1000)
        fragment_id = f"{self.skill.name}-{turn_index}-{ms}"
        self._logger.debug(
            "invocation start fragment={f} trigger={t}", f=fragment_id, t=trigger
        )
        return fragment_id

    def record_invocation_end(
        self,
        fragment_id: str,
        session_id: str,
        turn_index: int,
        tool_calls_count: int,
        llm_turns: int,
        duration_ms: float,
        success: bool,
        error_message: str | None = None,
        session_path: Path | None = None,
        line_start: int = 0,
        line_end: int = 0,
        trigger: str = "auto",
        query: str = "",
    ) -> None:
        """一轮执行结束时调用，更新所有统计并写入片段索引。

        Args:
            fragment_id: record_invocation_start() 返回的 ID
            session_id: 当前会话 ID
            turn_index: 当前轮次索引
            tool_calls_count: 本轮工具调用次数
            llm_turns: 本轮 LLM 调用轮数
            duration_ms: 本轮耗时（毫秒）
            success: 是否成功
            error_message: 失败时的错误信息
            session_path: session JSONL 文件路径（用于片段回放定位）
            line_start: skill 片段在 JSONL 中的起始行号
            line_end: skill 片段在 JSONL 中的结束行号
            trigger: 触发方式
            query: 用户原始请求
        """
        ts = time.time()
        self._update_cumulative(success, tool_calls_count, llm_turns, duration_ms)
        self._append_fragment_index(  # 必须先追加，_update_window_7d 才能读到最新数据
            fragment_id=fragment_id,
            session_id=session_id,
            trigger=trigger,
            query=query,
            tool_calls_count=tool_calls_count,
            llm_turns=llm_turns,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
            session_path=session_path,
            line_start=line_start,
            line_end=line_end,
            timestamp=ts,
        )
        self._update_window_7d()  # 先追加 fragment，再全量重算 7 日窗口
        self._check_alert()
        self._logger.info(
            "invocation end fragment={f} success={s} tool_calls={t} turns={r}",
            f=fragment_id,
            s=success,
            t=tool_calls_count,
            r=llm_turns,
        )

    # ─── 查询 API ──────────────────────────────────────────────────────────────

    def get_stats(self, window: str = "cumulative") -> SkillPerfStats:
        """读取统计数据。

        Args:
            window: "cumulative"（全量）或 "7d"（7 日窗口）
        """
        data = self._read_perf()
        if window == "7d":
            w = data["window_7d"]
            return SkillPerfStats(
                total_invocations=w["total_invocations"],
                successful_invocations=w["successful_invocations"],
                failed_invocations=w["total_invocations"] - w["successful_invocations"],
                success_rate=w["success_rate"],
                avg_tool_calls=w["avg_tool_calls"],
                avg_turns=w["avg_turns"],
                avg_duration_ms=0.0,
                last_invocation=None,
            )
        c = data["cumulative"]
        return SkillPerfStats(
            total_invocations=c["total_invocations"],
            successful_invocations=c["successful_invocations"],
            failed_invocations=c["failed_invocations"],
            success_rate=c["success_rate"],
            avg_tool_calls=c["avg_tool_calls"],
            avg_turns=c["avg_turns"],
            avg_duration_ms=c["avg_duration_ms"],
            last_invocation=c["last_invocation"],
        )

    def get_fragments(
        self,
        limit: int = 50,
        successful_only: bool = False,
        failed_only: bool = False,
        days: int | None = None,
    ) -> list[SkillPerfRecord]:
        """读取 fragments_index.jsonl，返回历史片段列表（最新优先）。

        Args:
            limit: 最大返回条数
            successful_only: 只返回成功片段
            failed_only: 只返回失败片段
            days: 只返回最近 N 天的片段（None=全量）
        """
        records: list[SkillPerfRecord] = []
        if not self._fragments_path.exists():
            return records

        cutoff = (time.time() - days * 86400) if days else 0.0

        with open(self._fragments_path, encoding="utf-8") as f:
            lines = f.readlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = entry.get("timestamp", 0.0)
            if days and ts < cutoff:
                continue

            success = entry.get("success", True)
            if successful_only and not success:
                continue
            if failed_only and success:
                continue

            sp = entry.get("session_path")
            records.append(
                SkillPerfRecord(
                    fragment_id=entry.get("fragment_id", ""),
                    session_id=entry.get("session_id", ""),
                    skill_name=self.skill.name,
                    trigger=entry.get("trigger", "auto"),
                    query=entry.get("query", ""),
                    tool_calls_count=entry.get("tool_calls_count", 0),
                    llm_turns=entry.get("llm_turns", 0),
                    duration_ms=entry.get("duration_ms", 0.0),
                    success=success,
                    error_message=entry.get("error_message"),
                    timestamp=ts,
                    session_path=Path(sp) if sp else None,
                    line_start=entry.get("line_start", 0),
                    line_end=entry.get("line_end", 0),
                )
            )
            if len(records) >= limit:
                break

        return records

    def get_config(self) -> SkillPerfConfig:
        """读取当前阈值配置。"""
        data = self._read_perf()
        t = data.get("thresholds", {})
        return SkillPerfConfig(
            success_rate_min=t.get("success_rate_min", 0.70),
            avg_tool_calls_max=t.get("avg_tool_calls_max", 15.0),
            avg_turns_max=t.get("avg_turns_max", 5.0),
        )

    def set_config(self, config: SkillPerfConfig) -> None:
        """更新阈值配置并持久化。"""
        data = self._read_perf()
        data["thresholds"] = {
            "success_rate_min": config.success_rate_min,
            "avg_tool_calls_max": config.avg_tool_calls_max,
            "avg_turns_max": config.avg_turns_max,
        }
        data["updated_at"] = _now_iso()
        self._write_perf(data)

    # ─── 优化触发 ──────────────────────────────────────────────────────────────

    def should_optimize(self) -> tuple[bool, str]:
        """判断 7 日窗口指标是否触发优化条件。

        触发条件（OR 关系）：
          - window_7d.success_rate < thresholds.success_rate_min
          - window_7d.avg_tool_calls > thresholds.avg_tool_calls_max
          - window_7d.avg_turns > thresholds.avg_turns_max

        Returns:
            (should_optimize, reason_message)
        """
        data = self._read_perf()
        w = data["window_7d"]
        t = data["thresholds"]
        alert = data.get("alert", {})

        if not alert.get("enabled", True):
            return False, "alerts disabled"

        if w["total_invocations"] < 3:
            return False, f"too few invocations ({w['total_invocations']} < 3)"

        reasons: list[str] = []
        if w["success_rate"] < t["success_rate_min"]:
            reasons.append(
                f"success_rate={w['success_rate']:.1%} < {t['success_rate_min']:.1%}"
            )
        if w["avg_tool_calls"] > t["avg_tool_calls_max"]:
            reasons.append(
                f"avg_tool_calls={w['avg_tool_calls']:.1f} > {t['avg_tool_calls_max']}"
            )
        if w["avg_turns"] > t["avg_turns_max"]:
            reasons.append(
                f"avg_turns={w['avg_turns']:.1f} > {t['avg_turns_max']}"
            )

        if not reasons:
            return False, "all metrics within thresholds"

        return True, "；".join(reasons)

    async def calibrate_thresholds(
        self,
        llm: "LLMProvider",
        overhead_factor: float = 1.2,
    ) -> SkillPerfConfig:
        """用 LLM 评估该 Skill 的合理工具调用次数和轮次，以此设置动态阈值。

        策略：
          - 向 LLM 提供 SKILL.md 内容
          - 让 LLM 评估：「执行一个典型任务大约需要多少次工具调用 / 多少轮 LLM 对话？」
          - threshold = LLM 估算值 × overhead_factor（默认 1.2，即允许 20% 超量）
          - success_rate_min 保持默认 0.70（无法从 SKILL.md 推断）

        Args:
            llm: LLM Provider 实例
            overhead_factor: 估算值的容忍倍数，默认 1.2（+20% 作为上限）

        Returns:
            标定后的 SkillPerfConfig（已写入 SKILL_PERF.json）
        """
        from ..agent.message import Message
        from ..agent.types import LLMContext

        try:
            skill_content = self.skill.path.read_text(encoding="utf-8")[:4000]
        except Exception:
            skill_content = self.skill.body[:4000]

        system_prompt = (
            "你是一名经验丰富的 AI 工程师，专门分析 Skill 的复杂度。\n"
            "请根据给定的 SKILL.md 内容，评估执行一个**典型任务**时大约需要：\n"
            "  1. 多少次工具调用（tool_calls）？\n"
            "  2. 多少轮 LLM 对话（llm_turns）？\n\n"
            "请只输出 JSON，格式如下，不要输出任何其他内容：\n"
            '{"expected_tool_calls": <整数>, "expected_turns": <整数>, "reasoning": "<一句话理由>"}'
        )
        user_content = f"以下是 SKILL.md 内容：\n\n{skill_content}"

        user_msg = Message(role="user")
        user_msg.add_text(user_content)

        ctx = LLMContext(
            session_id="calibrate",
            messages=[user_msg],
            tools=[],
            system_prompt=system_prompt,
            model=llm.model_name,
            max_tokens=256,
            temperature=0.0,
        )

        raw = ""
        async for event in llm.stream(ctx):
            text = getattr(event, "text", None) or (
                event.get("text", "") if isinstance(event, dict) else ""
            )
            raw += text

        import re as _re
        m = _re.search(r'\{[^}]+\}', raw, _re.DOTALL)
        if not m:
            self._logger.warning("LLM calibration: failed to parse JSON, using defaults. raw={r}", r=raw[:200])
            return self.get_config()

        try:
            parsed = json.loads(m.group())
            est_tool_calls = float(parsed.get("expected_tool_calls", 15))
            est_turns = float(parsed.get("expected_turns", 5))
            reasoning = parsed.get("reasoning", "")
        except (json.JSONDecodeError, ValueError) as exc:
            self._logger.warning("LLM calibration: JSON parse error {e}, using defaults", e=exc)
            return self.get_config()

        config = SkillPerfConfig(
            success_rate_min=0.70,
            avg_tool_calls_max=round(est_tool_calls * overhead_factor, 1),
            avg_turns_max=round(est_turns * overhead_factor, 1),
        )
        self.set_config(config)

        self._logger.info(
            "thresholds calibrated: tool_calls≤{tc} turns≤{t} (estimate×{f}) reason={r}",
            tc=config.avg_tool_calls_max,
            t=config.avg_turns_max,
            f=overhead_factor,
            r=reasoning,
        )
        return config

    def collect_optimization_context(
        self,
        successful_fragments_limit: int = 10,
        failed_fragments_limit: int = 10,
    ) -> str:
        """收集用于 LLM 优化分析的上下文文本。

        格式：
          - 7 日统计摘要
          - 成功片段列表（query + 关键指标）
          - 失败片段列表（query + 错误信息）
        """
        data = self._read_perf()
        w = data["window_7d"]
        t = data["thresholds"]

        lines: list[str] = [
            f"## Skill `{self.skill.name}` 性能分析（最近 {self.WINDOW_DAYS} 天）",
            "",
            f"| 指标 | 实际值 | 阈值 | 状态 |",
            f"|------|--------|------|------|",
            f"| 成功率 | {w['success_rate']:.1%} | ≥{t['success_rate_min']:.1%} | {'🔴' if w['success_rate'] < t['success_rate_min'] else '✅'} |",
            f"| 平均工具调用 | {w['avg_tool_calls']:.1f} | ≤{t['avg_tool_calls_max']} | {'🔴' if w['avg_tool_calls'] > t['avg_tool_calls_max'] else '✅'} |",
            f"| 平均轮次 | {w['avg_turns']:.1f} | ≤{t['avg_turns_max']} | {'🔴' if w['avg_turns'] > t['avg_turns_max'] else '✅'} |",
            f"| 总调用次数 | {w['total_invocations']} | — | — |",
            "",
        ]

        # 成功片段
        success_frags = self.get_fragments(
            limit=successful_fragments_limit, successful_only=True, days=self.WINDOW_DAYS
        )
        lines.append(f"### 成功片段（{len(success_frags)} 条）")
        for i, rec in enumerate(success_frags, 1):
            lines.append(
                f"{i}. query={rec.query!r} tool_calls={rec.tool_calls_count} turns={rec.llm_turns} duration={rec.duration_ms:.0f}ms"
            )
        lines.append("")

        # 失败片段
        failed_frags = self.get_fragments(
            limit=failed_fragments_limit, failed_only=True, days=self.WINDOW_DAYS
        )
        lines.append(f"### 失败片段（{len(failed_frags)} 条）")
        for i, rec in enumerate(failed_frags, 1):
            err = rec.error_message or "（未记录错误）"
            lines.append(
                f"{i}. query={rec.query!r} error={err!r} tool_calls={rec.tool_calls_count}"
            )
        lines.append("")

        # 当前 SKILL.md
        try:
            skill_md = self.skill.path.read_text(encoding="utf-8")[:3000]
            lines.append("### 当前 SKILL.md（前 3000 字符）")
            lines.append("```markdown")
            lines.append(skill_md)
            lines.append("```")
        except Exception:
            pass

        return "\n".join(lines)

    # ─── 内部更新方法 ──────────────────────────────────────────────────────────

    def _update_cumulative(
        self,
        success: bool,
        tool_calls: int,
        turns: int,
        duration_ms: float,
    ) -> None:
        """原子更新 cumulative 统计块并写回 JSON。"""
        data = self._read_perf()
        c = data["cumulative"]

        n = c["total_invocations"]
        c["total_invocations"] = n + 1
        if success:
            c["successful_invocations"] += 1
        else:
            c["failed_invocations"] += 1

        # 增量更新均值（避免重算全部 fragments）
        c["avg_tool_calls"] = _incremental_avg(c["avg_tool_calls"], tool_calls, n)
        c["avg_turns"] = _incremental_avg(c["avg_turns"], turns, n)
        c["avg_duration_ms"] = _incremental_avg(c["avg_duration_ms"], duration_ms, n)

        total = c["total_invocations"]
        c["success_rate"] = c["successful_invocations"] / total if total else 0.0
        c["last_invocation"] = _now_iso()

        data["updated_at"] = _now_iso()
        self._write_perf(data)

    def _update_window_7d(self) -> None:
        """从 fragments_index.jsonl 全量重算 7 日窗口统计（写回 JSON）。"""
        frags = self.get_fragments(limit=10_000, days=self.WINDOW_DAYS)
        if not frags:
            window = {
                "total_invocations": 0,
                "successful_invocations": 0,
                "success_rate": 0.0,
                "avg_tool_calls": 0.0,
                "avg_turns": 0.0,
                "alert_triggered": False,
            }
        else:
            n = len(frags)
            successes = sum(1 for r in frags if r.success)
            window = {
                "total_invocations": n,
                "successful_invocations": successes,
                "success_rate": successes / n,
                "avg_tool_calls": sum(r.tool_calls_count for r in frags) / n,
                "avg_turns": sum(r.llm_turns for r in frags) / n,
                "alert_triggered": False,
            }

        data = self._read_perf()
        data["window_7d"] = window
        data["updated_at"] = _now_iso()
        self._write_perf(data)

    def _append_fragment_index(
        self,
        fragment_id: str,
        session_id: str,
        trigger: str,
        query: str,
        tool_calls_count: int,
        llm_turns: int,
        duration_ms: float,
        success: bool,
        error_message: str | None,
        session_path: Path | None,
        line_start: int,
        line_end: int,
        timestamp: float,
    ) -> None:
        """追加一条记录到 fragments_index.jsonl（只追加，不修改已有行）。"""
        entry = {
            "fragment_id": fragment_id,
            "session_id": session_id,
            "trigger": trigger,
            "query": query,
            "tool_calls_count": tool_calls_count,
            "llm_turns": llm_turns,
            "duration_ms": duration_ms,
            "success": success,
            "error_message": error_message,
            "session_path": str(session_path) if session_path else None,
            "line_start": line_start,
            "line_end": line_end,
            "timestamp": timestamp,
        }
        self._fragments_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._fragments_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _check_alert(self) -> None:
        """检查是否触发告警，若是则记录到 SKILL_PERF.json。"""
        should, reason = self.should_optimize()
        if not should:
            return

        data = self._read_perf()
        alert = data.setdefault("alert", {})
        alert["last_alert_at"] = _now_iso()
        alert["alert_count"] = alert.get("alert_count", 0) + 1
        data["window_7d"]["alert_triggered"] = True
        data["updated_at"] = _now_iso()
        self._write_perf(data)

        self._logger.warning(
            "skill {n} optimization alert! reason={r} count={c}",
            n=self.skill.name,
            r=reason,
            c=alert["alert_count"],
        )

    # ─── JSON 读写 ─────────────────────────────────────────────────────────────

    def _read_perf(self) -> dict:
        try:
            return json.loads(self._perf_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = _default_perf_dict(self.skill.name)
            self._write_perf(data)
            return data

    def _write_perf(self, data: dict) -> None:
        self._perf_path.parent.mkdir(parents=True, exist_ok=True)
        self._perf_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


# ─── 辅助 ─────────────────────────────────────────────────────────────────────


def _incremental_avg(old_avg: float, new_value: float, old_count: int) -> float:
    """增量更新均值（避免重读全部 fragments）。"""
    if old_count <= 0:
        return float(new_value)
    return (old_avg * old_count + new_value) / (old_count + 1)


# ─── 工厂函数 ─────────────────────────────────────────────────────────────────


def skill_perf_tracker(skill_name: str, skills_dir: Path | None = None) -> "SkillPerfTracker | None":
    """根据 skill 名称获取 SkillPerfTracker 实例。

    优先在用户级技能目录（~/.auton/skill/）查找，也可通过 skills_dir 指定。

    Args:
        skill_name: skill 名称
        skills_dir: 可选，覆盖默认搜索路径

    Returns:
        SkillPerfTracker 实例，若 skill 不存在则返回 None
    """
    from .loader import SkillLoader
    from .types import SkillSource

    search_dirs = [skills_dir] if skills_dir else []
    search_dirs.append(Path.home() / ".auton" / "skill")

    for base in search_dirs:
        skill_dir = base / skill_name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            try:
                from .frontmatter import parse_skill_file
                skill = parse_skill_file(skill_md, source=SkillSource.USER)
                return SkillPerfTracker(skill)
            except Exception as exc:
                logger.warning("failed to load skill {n}: {e}", n=skill_name, e=exc)
                return None

    return None
