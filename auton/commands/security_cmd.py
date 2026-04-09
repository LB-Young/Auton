"""Commands — /security 命令

用法：
  /security audit [since] [until]   — 查看审计日志
  /security summary [since] [until]  — 审计汇总报告
  /security clear <before>           — 清理指定日期之前的记录
  /security mode                      — 显示当前权限模式
  /security keys                      — 查看已配置密钥信息
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from .base import Command, CommandResult


class SecurityCommand(Command):
    name = "security"
    description = "查看和管理安全设置、审计日志、密钥"

    def __init__(self) -> None:
        self._parser = argparse.ArgumentParser(prog="/security", exit_on_error=False)
        sub = self._parser.add_subparsers(dest="subcommand", required=True)

        # audit
        p_audit = sub.add_parser("audit", help="查看审计日志")
        p_audit.add_argument("--since", type=str, default=None, help="起始时间 (YYYY-MM-DD)")
        p_audit.add_argument("--until", type=str, default=None, help="结束时间 (YYYY-MM-DD)")
        p_audit.add_argument("--session", type=str, default=None, help="Session ID 过滤")
        p_audit.add_argument("--category", type=str, default=None, help="分类过滤 (read_only/write/destructive)")
        p_audit.add_argument("--limit", type=int, default=50, help="最多显示条数")

        # summary
        p_sum = sub.add_parser("summary", help="生成审计汇总报告")
        p_sum.add_argument("--since", type=str, default=None)
        p_sum.add_argument("--until", type=str, default=None)

        # clear
        p_clear = sub.add_parser("clear", help="清理审计日志")
        p_clear.add_argument("before", type=str, help="此日期之前的记录将被删除 (YYYY-MM-DD)")

        # mode
        sub.add_parser("mode", help="显示当前权限模式")

        # keys
        sub.add_parser("keys", help="查看已配置的密钥（不含实际值）")

    async def handle(self, ctx: dict) -> CommandResult:
        args = ctx.get("_args", "")
        try:
            parsed = self._parser.parse_args(args.split()) if args.strip() else argparse.Namespace(subcommand="mode")
        except SystemExit:
            return CommandResult(content="用法：/security audit | summary | clear | mode | keys", success=False)

        match parsed.subcommand:
            case "audit":
                return await self._audit(parsed)
            case "summary":
                return await self._summary(parsed)
            case "clear":
                return await self._clear(parsed)
            case "mode":
                return await self._mode()
            case "keys":
                return await self._keys()
            case _:
                return CommandResult(content="未知子命令", success=False)

    # ─── 子命令实现 ─────────────────────────────────────────────────

    async def _audit(self, args: argparse.Namespace) -> CommandResult:
        from ..security.audit import AuditLog

        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None

        log = AuditLog()
        entries = log.read_entries(
            since=since,
            until=until,
            session_id=args.session,
            category=args.category,
            limit=args.limit,
        )

        if not entries:
            return CommandResult(content="暂无审计记录。")

        lines = ["## 审计记录\n"]
        for e in entries:
            status = "✅" if e.allowed else "❌"
            sandbox = "[sandbox]" if e.sandboxed else ""
            ts = datetime.fromtimestamp(e.timestamp).strftime("%m-%d %H:%M:%S")
            cmd_preview = e.command[:60] + ("..." if len(e.command) > 60 else "")
            lines.append(
                f"{status} `{ts}` {e.category:12s} {sandbox} `{cmd_preview}`"
            )

        lines.append(f"\n共 {len(entries)} 条记录")
        return CommandResult(content="\n".join(lines))

    async def _summary(self, args: argparse.Namespace) -> CommandResult:
        from ..security.audit import AuditLog

        since = datetime.fromisoformat(args.since) if args.since else None
        until = datetime.fromisoformat(args.until) if args.until else None

        log = AuditLog()
        report = log.summarize(since=since, until=until)
        return CommandResult(content=report)

    async def _clear(self, args: argparse.Namespace) -> CommandResult:
        from ..security.audit import AuditLog

        try:
            before = datetime.fromisoformat(args.before)
        except ValueError:
            return CommandResult(content=f"日期格式错误，请使用 YYYY-MM-DD：{args.before}", success=False)

        log = AuditLog()
        n = log.clear_before(before)
        return CommandResult(content=f"已删除 {n} 条 {args.before} 之前的审计记录。")

    async def _mode(self) -> CommandResult:
        from ..security.permission import PermissionMode

        lines = ["## 当前权限模式\n"]
        for mode in PermissionMode:
            lines.append(f"- `{mode.value}`")
        lines.append("")
        lines.append("| 模式 | 行为 |")
        lines.append("|------|------|")
        lines.append("| default | 交互式确认（每次写操作询问） |")
        lines.append("| auto | ML 分类器自动审批低风险操作 |")
        lines.append("| bypass | 跳过所有权限检查（危险） |")
        lines.append("| yolo | 全部自动拒绝（只读） |")
        return CommandResult(content="\n".join(lines))

    async def _keys(self) -> CommandResult:
        from ..security.key_manager import KeyManager

        km = KeyManager.get_instance()
        known_keys = ["MINIMAX_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
        lines = ["## 密钥状态\n"]
        lines.append("| 密钥名 | 来源 | 状态 |")
        lines.append("|--------|------|------|")
        for name in known_keys:
            info = km.info(name)
            status = "✅ 已配置" if info.present else "❌ 未配置"
            lines.append(f"| `{name}` | {info.source} | {status} |")
        return CommandResult(content="\n".join(lines))
