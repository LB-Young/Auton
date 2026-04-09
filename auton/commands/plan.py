"""Plan Command — /plan (M8 Planning Engine)"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from ..planner import (
    Plan,
    Planner,
    RiskAnalyzer,
)
from .base import Command, CommandResult


# ─── 确认关键词 ────────────────────────────────────────────────────────────────

CONFIRM_KEYWORDS = {"ok", "好的", "执行", "开始", "确认", "go", "yes", "start", "do it"}
CANCEL_KEYWORDS = {"取消", "不要", "算了", "abort", "cancel", "stop", "nevermind"}
SKIP_KEYWORDS = {"跳过", "skip", "ignore"}


def _is_confirm(text: str) -> bool:
    t = text.strip().lower()
    return any(k in t for k in CONFIRM_KEYWORDS) or re.match(r"^(ok|go|yes|do)\s*$", t)


def _is_cancel(text: str) -> bool:
    t = text.strip().lower()
    return any(k in t for k in CANCEL_KEYWORDS)


def _is_skip(text: str) -> bool:
    t = text.strip().lower()
    return any(k in t for k in SKIP_KEYWORDS)


def _parse_step_modification(text: str) -> tuple[int | None, str]:
    """解析 '修改步骤N: xxx' 或 '步骤 N xxx' 格式"""
    patterns = [
        r"修改步骤\s*(\d+)\s*[:：]\s*(.+)",
        r"步骤\s*(\d+)\s*[:：]\s*(.+)",
        r"step\s*(\d+)\s*[:：]\s*(.+)",
        r"modify step\s*(\d+)\s*[:：]\s*(.+)",
    ]
    for pattern in patterns:
        m = re.match(pattern, text.strip(), re.IGNORECASE)
        if m:
            return int(m.group(1)), m.group(2).strip()
    return None, ""


# ─── Command ─────────────────────────────────────────────────────────────────

class PlanCommand(Command):
    name = "plan"
    description = "对复杂任务生成执行计划（分解步骤 + 风险分析 + 多方案比较）"
    patterns = [
        ("/plan",),
        ("/plan", "<task_description>"),
        # 确认相关
        ("/plan", "confirm"),
        ("/plan", "cancel"),
        ("/plan", "list"),
        ("/plan", "show", "<plan_id>"),
        ("/plan", "modify", "<step_description>"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._logger = logger.bind(name="PlanCommand")
        self._planner: Planner | None = None
        self._current_plan: Plan | None = None
        self._awaiting_confirm: bool = False

    @property
    def planner(self) -> Planner:
        if self._planner is None:
            self._planner = Planner()
        return self._planner

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or ""
        raw = args.get("<task_description>") or ""
        raw_step = args.get("<step_description>") or ""

        # 0. 如果有待确认计划，且输入是确认相关词，优先处理确认
        if self._current_plan:
            raw_lower = raw.strip().lower()
            if _is_confirm(raw) or _is_cancel(raw) or _is_skip(raw):
                return await self._handle_confirmation(args, raw)
            if sub == "confirm" or sub == "cancel":
                return await self._handle_confirmation(args, raw)
            # 步骤修改
            step_idx, _ = _parse_step_modification(raw)
            if step_idx:
                return await self._handle_confirmation(args, raw)

        # 1. 列表命令
        if sub == "list":
            return await self._list(args)

        # 2. 查看指定计划
        if sub == "show":
            return await self._show(args)

        # 3. 取消
        if sub == "cancel" or _is_cancel(raw):
            return await self._cancel(args)

        # 4. 修改步骤
        if sub == "modify" or raw_step:
            return await self._modify(args, raw_step or raw)

        # 5. 新建计划（主流程）
        if raw.strip():
            return await self._new_plan(args, raw)

        # 6. 无参数无计划：显示帮助
        return CommandResult(content=self._usage())

    # ─── /plan <task> — 新建计划 ─────────────────────────────────────────────

    async def _new_plan(self, args: dict, task: str) -> CommandResult:
        self._logger.info("creating plan for: {t}", t=task[:80])

        try:
            # 获取项目上下文
            context = self._get_project_context()

            # 生成计划
            plan = self.planner.plan(task, context=context)

            # 格式化输出
            analysis = RiskAnalyzer().analyze([s.to_dict() for s in plan.steps])
            markdown = self.planner.format(plan, analysis)

            self._current_plan = plan
            self._awaiting_confirm = True

            return CommandResult(
                content=markdown,
                metadata={"plan_id": plan.id, "awaiting_confirm": True},
            )

        except Exception as exc:
            self._logger.error("plan creation failed: {e}", e=exc)
            return CommandResult(
                content=f"[plan] 计划生成失败：{exc}\n\n请尝试用更简单的方式描述任务。",
                success=False,
            )

    # ─── /plan confirm — 确认执行 ───────────────────────────────────────────

    async def _handle_confirmation(self, args: dict, raw: str) -> CommandResult:
        if self._current_plan is None:
            return CommandResult(
                content="没有待确认的计划。请先使用 `/plan <任务描述>` 生成计划。",
                success=False,
            )

        text = raw.strip() or args.get("_subcommand") or ""

        if _is_cancel(text):
            return await self._cancel(args)

        if _is_skip(text):
            self._current_plan = None
            self._awaiting_confirm = False
            return CommandResult(
                content="好的，已跳过计划。直接用自然语言继续对话。",
                handled=False,  # 继续发给 LLM
            )

        step_idx, new_desc = _parse_step_modification(text)
        if step_idx:
            return await self._modify_step(step_idx, new_desc)

        if _is_confirm(text) or text == "":
            return await self._confirm()

        # 不是确认词，也不是修改 → 继续发给 LLM 处理
        return CommandResult(content="", handled=False)

    async def _confirm(self) -> CommandResult:
        plan = self.planner.confirm(self._current_plan.id)
        if not plan:
            return CommandResult(content="计划确认失败。", success=False)

        self._logger.info("plan confirmed: {id}", id=plan.id)

        lines = [
            "✅ **计划已确认！**\n",
            f"计划 `{plan.id}` 开始执行。\n",
            "我将按以下顺序执行：",
        ]
        for step in plan.steps:
            lines.append(f"  {step.index}. {step.description}")

        lines.append("")
        lines.append("开始执行第一步...")

        self._awaiting_confirm = False
        # 返回 handled=False，让 SessionProcessor 继续用 LLM 执行
        return CommandResult(
            content="\n".join(lines),
            metadata={"plan_id": plan.id, "confirmed": True},
            handled=False,
        )

    async def _cancel(self, args: dict) -> CommandResult:
        if self._current_plan:
            plan = self.planner.cancel(self._current_plan.id)
            self._current_plan = None
            self._awaiting_confirm = False
            if plan:
                return CommandResult(content=f"已取消计划 `{plan.id}`。")
        return CommandResult(content="没有正在进行的计划。")

    async def _modify_step(self, step_idx: int, new_desc: str) -> CommandResult:
        if not self._current_plan:
            return CommandResult(content="没有正在进行的计划。", success=False)

        plan = self.planner.modify_step(self._current_plan.id, step_idx, new_desc)
        if not plan:
            return CommandResult(content=f"修改失败：步骤 {step_idx} 不存在。", success=False)

        analysis = RiskAnalyzer().analyze([s.to_dict() for s in plan.steps])
        markdown = self.planner.format(plan, analysis)
        self._current_plan = plan

        return CommandResult(
            content=markdown,
            metadata={"plan_id": plan.id, "awaiting_confirm": True},
        )

    # ─── /plan list ────────────────────────────────────────────────────────

    async def _list(self, args: dict) -> CommandResult:
        plans = self.planner.list_plans()
        if not plans:
            content = "暂无保存的计划。\n\n使用 `/plan <任务>` 开始一个新计划。"
        else:
            lines = [f"**已保存的计划**: {len(plans)} 个\n"]
            status_icon = {
                "draft": "📝",
                "proposed": "📋",
                "confirmed": "✅",
                "in_progress": "🔄",
                "completed": "🎉",
                "cancelled": "❌",
                "failed": "❌",
            }
            for p in plans[:10]:
                icon = status_icon.get(p.status, "📋")
                lines.append(
                    f"{icon} `{p.id}` — {p.task[:40]}"
                    + (f"... (步骤 {len(p.steps)})" if len(p.task) > 40 else f" (步骤 {len(p.steps)})")
                )
            if len(plans) > 10:
                lines.append(f"\n... 还有 {len(plans) - 10} 个旧计划")
        return CommandResult(content="\n".join(lines))

    # ─── /plan show <id> ───────────────────────────────────────────────────

    async def _show(self, args: dict) -> CommandResult:
        plan_id = args.get("<plan_id>", "").strip()
        if not plan_id:
            return CommandResult(content="用法：`/plan show <plan_id>`", success=False)

        plan = self.planner.get_plan(plan_id)
        if not plan:
            return CommandResult(content=f"未找到计划：`{plan_id}`", success=False)

        analysis = RiskAnalyzer().analyze([s.to_dict() for s in plan.steps])
        markdown = self.planner.format(plan, analysis)
        self._current_plan = plan
        self._awaiting_confirm = plan.status == "proposed"

        return CommandResult(content=markdown)

    async def _modify(self, args: dict, raw: str) -> CommandResult:
        """处理 /plan modify <描述>"""
        # 尝试从原始文本中提取步骤号和新描述
        step_idx, new_desc = _parse_step_modification(raw)
        if not step_idx:
            return CommandResult(
                content="用法：`/plan modify 步骤N: <新描述>`\n例如：`/plan modify 步骤2: 先分析代码结构`",
                success=False,
            )
        return await self._modify_step(step_idx, new_desc)

    # ─── 工具 ─────────────────────────────────────────────────────────────

    def _get_project_context(self) -> str:
        """获取项目上下文"""
        try:
            from ..memory import MemoryManager
            from pathlib import Path

            mm = MemoryManager()
            mode = mm.detect_mode(Path.cwd())

            if mode.mode == "project" and mode.project_root:
                # 项目模式：读取项目信息
                parts = [f"项目目录: {mode.project_root}"]

                # 读取项目类型
                pyproject = mode.project_root / "pyproject.toml"
                if pyproject.exists():
                    parts.append("Python 项目 (pyproject.toml)")

                package_json = mode.project_root / "package.json"
                if package_json.exists():
                    parts.append("Node.js 项目 (package.json)")

                # 读取 .git 目录
                git_dir = mode.project_root / ".git"
                if git_dir.exists():
                    parts.append("Git 仓库")

                return "\n".join(parts)
        except Exception:
            pass
        return ""

    # ─── 帮助 ─────────────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/plan** — 任务规划命令

## 用法
```
/plan <任务描述>              — 生成执行计划
/plan confirm                 — 确认当前计划并开始执行
/plan list                    — 列出已保存的计划
/plan show <plan_id>          — 查看指定计划
/plan modify 步骤N: <新描述>   — 修改某个步骤
/plan cancel                  — 取消当前计划
```

## 计划内容
- **步骤分解**: 任务 → 可执行的原子步骤
- **风险分析**: 每步和整体风险等级
- **执行流程图**: Mermaid 格式展示步骤依赖
- **替代方案**: 备选实现路径

## 确认后
输入 `ok` / `好的` / `执行` 开始按计划执行。
输入 `修改步骤N: <描述>` 修改后继续。
输入 `取消` 放弃计划。

## 示例
```
/plan 重构 auth 模块为插件化架构
/plan 帮我写一个用户登录 API
/plan 优化数据库查询性能
```
"""
