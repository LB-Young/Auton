"""Skills Optimizer — 基于追踪数据自动优化 Skill

完整优化流程：
  1. 调 should_optimize() 判断是否达到阈值
  2. 调 collect_optimization_context() 收集成功/失败片段 + 指标
  3. 调 LLM 生成结构化优化建议（分析 + 新 SKILL.md body + 新经验条目）
  4. 将新 body 写回 SKILL.md
  5. 将经验条目追加到 experiences/README.md
  6. 清除 alert_triggered 标志（防止重复触发）
  7. 返回 OptimizationResult

输出格式：LLM 生成的内容用 ===SECTION=== 分隔，解析稳定、无需 JSON。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from ..llm.base import LLMProvider
    from .perf_tracker import SkillPerfTracker


# ─── 结果数据类 ───────────────────────────────────────────────────────────────


@dataclass
class OptimizationResult:
    """一次 Skill 优化的完整记录"""
    skill_name: str
    triggered_at: str                   # ISO 时间戳
    trigger_reason: str                 # 触发原因（来自 should_optimize）
    analysis: str                       # LLM 分析文本
    skill_md_updated: bool = False      # SKILL.md 是否已更新
    experiences_appended: bool = False  # experiences 是否已追加
    changes_summary: str = ""           # 变更摘要（供 /skill tune 显示）
    error: str | None = None            # 若失败，记录错误信息


# ─── 系统提示词 ───────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一名资深 AI 工程专家，专门优化 Skill（Agent 技能文档）。

你会收到：
1. 某个 Skill 的性能统计（成功率、工具调用次数、LLM 轮次）
2. 成功调用片段列表（query + 指标）
3. 失败调用片段列表（query + 错误信息）
4. 当前 SKILL.md 内容

你的任务：
- 分析失败原因和效率瓶颈
- 提出改进建议
- 生成优化后的完整 SKILL.md body（不含 frontmatter）
- 生成一条 experiences 经验条目

输出格式（严格按以下分隔符）：
===ANALYSIS===
（对失败原因和优化方向的简明分析，200字以内）

===NEW_SKILL_MD===
（优化后的完整 SKILL.md body，不含 ---frontmatter--- 部分）

===EXPERIENCE_ENTRY===
（一条新的经验记录，格式如下）
### {今天日期}: {简短标题}
- **场景**：描述触发失败的典型场景
- **教训/最佳实践**：如何避免或解决
- **标签**：#相关标签
"""

_USER_TEMPLATE = """\
{context}

请根据以上信息生成优化建议。
"""


# ─── 主类 ─────────────────────────────────────────────────────────────────────


class SkillOptimizer:
    """Skill 持续优化器。

    用法::

        tracker = SkillPerfTracker(skill)
        should, reason = tracker.should_optimize()
        if should:
            optimizer = SkillOptimizer(tracker, llm)
            result = await optimizer.optimize()
            print(result.changes_summary)
    """

    def __init__(
        self,
        tracker: "SkillPerfTracker",
        llm: "LLMProvider",
    ) -> None:
        self.tracker = tracker
        self.llm = llm
        self._logger = logger.bind(name="SkillOptimizer", skill=tracker.skill.name)

    # ─── 公共接口 ──────────────────────────────────────────────────────────────

    async def optimize(
        self,
        force: bool = False,
        successful_limit: int = 10,
        failed_limit: int = 10,
    ) -> OptimizationResult:
        """执行完整优化流程。

        Args:
            force: 跳过 should_optimize() 检查，强制优化（/skill tune 手动触发用）
            successful_limit: 送入 LLM 的最大成功片段数
            failed_limit: 送入 LLM 的最大失败片段数

        Returns:
            OptimizationResult 记录优化结果
        """
        from datetime import datetime, timezone
        triggered_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 1. 检查是否满足触发条件
        should, reason = self.tracker.should_optimize()
        if not should and not force:
            return OptimizationResult(
                skill_name=self.tracker.skill.name,
                triggered_at=triggered_at,
                trigger_reason="skipped",
                analysis="未达到优化触发阈值，跳过。",
                changes_summary="无需优化。",
            )

        trigger_reason = reason if should else "手动触发（force=True）"
        self._logger.info("optimizing skill={n} reason={r}", n=self.tracker.skill.name, r=trigger_reason)

        # 2. 收集优化上下文
        context = self.tracker.collect_optimization_context(
            successful_fragments_limit=successful_limit,
            failed_fragments_limit=failed_limit,
        )

        # 3. 调 LLM 生成建议
        try:
            analysis, new_body, experience_entry = await self._generate_suggestion(context)
        except Exception as exc:
            self._logger.error("LLM suggestion failed: {e}", e=exc)
            return OptimizationResult(
                skill_name=self.tracker.skill.name,
                triggered_at=triggered_at,
                trigger_reason=trigger_reason,
                analysis="",
                error=str(exc),
                changes_summary=f"优化失败：{exc}",
            )

        result = OptimizationResult(
            skill_name=self.tracker.skill.name,
            triggered_at=triggered_at,
            trigger_reason=trigger_reason,
            analysis=analysis,
        )

        # 4. 更新 SKILL.md
        if new_body.strip():
            try:
                self._apply_to_skill_md(new_body.strip())
                result.skill_md_updated = True
                self._logger.info("SKILL.md updated for {n}", n=self.tracker.skill.name)
            except Exception as exc:
                self._logger.warning("failed to update SKILL.md: {e}", e=exc)

        # 5. 追加 experiences
        if experience_entry.strip():
            try:
                self._append_experiences(experience_entry.strip())
                result.experiences_appended = True
                self._logger.info("experiences appended for {n}", n=self.tracker.skill.name)
            except Exception as exc:
                self._logger.warning("failed to append experiences: {e}", e=exc)

        # 6. 清除 alert 标志（确保不重复触发）
        try:
            self.tracker._clear_alert()
        except Exception as exc:
            self._logger.warning("failed to clear alert flag: {e}", e=exc)

        # 7. 生成变更摘要
        parts = [f"**Skill `{self.tracker.skill.name}` 优化完成**\n"]
        parts.append(f"**触发原因**：{trigger_reason}\n")
        parts.append(f"**分析**：\n{analysis}\n")
        parts.append(f"**SKILL.md**：{'✅ 已更新' if result.skill_md_updated else '⚠️ 未变更'}")
        parts.append(f"**Experiences**：{'✅ 已追加' if result.experiences_appended else '⚠️ 未追加'}")
        result.changes_summary = "\n".join(parts)

        return result

    # ─── 内部方法 ──────────────────────────────────────────────────────────────

    async def _generate_suggestion(
        self, context: str
    ) -> tuple[str, str, str]:
        """调 LLM 生成结构化优化建议。

        Returns:
            (analysis, new_skill_md_body, experience_entry)
        """
        from ..agent.message import Message
        from ..agent.types import LLMContext

        user_msg = Message(role="user")
        user_msg.add_text(_USER_TEMPLATE.format(context=context))

        ctx = LLMContext(
            session_id="optimize",
            messages=[user_msg],
            tools=[],
            system_prompt=_SYSTEM_PROMPT,
            model=self.llm.model_name,
            max_tokens=4096,
            temperature=0.3,
        )

        raw = ""
        async for event in self.llm.stream(ctx):
            text = getattr(event, "text", None) or (
                event.get("text", "") if isinstance(event, dict) else ""
            )
            raw += text

        return self._parse_llm_output(raw)

    def _parse_llm_output(self, raw: str) -> tuple[str, str, str]:
        """解析 LLM 输出的三个分隔块。"""
        def extract(tag: str) -> str:
            pattern = rf"==={tag}===\s*(.*?)(?====[A-Z_]+=====|$)"
            m = re.search(pattern, raw, re.DOTALL)
            return m.group(1).strip() if m else ""

        analysis = extract("ANALYSIS")
        new_body = extract("NEW_SKILL_MD")
        experience = extract("EXPERIENCE_ENTRY")

        if not analysis:
            # 降级：把整个输出作为 analysis
            analysis = raw.strip()[:500]

        return analysis, new_body, experience

    def _apply_to_skill_md(self, new_body: str) -> None:
        """将 LLM 生成的新 body 写回 SKILL.md（保留 frontmatter）。

        SKILL.md 格式：
          ---
          frontmatter...
          ---

          body...

        这里只替换 --- 之后的 body 部分，frontmatter 保持不变。
        """
        skill_path = self.tracker.skill.path
        original = skill_path.read_text(encoding="utf-8")

        # 提取 frontmatter 部分
        if original.startswith("---"):
            end = original.find("---", 3)
            if end != -1:
                frontmatter = original[: end + 3]
                updated = frontmatter + "\n\n" + new_body + "\n"
                skill_path.write_text(updated, encoding="utf-8")
                return

        # 无 frontmatter：直接覆盖
        skill_path.write_text(new_body + "\n", encoding="utf-8")

    def _append_experiences(self, entry: str) -> None:
        """将新经验条目追加到 experiences/README.md。

        - 文件不存在时自动创建
        - 追加到文件末尾，前后各空一行
        """
        exp_path: Path = self.tracker.skill.experiences_path
        exp_path.parent.mkdir(parents=True, exist_ok=True)

        # 确保条目包含日期（若 LLM 没有填日期则补上）
        today = date.today().isoformat()
        if today not in entry and "YYYY-MM-DD" in entry:
            entry = entry.replace("YYYY-MM-DD", today)

        if not exp_path.exists():
            skill_name = self.tracker.skill.name
            header = (
                f"# {skill_name} 使用经验\n\n"
                "本文档记录本 skill 在实际使用中积累的经验和教训。\n"
            )
            exp_path.write_text(header + "\n## 经验条目\n\n" + entry + "\n", encoding="utf-8")
        else:
            existing = exp_path.read_text(encoding="utf-8")
            exp_path.write_text(existing.rstrip() + "\n\n" + entry + "\n", encoding="utf-8")
