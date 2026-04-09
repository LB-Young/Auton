"""Skills — frontmatter parsing and schema validation.

SKILL.md uses YAML frontmatter with a well-defined schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml


class FrontmatterError(ValueError):
    """Invalid frontmatter"""


@dataclass
class SkillMetadata:
    """metadata.yaml section (optional, for extensibility)"""

    emoji: str = ""
    requires: "dict[str, list[str]]" = field(default_factory=dict)
    install: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SkillFrontmatter:
    """Parsed frontmatter of a SKILL.md file"""

    name: str  # 唯一标识，小写+连字符
    description: str  # 最重要字段：何时使用/何时不用
    disable_model_invocation: bool = False  # 是否禁止 LLM 自动调用
    user_invocable: bool = True  # 是否允许用户手动触发
    load_experiences: bool = False  # 是否自动加载 experiences/README.md
    metadata: SkillMetadata = field(default_factory=SkillMetadata)

    # 内部字段
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（用于写入）"""
        d = {
            "name": self.name,
            "description": self.description,
        }
        if self.disable_model_invocation:
            d["disable-model-invocation"] = True
        if not self.user_invocable:
            d["user-invocable"] = False
        if self.load_experiences:
            d["load-experiences"] = True
        if self.metadata.emoji or self.metadata.requires or self.metadata.install:
            meta: dict[str, Any] = {}
            if self.metadata.emoji:
                meta["emoji"] = self.metadata.emoji
            if self.metadata.requires:
                meta["requires"] = self.metadata.requires
            if self.metadata.install:
                meta["install"] = self.metadata.install
            d["metadata"] = {"openclaw": meta}
        return d

    def to_yaml(self) -> str:
        """序列化为 YAML 字符串"""
        import io

        buf = io.StringIO()
        yaml.dump(self.to_dict(), buf, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return buf.getvalue()


def parse_skill_file(skill_path: Path) -> tuple[SkillFrontmatter, str]:
    """解析 SKILL.md 文件，分离 frontmatter 和 body

    Args:
        skill_path: SKILL.md 文件路径

    Returns:
        (frontmatter, body): 解析后的 frontmatter 对象 + body 原文

    Raises:
        FrontmatterError: frontmatter 格式错误
    """
    text = skill_path.read_text(encoding="utf-8")
    return parse_skill_text(text)


def parse_skill_text(text: str) -> tuple[SkillFrontmatter, str]:
    """解析 SKILL.md 文本，分离 frontmatter 和 body"""
    lines = text.splitlines()
    if not lines:
        raise FrontmatterError("SKILL.md is empty")

    # 找 frontmatter 分隔符
    if lines[0].strip() != "---":
        raise FrontmatterError("SKILL.md must start with '---' YAML delimiter")

    # 找到结束的 ---
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise FrontmatterError("SKILL.md missing closing '---' delimiter")

    yaml_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])

    try:
        raw = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"YAML parse error: {exc}") from exc

    if not isinstance(raw, dict):
        raise FrontmatterError(f"YAML frontmatter must be a dict, got {type(raw).__name__}")

    # 验证必需字段
    if "name" not in raw:
        raise FrontmatterError("'name' field is required in frontmatter")
    if "description" not in raw:
        raise FrontmatterError("'description' field is required in frontmatter")

    # 解析 metadata.openclaw
    meta = SkillMetadata()
    raw_meta = raw.get("metadata", {}) or {}
    if isinstance(raw_meta, dict):
        openclaw = raw_meta.get("openclaw", {}) or {}
        if isinstance(openclaw, dict):
            meta.emoji = str(openclaw.get("emoji", ""))
            meta.requires = openclaw.get("requires", {})
            meta.install = openclaw.get("install", []) or []

    fm = SkillFrontmatter(
        name=str(raw["name"]),
        description=str(raw["description"]),
        disable_model_invocation=bool(raw.get("disable-model-invocation", False)),
        user_invocable=bool(raw.get("user-invocable", True)),
        load_experiences=bool(raw.get("load-experiences", False)),
        metadata=meta,
        _raw=raw,
    )

    return fm, body


def write_skill_file(path: Path, frontmatter: SkillFrontmatter, body: str) -> None:
    """将 frontmatter 和 body 写回 SKILL.md"""
    content = "---\n" + frontmatter.to_yaml() + "---\n" + body
    path.write_text(content, encoding="utf-8")
