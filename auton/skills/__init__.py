"""Auton Skills — 技能系统模块

Skill 是一个带 YAML frontmatter 的 Markdown 文件，本质是知识文档。
当用户请求涉及某个领域时，Auton 把对应 Skill 的内容注入 context，
让 LLM 知道在这个场景下应该用什么工具、怎么用。

导出公共接口供 agent 和 commands 使用。
"""

from .checker import SkillChecker
from .frontmatter import (
    parse_skill_file,
    parse_skill_text,
    write_skill_file,
    SkillFrontmatter,
    SkillMetadata,
    FrontmatterError,
)
from .injector import SkillInjector
from .loader import SkillLoader
from .packager import SkillPackager
from .registry import SkillRegistry
from .semantic_search import SkillSearcher, SearchResult
from .skill_creator import SkillCreator
from .types import Skill, SkillSource

__all__ = [
    # 类型
    "Skill",
    "SkillSource",
    "SkillFrontmatter",
    "SkillMetadata",
    "SearchResult",
    # 核心
    "SkillRegistry",
    "SkillLoader",
    "SkillInjector",
    "SkillSearcher",
    "SkillChecker",
    "SkillPackager",
    "SkillCreator",
    # 工具
    "parse_skill_file",
    "parse_skill_text",
    "write_skill_file",
    "FrontmatterError",
]
