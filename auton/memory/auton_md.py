"""AutonMD Manager — auton.md 三位置加载与合并

auton.md 存放跨项目通用用户偏好，可在三处出现（优先级从高到低）：
  ~/.auton/auton.md         （高）
  {项目根}/.auton/auton.md  （中）
  {auton源码}/.auton/auton.md （低）

加载规则：取并集，同键冲突时高优先级覆盖低优先级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger


@dataclass
class AutonMDEntry:
    """auton.md 中的一条条目"""

    section: str  # 节名称（对应 ## 标题）
    content: str  # 条目内容
    source: Path  # 来源文件路径
    lineno: int = 0  # 行号


class AutonMDManager:
    """auton.md 三位置加载器"""

    FILENAME = "auton.md"

    def __init__(self) -> None:
        self._logger = logger.bind(name="AutonMDManager")

    # ─── 三位置路径 ────────────────────────────────────────────────────

    def get_paths(self) -> dict[str, Path | None]:
        """返回三处 auton.md 路径

        Returns:
            {"high": Path|None, "medium": Path|None, "low": Path|None}
        """
        high = Path("~/.auton").expanduser() / self.FILENAME
        if not high.exists():
            high = None

        # medium: 项目根 .auton/auton.md
        from .project_memory import ProjectMemory

        project_root = ProjectMemory.find_project_root()
        medium = None
        if project_root:
            medium = project_root / ".auton" / self.FILENAME
            if not medium.exists():
                medium = None

        # low: 源码 .auton/auton.md
        import auton
        low = Path(auton.__file__).parent / ".auton" / self.FILENAME
        if not low.exists():
            low = None

        return {"high": high, "medium": medium, "low": low}

    # ─── 解析 ──────────────────────────────────────────────────────────

    def parse_file(self, path: Path) -> list[AutonMDEntry]:
        """解析单个 auton.md 文件，返回所有条目"""
        if path is None or not path.exists():
            return []

        entries: list[AutonMDEntry] = []
        lines = path.read_text(encoding="utf-8").splitlines()

        current_section = ""
        current_content_lines: list[str] = []
        current_lineno = 0

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("## "):
                # 保存前一个 section
                if current_section:
                    entries.append(
                        AutonMDEntry(
                            section=current_section,
                            content="\n".join(current_content_lines).strip(),
                            source=path,
                            lineno=current_lineno,
                        )
                    )
                current_section = stripped[3:].strip()
                current_content_lines = []
                current_lineno = i
            elif current_section:
                current_content_lines.append(line)

        # 最后一个 section
        if current_section:
            entries.append(
                AutonMDEntry(
                    section=current_section,
                    content="\n".join(current_content_lines).strip(),
                    source=path,
                    lineno=current_lineno,
                )
            )

        return entries

    # ─── 合并 ─────────────────────────────────────────────────────────

    def load_merged(self) -> dict[str, str]:
        """加载并合并三处 auton.md

        Returns:
            {section_name: merged_content}
            高优先级 section 覆盖低优先级
        """
        paths = self.get_paths()
        priority: list[tuple[str, Path | None]] = [
            ("high", paths["high"]),
            ("medium", paths["medium"]),
            ("low", paths["low"]),
        ]

        merged: dict[str, str] = {}  # section → content

        for level, path in priority:
            if path is None:
                continue
            for entry in self.parse_file(path):
                if entry.section not in merged:
                    # 新 section，直接加入
                    merged[entry.section] = entry.content
                # else: 已有 section，高优先级已覆盖，无需处理

        return merged

    def load_as_markdown(self) -> str:
        """加载合并后的 auton.md 为 Markdown 字符串（供注入 context）"""
        merged = self.load_merged()
        if not merged:
            return ""

        lines = [
            "# 用户偏好（跨项目通用）",
            "",
        ]
        for section, content in merged.items():
            lines.append(f"## {section}")
            lines.append("")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    # ─── 写入 ─────────────────────────────────────────────────────────

    def write_entry(
        self,
        section: str,
        content: str,
        level: Literal["high", "medium", "low"] = "high",
    ) -> Path:
        """向指定层级的 auton.md 追加/覆盖条目

        Args:
            section: 节名称
            content: 条目内容
            level: high ~/.auton / medium 项目 / low 源码
        """
        from .conflict_resolver import ConflictResolver

        if level == "high":
            path = Path("~/.auton").expanduser() / self.FILENAME
        elif level == "medium":
            from .project_memory import ProjectMemory

            project_root = ProjectMemory.find_project_root()
            if project_root is None:
                raise ValueError("No project found. Cannot write medium-level auton.md.")
            path = project_root / ".auton" / self.FILENAME
        else:
            import auton

            path = Path(auton.__file__).parent / ".auton" / self.FILENAME

        path.parent.mkdir(parents=True, exist_ok=True)

        # 冲突检测
        resolver = ConflictResolver()
        existing = self.parse_file(path) if path.exists() else []
        conflict = resolver.detect_conflict(section, content, existing)

        if conflict:
            # 追加冲突标记，不直接覆盖
            content = (
                f"{content}\n\n"
                f"<!-- conflict: {conflict.reason} -->\n"
                f"<!-- conflicting_source: {conflict.existing_source} -->"
            )

        # 写入
        if not path.exists():
            path.write_text("", encoding="utf-8")

        text = path.read_text(encoding="utf-8")

        # 检查 section 是否已存在
        import re

        section_pattern = re.compile(rf"^## {re.escape(section)}\s*$", re.MULTILINE)
        if section_pattern.search(text):
            # 替换已有 section
            # 找到 section 范围
            start = section_pattern.search(text)
            if start:
                start_pos = start.start()
                # 找下一个 ## 标题或文件末尾
                next_section = re.search(r"\n## ", text[start_pos + 1 :])
                if next_section:
                    end_pos = start_pos + 1 + next_section.start()
                else:
                    end_pos = len(text)
                text = text[:start_pos] + f"## {section}\n\n{content}\n" + text[end_pos:]
        else:
            # 追加新 section
            text = text.rstrip()
            text += f"\n## {section}\n\n{content}\n"

        path.write_text(text, encoding="utf-8")
        self._logger.info("written auton.md entry section={s} level={l}", s=section, l=level)
        return path


# 临时引用解决循环
from typing import Literal
