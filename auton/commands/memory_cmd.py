"""Memory Command — /memory (M7 Long-term Memory)"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..memory import (
    MemoryEntry,
    MemoryManager,
    MemoryMode,
    MemoryType,
)
from .base import Command, CommandResult


def _get_mm_and_mode() -> tuple[MemoryManager, MemoryMode]:
    """获取 MemoryManager 实例和当前模式"""
    from ..core.config import get_config

    config = get_config()
    mm = MemoryManager(storage_dir=config.memory.storage_dir)
    mode = mm.detect_mode()
    return mm, mode


class MemoryCommand(Command):
    """记忆管理命令（M7 — Long-term Memory）"""

    name = "memory"
    description = "查看和管理记忆（list/get/edit/delete/gc/search/reindex）"
    patterns = [
        ("/memory",),
        ("/memory", "list"),
        ("/memory", "search", "<query>"),
        ("/memory", "get", "<id>"),
        ("/memory", "edit", "<id>"),
        ("/memory", "delete", "<id>"),
        ("/memory", "gc"),
        ("/memory", "reindex"),
        ("/memory", "stats"),
        ("/memory", "forget", "<id>"),
    ]

    async def handle(self, args: dict[str, Any]) -> CommandResult:
        sub = args.get("_subcommand") or "list"

        handler = {
            "list": self._list,
            "get": self._get,
            "edit": self._edit,
            "delete": self._delete,
            "gc": self._gc,
            "search": self._search,
            "reindex": self._reindex,
            "stats": self._stats,
            "forget": self._forget,
        }.get(sub)

        if handler:
            return await handler(args)
        return CommandResult(content=self._usage())

    # ─── /memory list ─────────────────────────────────────────────────

    async def _list(self, _args: dict) -> CommandResult:
        """列出当前模式下所有记忆条目"""
        mm, mode = _get_mm_and_mode()
        entries = mm.list_memory_entries(mode)

        if not entries:
            content = (
                f"**当前模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}\n\n"
                "暂无记忆条目。\n\n"
                "提示：记忆会在会话结束时自动蒸馏沉淀，"
                "或可通过 `/memory gc` 手动触发。"
            )
        else:
            lines = [
                f"**当前模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}",
                f"**记忆条目**: {len(entries)} 个\n",
            ]
            for entry in entries:
                type_label = entry.type.label()
                lines.append(f"### [{type_label}] {entry.name}")
                lines.append(f"{entry.description}")
                src = entry.source_file.name if entry.source_file else "?"
                lines.append(f"文件：`{src}` | 标签：{', '.join(entry.tags) or '无'}")
                lines.append("")

            content = "\n".join(lines)

        return CommandResult(content=content)

    # ─── /memory get <id> ─────────────────────────────────────────────

    async def _get(self, args: dict) -> CommandResult:
        """查看单条记忆详情"""
        mm, mode = _get_mm_and_mode()
        entries = mm.list_memory_entries(mode)

        identifier = args.get("<id>", "").strip()
        if not identifier:
            return CommandResult(content="用法：`/memory get <文件名>`", success=False)

        found: MemoryEntry | None = None
        for entry in entries:
            path = entry.source_file
            if path and (path.name == identifier or entry.name == identifier):
                found = entry
                break

        if not found:
            return CommandResult(content=f"未找到记忆：{identifier}", success=False)

        content = [
            f"# {found.name}",
            f"**类型**: {found.type.label()}",
            f"**标签**: {', '.join(found.tags) or '无'}",
            f"**描述**: {found.description}",
            f"**来源**: {found.source_session_id or found.source_file or '?'}",
            f"**创建**: {found.created_at.strftime('%Y-%m-%d %H:%M')}",
            f"**更新**: {found.updated_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            found.content,
        ]
        return CommandResult(content="\n".join(content))

    # ─── /memory edit <id> ─────────────────────────────────────────────

    async def _edit(self, args: dict) -> CommandResult:
        """编辑记忆条目（返回文件路径，用户自行编辑）"""
        mm, mode = _get_mm_and_mode()
        entries = mm.list_memory_entries(mode)

        identifier = args.get("<id>", "").strip()
        if not identifier:
            return CommandResult(content="用法：`/memory edit <文件名>`", success=False)

        found: MemoryEntry | None = None
        for entry in entries:
            path = entry.source_file
            if path and (path.name == identifier or entry.name == identifier):
                found = entry
                break

        if not found:
            return CommandResult(content=f"未找到记忆：{identifier}", success=False)

        path = found.source_file
        if not path:
            return CommandResult(content="无法定位记忆文件路径。", success=False)

        # 更新 updated_at 并写回
        from datetime import datetime

        try:
            text = path.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                fm = parts[1].rstrip()
                # 更新 updated_at
                new_fm_lines = []
                updated = False
                for line in fm.splitlines():
                    if line.strip().startswith("updated_at:"):
                        new_fm_lines.append(f"updated_at: {datetime.now().isoformat()}")
                        updated = True
                    else:
                        new_fm_lines.append(line)
                if not updated:
                    new_fm_lines.append(f"updated_at: {datetime.now().isoformat()}")
                new_fm = "\n".join(new_fm_lines)
                new_text = "---" + new_fm + "\n---\n" + parts[2]
                path.write_text(new_text, encoding="utf-8")
        except Exception as exc:
            return CommandResult(content=f"写入失败：{exc}", success=False)

        content = (
            f"## 编辑记忆\n\n"
            f"**文件**: `{path}`\n\n"
            "请直接编辑文件（支持 Markdown）。保存后记忆自动更新。\n\n"
            "**编辑建议**：\n"
            "- frontmatter `content` 行之后是正文内容\n"
            "- `updated_at` 已自动更新\n"
            "- `description` 用于检索，请保持简短"
        )
        return CommandResult(content=content)

    # ─── /memory delete <id> ─────────────────────────────────────────

    async def _delete(self, args: dict) -> CommandResult:
        """安全删除记忆（软删除，过 7 天后物理删除）"""
        mm, mode = _get_mm_and_mode()
        entries = mm.list_memory_entries(mode)

        identifier = args.get("<id>", "").strip()
        if not identifier:
            return CommandResult(content="用法：`/memory delete <文件名>`", success=False)

        found: MemoryEntry | None = None
        for entry in entries:
            path = entry.source_file
            if path and (path.name == identifier or entry.name == identifier):
                found = entry
                break

        if not found:
            return CommandResult(content=f"未找到记忆：{identifier}", success=False)

        path = found.source_file
        if not path or not path.exists():
            return CommandResult(content="记忆文件不存在。", success=False)

        # 检查是否内置/重要类型
        if found.type in (MemoryType.USER,):
            return CommandResult(
                content=f"**{found.type.label()}** 类型不可删除（用户身份信息）。\n"
                f"如需修改请用 `/memory edit {identifier}`。",
                success=False,
            )

        # 软删除：写入 deleted 标记
        try:
            text = path.read_text(encoding="utf-8")
            from datetime import datetime

            if text.startswith("---"):
                parts = text.split("---", 2)
                fm = parts[1].rstrip()
                new_fm = fm + f"\ndeleted: true\ndeleted_at: {datetime.now().isoformat()}\n"
                new_text = "---" + new_fm + "---" + parts[2]
            else:
                new_text = f"---\ndeleted: true\ndeleted_at: {datetime.now().isoformat()}\n---\n\n" + text

            path.write_text(new_text, encoding="utf-8")
        except Exception as exc:
            return CommandResult(content=f"删除失败：{exc}", success=False)

        content = (
            f"## 记忆已标记为删除\n\n"
            f"**文件**: `{path.name}`\n\n"
            f"记忆已进入软删除状态，将在 7 天后自动物理删除。"
            f"如需恢复，请在 7 天内手动移除 frontmatter 中的 `deleted: true` 行。"
        )
        return CommandResult(content=content)

    # ─── /memory gc ──────────────────────────────────────────────────

    async def _gc(self, _args: dict) -> CommandResult:
        """触发遗忘机制：蒸馏 + 遗忘 GC"""
        mm, mode = _get_mm_and_mode()

        from datetime import date, timedelta

        today = date.today()
        yesterday = today - timedelta(days=1)

        # 1. 蒸馏
        new_entries = mm.trigger_daily_distillation(yesterday)

        # 2. 遗忘 GC（干跑）
        to_forget = mm.run_forgetting_gc(mode=mode, dry_run=True)

        # 3. 实际执行遗忘
        deleted = mm.run_forgetting_gc(mode=mode, dry_run=False)

        stats = mm.get_memory_stats(mode=mode)

        content = (
            "## 记忆 GC 完成\n\n"
            f"**模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}\n"
            f"**蒸馏日期**: {yesterday.isoformat()}\n"
            f"**新增 MEMORY.md 条目**: {new_entries} 个\n"
            f"**遗忘条目数**: {len(deleted)} 个\n\n"
            f"**记忆统计**: {stats['total_entries']} 条有效条目\n"
            f"**遗忘池**: {stats['forgetting'].get('over_limit', 0)} 条超过容量上限\n\n"
            "### 遗忘策略说明\n"
            "| 维度 | 说明 |\n"
            "|------|------|\n"
            "| 评分公式 | relevance × decay(type_weight) |\n"
            "| 遗忘阈值 | score < 0.1 |\n"
            "| 容量上限 | > 200 条时强制遗忘 |\n"
            "| 删除方式 | 先软删除（marked deleted），7 天后物理删除 |\n"
            "| 半衰期 | 90 天 |\n"
        )
        return CommandResult(content=content)

    # ─── /memory search <query> ───────────────────────────────────────

    async def _search(self, args: dict) -> CommandResult:
        """搜索记忆（四层检索）"""
        mm, mode = _get_mm_and_mode()
        query = args.get("<query>", "").strip()

        if not query:
            return CommandResult(content="用法：`/memory search <关键词>`", success=False)

        results = mm.retrieve(query, mode, top_k=10)

        if not results:
            content = (
                f"**搜索**: {query}\n\n"
                f"**模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}\n\n"
                "未找到相关记忆。"
            )
        else:
            lines = [
                f"**搜索**: {query}",
                f"**模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}",
                f"**结果**: {len(results)} 条\n",
            ]
            for i, r in enumerate(results, start=1):
                lines.append(f"### 结果 {i}")
                lines.append(f"**来源**: `{r.source}`")
                if r.session_id:
                    lines.append(f"**Session**: `{r.session_id}`")
                lines.append(r.content[:200])
                if len(r.content) > 200:
                    lines.append("...")
                lines.append("")

            content = "\n".join(lines)

        return CommandResult(content=content)

    # ─── /memory reindex ─────────────────────────────────────────────

    async def _reindex(self, _args: dict) -> CommandResult:
        """重建 L0 长期记忆索引（从 MEMORY.md / SUMMARY.md 分块写入 chunks.jsonl）"""
        mm, mode = _get_mm_and_mode()
        count = mm.rebuild_long_term_index(mode=mode)
        content = (
            "## L0 索引重建完成\n\n"
            f"**模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}\n"
            f"**生成 chunks**: {count} 个\n\n"
            "L0 层使用 BM25 关键词检索 + 时间衰减排序。"
        )
        return CommandResult(content=content)

    # ─── /memory stats ────────────────────────────────────────────────

    async def _stats(self, _args: dict) -> CommandResult:
        """显示记忆统计"""
        mm, mode = _get_mm_and_mode()
        stats = mm.get_memory_stats(mode=mode)

        fg = stats["forgetting"]
        lines = [
            "## 记忆统计\n",
            f"**模式**: {'项目模式' if mode.mode == 'project' else '全局模式'}",
            f"**目录**: `{stats['storage_dir']}`",
            f"**有效条目**: {stats['total_entries']} 个",
            "",
            "### 遗忘统计",
            f"- 总条目: {fg.get('total', 0)}",
            f"- 超过上限: {fg.get('over_limit', 0)} (> 200 条)",
            f"- 最老条目: {fg.get('oldest_days', 0):.0f} 天",
            f"- 平均评分: {fg.get('avg_score', 0):.3f}",
            f"- 最低评分: {fg.get('lowest_score', 0):.3f}",
            "",
            "### 按类型",
        ]
        for t, n in fg.get("by_type", {}).items():
            lines.append(f"- {t}: {n} 条")

        return CommandResult(content="\n".join(lines))

    # ─── /memory forget <id> ─────────────────────────────────────────

    async def _forget(self, args: dict) -> CommandResult:
        """立即遗忘（标记为软删除）"""
        return await self._delete(args)

    # ─── 使用说明 ─────────────────────────────────────────────────────

    def _usage(self) -> str:
        return """**/memory** — 记忆管理命令

## 用法
```
/memory list              — 列出所有记忆条目
/memory search <关键词>    — 四层检索（BM25 关键词 + 时间衰减）
/memory get <文件名>       — 查看记忆详情
/memory edit <文件名>      — 返回文件路径，手动编辑
/memory delete <文件名>    — 软删除（7 天后物理删除）
/emory gc                  — 触发遗忘机制（蒸馏 + 遗忘）
/memory reindex           — 重建 L0 BM25 索引
/memory stats             — 显示记忆统计
```

## 检索分层
```
L0: chunks.jsonl  — BM25 关键词 + 时间衰减
L1: MEMORY.md     — 顶层索引
L2: SUMMARY.md    — 分段摘要
L3: jsonl         — 原始事件流
```

## 遗忘策略
| 参数 | 值 |
|------|------|
| 遗忘阈值 | score < 0.1 |
| 容量上限 | > 200 条强制遗忘 |
| 软删除保留 | 7 天 |
| 半衰期 | 90 天 |
"""
