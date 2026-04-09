"""Security — 操作审计日志

所有工具调用必须写入审计日志，无论权限模式为何。
审计日志格式：JSONL，每行一个事件。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from loguru import logger


@dataclass
class AuditEntry:
    """单条审计记录"""

    timestamp: float
    session_id: str
    tool: str
    command: str  # bash 命令内容 / 其他工具名
    category: str  # read_only / write / destructive
    allowed: bool  # 是否被放行
    sandboxed: bool
    returncode: int | None
    duration_ms: float
    result_preview: str
    platform: str
    permission_mode: str = "default"
    error: str | None = None


AUDIT_LOG_DIR = Path("~/.auton/logs").expanduser()
BASH_AUDIT_LOG = AUDIT_LOG_DIR / "commands.log"


class AuditLog:
    """审计日志管理器

    提供查询接口，支持：
      - 按时间范围过滤
      - 按 session 过滤
      - 按 category 过滤
      - 汇总统计
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or BASH_AUDIT_LOG
        self._logger = logger.bind(name="AuditLog")

    def ensure_dir(self) -> None:
        """确保日志目录存在"""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: AuditEntry) -> None:
        """追加一条审计记录"""
        import json

        self.ensure_dir()
        record = {
            "timestamp": entry.timestamp,
            "session_id": entry.session_id,
            "tool": entry.tool,
            "command": entry.command,
            "category": entry.category,
            "allowed": entry.allowed,
            "sandboxed": entry.sandboxed,
            "returncode": entry.returncode,
            "duration_ms": entry.duration_ms,
            "result_preview": entry.result_preview,
            "platform": entry.platform,
            "permission_mode": entry.permission_mode,
            "error": entry.error,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read_entries(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        session_id: str | None = None,
        category: str | None = None,
        allowed: bool | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """读取审计记录（支持过滤）

        Args:
            since: 最早时间
            until: 最晚时间
            session_id: 只看某个 session
            category: 过滤分类
            allowed: 过滤放行状态
            limit: 最多返回多少条
        """
        if not self.log_path.exists():
            return []

        entries: list[AuditEntry] = []
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = record.get("timestamp", 0)
                entry_time = datetime.fromtimestamp(ts)

                # 时间过滤
                if since and entry_time < since:
                    continue
                if until and entry_time > until:
                    continue

                # session 过滤
                if session_id and record.get("session_id") != session_id:
                    continue

                # 分类过滤
                if category and record.get("category") != category:
                    continue

                # 放行状态过滤
                if allowed is not None and record.get("allowed") != allowed:
                    continue

                entries.append(AuditEntry(
                    timestamp=ts,
                    session_id=record.get("session_id", ""),
                    tool=record.get("tool", "bash"),
                    command=record.get("command", ""),
                    category=record.get("category", "unknown"),
                    allowed=record.get("allowed", True),
                    sandboxed=record.get("sandboxed", False),
                    returncode=record.get("returncode"),
                    duration_ms=record.get("duration_ms", 0),
                    result_preview=record.get("result_preview", ""),
                    platform=record.get("platform", ""),
                    permission_mode=record.get("permission_mode", "default"),
                    error=record.get("error"),
                ))

                if len(entries) >= limit:
                    break

        # 按时间倒序
        entries.sort(key=lambda x: x.timestamp, reverse=True)
        return entries

    def summarize(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> str:
        """生成汇总报告"""
        entries = self.read_entries(since=since, until=until, limit=10000)

        if not entries:
            return "暂无审计记录。"

        total = len(entries)
        allowed_count = sum(1 for e in entries if e.allowed)
        denied_count = total - allowed_count
        sandboxed_count = sum(1 for e in entries if e.sandboxed)
        destructive_count = sum(1 for e in entries if e.category == "destructive")

        read_count = sum(1 for e in entries if e.category == "read_only")
        write_count = sum(1 for e in entries if e.category == "write")

        duration = sum(e.duration_ms for e in entries)
        avg_duration = duration / total if total > 0 else 0

        time_range = ""
        if entries:
            first = datetime.fromtimestamp(entries[-1].timestamp)
            last = datetime.fromtimestamp(entries[0].timestamp)
            time_range = f"从 {first.strftime('%Y-%m-%d %H:%M')} 到 {last.strftime('%Y-%m-%d %H:%M')}"

        lines = [
            f"## 审计日志汇总 {time_range}\n",
            f"**总操作数**: {total}",
            f"**放行**: {allowed_count} ({100*allowed_count/total:.1f}%)",
            f"**拒绝**: {denied_count} ({100*denied_count/total:.1f}%)",
            f"**沙箱执行**: {sandboxed_count}",
            "",
            "### 按分类",
            f"- 读操作（read_only）: {read_count}",
            f"- 写操作（write）: {write_count}",
            f"- 破坏性操作（destructive）: {destructive_count}",
            "",
            f"**平均耗时**: {avg_duration:.1f} ms",
        ]

        return "\n".join(lines)

    def recent(
        self,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[AuditEntry]:
        """读取最近的审计记录"""
        return self.read_entries(session_id=session_id, limit=limit)

    def clear_before(self, before: datetime) -> int:
        """删除指定时间之前的审计记录（保留最近 N 天）"""
        if not self.log_path.exists():
            return 0

        kept: list[str] = []
        removed = 0
        with open(self.log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    ts = record.get("timestamp", 0)
                    if datetime.fromtimestamp(ts) < before:
                        removed += 1
                        continue
                    kept.append(line)
                except json.JSONDecodeError:
                    pass

        # 重写文件
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.writelines(kept)

        self._logger.info("cleared {n} audit entries before {d}", n=removed, d=before)
        return removed
