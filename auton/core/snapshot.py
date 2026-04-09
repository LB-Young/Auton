"""Auton Core — 快照与 Patch 系统

每步执行前后记录快照，产出 patch 文件清单。
工程价值：可解释（知道改了什么文件）、可审计、可回放、可重试。
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class PatchEntry:
    """单个文件改动"""
    file_path: str
    patch_type: str  # "edit" | "write" | "delete"
    before_hash: str | None  # None = 新建文件
    after_hash: str | None    # None = 删除文件
    diff: str | None = None   # 可选：diff 内容


@dataclass
class Snapshot:
    """一次快照：记录 step 的所有文件改动"""
    step_id: str
    session_id: str
    files_changed: list[str] = field(default_factory=list)
    patches: list[PatchEntry] = field(default_factory=list)
    summary: str = ""
    tool_calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "session_id": self.session_id,
            "files_changed": self.files_changed,
            "patches": [
                {
                    "file_path": p.file_path,
                    "patch_type": p.patch_type,
                    "before_hash": p.before_hash,
                    "after_hash": p.after_hash,
                    "diff": p.diff,
                }
                for p in self.patches
            ],
            "summary": self.summary,
            "tool_calls": self.tool_calls,
        }


class SnapshotManager:
    """快照管理器：记录所有步骤的文件改动"""

    def __init__(self, session_id: str, output_dir: Path) -> None:
        self.session_id = session_id
        self.output_dir = Path(output_dir) / "snapshots"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._snapshots: list[Snapshot] = []
        self._logger = logger.bind(name="SnapshotManager")

    def record_step(
        self,
        step_id: str,
        *,
        summary: str = "",
        tool_calls: list[dict] | None = None,
        files_changed: list[str] | None = None,
        patches: list[PatchEntry] | None = None,
    ) -> Snapshot:
        """记录一个 step 的快照"""
        snap = Snapshot(
            step_id=step_id,
            session_id=self.session_id,
            summary=summary,
            tool_calls=tool_calls or [],
            files_changed=files_changed or [],
            patches=patches or [],
        )
        self._snapshots.append(snap)
        self._save_snapshot(snap)
        self._logger.info(
            "快照记录 step={step} files={count}",
            step=step_id,
            count=len(snap.files_changed),
        )
        return snap

    def _save_snapshot(self, snap: Snapshot) -> None:
        """将快照追加写入 JSONL 文件"""
        path = self.output_dir / f"{self.session_id}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snap.to_dict(), ensure_ascii=False) + "\n")

    def get_all_snapshots(self) -> list[Snapshot]:
        """读取所有快照"""
        path = self.output_dir / f"{self.session_id}.jsonl"
        if not path.exists():
            return []
        snapshots = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    snapshots.append(Snapshot(**d))
        return snapshots

    def get_patch_for_file(self, file_path: str) -> list[PatchEntry]:
        """查找某个文件的所有 patch（按时间顺序）"""
        entries = []
        for snap in self._snapshots:
            for patch in snap.patches:
                if patch.file_path == file_path:
                    entries.append(patch)
        return entries


def compute_file_hash(content: str) -> str:
    """计算文件内容 MD5"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()  # nosec B324 — not for crypto
