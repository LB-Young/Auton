"""Memory Types — 记忆类型定义"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Literal


class MemoryType(Enum):
    """记忆类型（与 Claude Code 格式兼容）"""

    USER = "user"  # 用户身份、偏好、沟通风格
    FEEDBACK = "feedback"  # 用户反馈与行为规则
    PROJECT = "project"  # 项目背景、关键决策、约束
    REFERENCE = "reference"  # 外部资源指针（链接、文档）

    def filename(self, slug: str = "") -> str:
        """生成标准文件名"""
        if slug:
            return f"{self.value}_{slug}.md"
        return f"{self.value}.md"

    def label(self) -> str:
        """人类可读的标签"""
        return {
            "user": "用户角色与偏好",
            "feedback": "行为规则与反馈",
            "project": "项目背景与决策",
            "reference": "外部引用与指针",
        }[self.value]


@dataclass
class MemoryEntry:
    """单条记忆条目（存入 MEMORY.md 或主题文件的结构化表示）"""

    type: MemoryType
    name: str
    description: str  # 一句话描述
    content: str  # 完整内容（Markdown）
    source_session_id: str | None = None  # 来源 session（可选）
    source_file: Path | None = None  # 来源文件路径
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """序列化为带 frontmatter 的 Markdown"""
        lines = [
            "---",
            f"name: {self.name}",
            f"description: {self.description}",
            f"type: {self.type.value}",
            f"tags: [{', '.join(self.tags)}]",
            f"created_at: {self.created_at.isoformat()}",
            f"updated_at: {self.updated_at.isoformat()}",
            "---",
            "",
            self.content,
        ]
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str, path: Path) -> "MemoryEntry":
        """从 Markdown 解析 MemoryEntry"""
        import re

        frontmatter: dict[str, str] = {}
        content_lines: list[str] = []
        in_frontmatter = False

        for line in text.splitlines():
            if line.strip() == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    in_frontmatter = False
                    continue
            if in_frontmatter:
                if ":" in line:
                    key, _, val = line.partition(":")
                    frontmatter[key.strip()] = val.strip().strip('"').strip("'")
            else:
                content_lines.append(line)

        content = "\n".join(content_lines).strip()
        return cls(
            type=MemoryType(frontmatter.get("type", "project")),
            name=frontmatter.get("name", path.stem),
            description=frontmatter.get("description", ""),
            content=content,
            tags=_parse_tags(frontmatter.get("tags", "")),
            source_file=path,
            created_at=datetime.fromisoformat(frontmatter["created_at"])
            if "created_at" in frontmatter
            else datetime.now(),
            updated_at=datetime.fromisoformat(frontmatter["updated_at"])
            if "updated_at" in frontmatter
            else datetime.now(),
        )


def _parse_tags(tags_str: str) -> list[str]:
    """解析 tags 字符串为列表"""
    tags_str = tags_str.strip().strip("[]")
    if not tags_str:
        return []
    return [t.strip().strip("'").strip('"') for t in tags_str.split(",") if t.strip()]


@dataclass
class SummaryBlock:
    """SUMMARY.md 中的一条 block 摘要"""

    session_id: str  # jsonl 文件名（不含路径）
    block_index: int  # block 序号（从 1 开始）
    summary: str  # 该 block 的详细总结
    intent: str = ""  # 用户意图
    files: list[str] = field(default_factory=list)  # 涉及的文件/模块
    decisions: list[str] = field(default_factory=list)  # 关键决策/结论
    todos: list[str] = field(default_factory=list)  # 待跟进事项

    def to_line(self) -> str:
        """序列化为 SUMMARY.md 中的一行"""
        return f"- block_{self.block_index:03d}: {self.summary}"

    @classmethod
    def from_line(cls, session_id: str, line: str) -> "SummaryBlock | None":
        """从 SUMMARY.md 一行解析出 SummaryBlock"""
        import re

        m = re.match(r"- block_(\d+): (.*)", line.strip())
        if not m:
            return None
        return cls(session_id=session_id, block_index=int(m.group(1)), summary=m.group(2).strip())


@dataclass
class RetrievalResult:
    """检索结果"""

    content: str  # 检索到的内容
    source: str  # 来源：MEMORY.md / SUMMARY.md / jsonl
    session_id: str | None = None  # 来源 session
    block_index: int | None = None  # 来源 block（如果是 jsonl）
    score: float = 1.0  # 相似度分数
