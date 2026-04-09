"""Memory — 遗忘策略

基于相关性和时间衰减的自动遗忘机制。

遗忘触发条件：
  - 存储条目超过 MAX_ENTRIES 限制
  - 条目评分低于 DECAY_THRESHOLD

评分公式：
  score = relevance * decay(days_since_update) * type_weight

  - relevance: 访问频率 + 查询命中次数（从索引读取）
  - decay: 指数衰减，HALF_LIFE=90 天
  - type_weight: USER=1.5, PROJECT=1.2, FEEDBACK=1.0, REFERENCE=0.8

删除策略：
  1. 先标记为过期（soft delete）
  2. 超过 DELETE_GRACE_PERIOD 天后物理删除
  3. 每次 GC 最多删除 MAX_DELETE_PER_GC 条
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import MemoryType


# 遗忘参数
MAX_ENTRIES = 200          # 最大条目数（超过后触发遗忘）
HALF_LIFE_DAYS = 90         # 半衰期（天）
DECAY_THRESHOLD = 0.1       # 评分低于此值触发删除
DELETE_GRACE_PERIOD = 7     # 软删除后保留天数
MAX_DELETE_PER_GC = 20      # 每次 GC 最多删除条数

# 重要类型权重（越重要越难遗忘）
TYPE_WEIGHTS: dict[str, float] = {
    "user": 1.5,
    "feedback": 1.2,
    "project": 1.0,
    "reference": 0.8,
}


@dataclass
class MemoryScore:
    """记忆评分"""
    source_id: str       # 文件名
    memory_type: str     # 类型
    score: float         # 综合评分
    relevance: float     # 相关性（访问频率）
    decay: float         # 时间衰减
    days_since_update: float  # 距上次更新天数
    is_deleted: bool     # 是否已软删除


def compute_decay(created_at: float | datetime, half_life: float = HALF_LIFE_DAYS) -> float:
    """计算时间衰减因子：e^(-ln(2) * days / half_life)"""
    if isinstance(created_at, datetime):
        ts = created_at.timestamp()
    else:
        ts = created_at

    days = (time.time() - ts) / 86400
    if days < 0:
        days = 0
    return pow(0.5, days / half_life)


def score_memory(
    source_id: str,
    memory_type: str,
    updated_at: float,
    access_count: int = 0,
    query_hit_count: int = 0,
) -> MemoryScore:
    """计算单条记忆的遗忘评分"""
    decay = compute_decay(updated_at)
    relevance = min(1.0, (access_count * 0.1 + query_hit_count * 0.2) / 10.0)
    type_weight = TYPE_WEIGHTS.get(memory_type.lower(), 1.0)

    days = (time.time() - updated_at) / 86400
    score = relevance * decay * type_weight

    return MemoryScore(
        source_id=source_id,
        memory_type=memory_type,
        score=score,
        relevance=relevance,
        decay=decay,
        days_since_update=max(0, days),
        is_deleted=False,
    )


def score_all_memories(
    memory_dir: Path,
    updated_index: dict[str, float] | None = None,
) -> list[MemoryScore]:
    """对目录下所有记忆文件评分"""
    if not memory_dir.exists():
        return []

    # 读取访问索引
    access_index = _read_access_index(memory_dir)

    scores: list[MemoryScore] = []

    for path in memory_dir.glob("*.md"):
        if path.name in ("MEMORY.md", "SUMMARY.md", "index.jsonl"):
            continue
        if path.name.startswith("."):
            continue

        # 解析 frontmatter 获取类型
        mem_type, updated_ts = _parse_frontmatter(path)
        if mem_type is None:
            mem_type = "project"

        access_count = access_index.get(path.name, 0)
        query_hit = updated_index.get(path.name, 0) if updated_index else 0

        ms = score_memory(
            source_id=path.name,
            memory_type=mem_type,
            updated_at=updated_ts,
            access_count=access_count,
            query_hit_count=query_hit,
        )
        scores.append(ms)

    # 按评分排序（最低的排前面，最先被遗忘）
    scores.sort(key=lambda x: x.score)
    return scores


def _read_access_index(memory_dir: Path) -> dict[str, int]:
    """读取访问索引"""
    index_path = memory_dir / ".access_index.json"
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return {k: int(v) for k, v in data.items()}
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_frontmatter(path: Path) -> tuple[str | None, float]:
    """从 MD 文件解析 frontmatter 的 type 和 updated_at"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, 0.0

    if not text.startswith("---"):
        return None, path.stat().st_mtime

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, path.stat().st_mtime

    fm_text = parts[1]
    type_val = None
    date_val = None

    for line in fm_text.splitlines():
        line = line.strip()
        if line.startswith("type:"):
            type_val = line.split(":", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("updated_at:") or line.startswith("updated:"):
            date_val = line.split(":", 1)[1].strip()

    ts = path.stat().st_mtime
    if date_val:
        try:
            dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            ts = dt.timestamp()
        except ValueError:
            pass

    return type_val, ts


def run_gc(memory_dir: Path, dry_run: bool = False) -> list[str]:
    """运行遗忘 GC，返回被删除的文件名列表（dry_run 时只返回待删除列表）"""
    scores = score_all_memories(memory_dir)

    deleted: list[str] = []
    total = len(scores)

    # 1. 超过 MAX_ENTRIES → 强制删除最低评分条目
    if total > MAX_ENTRIES:
        excess = total - MAX_ENTRIES
        to_delete = scores[:excess]
        for ms in to_delete:
            if _soft_delete(memory_dir / ms.source_id, dry_run):
                deleted.append(ms.source_id)
            if len(deleted) >= MAX_DELETE_PER_GC:
                break

    # 2. 低于 DECAY_THRESHOLD 的条目
    for ms in scores:
        if ms.score < DECAY_THRESHOLD and ms.source_id not in deleted:
            if _soft_delete(memory_dir / ms.source_id, dry_run):
                deleted.append(ms.source_id)
            if len(deleted) >= MAX_DELETE_PER_GC:
                break

    return deleted


def _soft_delete(path: Path, dry_run: bool) -> bool:
    """软删除：将 deleted: true 写入 frontmatter"""
    if not path.exists():
        return False

    if dry_run:
        return True

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    # 检查是否已有 deleted 标记
    if re.search(r"^deleted:\s*(true|1|yes)", text, re.MULTILINE):
        # 已经是软删除状态 → 物理删除
        # 检查是否超过保留期
        m = re.search(r"deleted_at:\s*(.+?)(?:\n|$)", text)
        if m:
            try:
                deleted_at = datetime.fromisoformat(m.group(1).strip())
                if (datetime.now() - deleted_at).days >= DELETE_GRACE_PERIOD:
                    path.unlink()
                    return True
            except ValueError:
                pass
        # 未超过保留期或无 deleted_at → 跳过
        return False

    # 添加 deleted 标记
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = parts[1]
        new_fm = fm.rstrip() + f"\ndeleted: true\ndeleted_at: {datetime.now().isoformat()}\n"
        new_text = "---" + new_fm + "---" + parts[2]
    else:
        new_text = f'---\ndeleted: true\ndeleted_at: {datetime.now().isoformat()}\n---\n\n' + text

    path.write_text(new_text, encoding="utf-8")
    return True


def get_forgetting_stats(memory_dir: Path) -> dict:
    """获取遗忘统计信息"""
    scores = score_all_memories(memory_dir)
    if not scores:
        return {"total": 0, "by_type": {}, "oldest_days": 0, "avg_score": 0.0}

    by_type: dict[str, int] = {}
    for ms in scores:
        by_type[ms.memory_type] = by_type.get(ms.memory_type, 0) + 1

    return {
        "total": len(scores),
        "over_limit": max(0, len(scores) - MAX_ENTRIES),
        "by_type": by_type,
        "oldest_days": max(ms.days_since_update for ms in scores),
        "avg_score": sum(ms.score for ms in scores) / len(scores),
        "lowest_score": scores[0].score if scores else 0.0,
    }
