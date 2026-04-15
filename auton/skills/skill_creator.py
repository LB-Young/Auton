"""Skills — skill-creator: meta-skill for creating new skills."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ..core.paths import resolve_userspace_path

from .frontmatter import write_skill_file, SkillFrontmatter, SkillMetadata
from .packager import SkillPackager


class SkillCreator:
    """skill-creator 逻辑

    引导用户通过对话创建新技能。

    流程：
      1. 理解场景：收集具体使用示例
      2. 规划内容：确定需要哪些资源（scripts/references/assets/experiences）
      3. 初始化目录：创建 ~/.auton/skill/<skill-name>/
      4. 编写 SKILL.md
      5. 创建 experiences/README.md 模板
      6. 验证并打包
    """

    def __init__(self) -> None:
        self._logger = logger.bind(name="SkillCreator")
        self._packager = SkillPackager()

    def get_user_skills_dir(self) -> Path:
        """用户级技能目录：~/.auton/skill/"""
        return resolve_userspace_path("skill")

    def init_skill(
        self,
        name: str,
        description: str,
        emoji: str = "",
        load_experiences: bool = True,
        cwd: Path | None = None,
    ) -> Path:
        """初始化一个技能目录

        Args:
            name: 技能名称（小写+连字符）
            description: 何时使用/何时不用
            emoji: 可选 emoji
            load_experiences: 是否加载 experiences
            cwd: 当前工作目录（用于 project 级技能）

        Returns:
            技能目录路径
        """
        # 决定写入哪个层级
        if cwd is None:
            cwd = Path.cwd()

        dest_dir = self.get_user_skills_dir()

        skill_dir = dest_dir / name
        if skill_dir.exists():
            raise ValueError(f"Skill '{name}' already exists at {skill_dir}")

        skill_dir.mkdir(parents=True, exist_ok=True)

        # 创建 SKILL.md
        fm = SkillFrontmatter(
            name=name,
            description=description,
            load_experiences=load_experiences,
            metadata=SkillMetadata(emoji=emoji) if emoji else SkillMetadata(),
        )

        default_body = self._default_body(name, description)
        write_skill_file(skill_dir / "SKILL.md", fm, default_body)

        # 创建 experiences/README.md
        experiences_dir = skill_dir / "experiences"
        experiences_dir.mkdir(parents=True, exist_ok=True)
        experiences_readme = experiences_dir / "README.md"
        experiences_readme.write_text(
            self._experiences_template(name),
            encoding="utf-8",
        )
        self._logger.debug("created experiences/README.md for {n}", n=name)

        # 初始化 SKILL_PERF.json（性能追踪基准文件）
        from .perf_tracker import SkillPerfTracker
        from .frontmatter import parse_skill_file
        from .types import SkillSource as _SkillSource
        skill_obj = parse_skill_file(skill_dir / "SKILL.md", source=_SkillSource.USER)
        SkillPerfTracker(skill_obj)  # _ensure_init() 在 __init__ 中自动执行
        self._logger.debug("initialized SKILL_PERF.json for {n}", n=name)

        self._logger.info("created skill {n} at {d}", n=name, d=skill_dir)
        return skill_dir

    def _default_body(self, name: str, description: str) -> str:
        """生成默认 SKILL.md body"""
        return f"""# {name} Skill

{description}

## When to Use

✅ **USE this skill when:**
- ...

❌ **DON'T use this skill when:**
- ...

## Quick Start

```bash
# ...
```

## Common Commands

...

## Examples

### Example 1: ...

```

## Notes

- ...
"""

    def _experiences_template(self, name: str) -> str:
        """生成 experiences/README.md 模板"""
        return f"""# {name} 使用经验

本文档记录本 skill 在实际使用中积累的经验和教训，每次使用后可选择追加新条目。
LLM 在执行本 skill 时读取此文件，避免重复犯错、复用成功路径。

## 经验条目

### YYYY-MM-DD: 简短标题
- **场景**：在什么情况下遇到问题或发现最佳实践。
- **教训/最佳实践**：如何解决或应该怎么做。
- **标签**：#topic

"""

    async def init_skill_async(
        self,
        name: str,
        description: str,
        llm,
        emoji: str = "",
        load_experiences: bool = True,
        cwd: Path | None = None,
        overhead_factor: float = 1.2,
    ) -> Path:
        """异步版本：创建 skill 并用 LLM 自动标定性能阈值。

        工具调用次数和 LLM 轮次阈值 = LLM 估算值 × overhead_factor（默认 1.2）。
        比固定阈值更合理：复杂 skill 自然允许更多工具调用，简单 skill 会更严格。

        Args:
            name: skill 名称
            description: 使用描述
            llm: LLM Provider（用于阈值标定）
            emoji: 可选 emoji
            load_experiences: 是否加载 experiences
            cwd: 当前工作目录
            overhead_factor: 容忍倍数（LLM 估算值的倍数作为上限）

        Returns:
            skill 目录路径
        """
        skill_dir = self.init_skill(
            name=name,
            description=description,
            emoji=emoji,
            load_experiences=load_experiences,
            cwd=cwd,
        )
        try:
            from .perf_tracker import SkillPerfTracker
            from .frontmatter import parse_skill_file
            from .types import SkillSource
            skill = parse_skill_file(skill_dir / "SKILL.md", source=SkillSource.USER)
            tracker = SkillPerfTracker(skill)
            config = await tracker.calibrate_thresholds(llm, overhead_factor=overhead_factor)
            self._logger.info(
                "auto-calibrated thresholds for {n}: tool_calls≤{tc} turns≤{t}",
                n=name,
                tc=config.avg_tool_calls_max,
                t=config.avg_turns_max,
            )
        except Exception as exc:
            self._logger.warning(
                "threshold calibration failed for {n}: {e} (defaults kept)", n=name, e=exc
            )
        return skill_dir

    def package_skill(self, name: str, cwd: Path | None = None) -> Path:
        """打包技能为 .skill 文件"""
        skill_dir = self._find_skill_dir(name, cwd)
        return self._packager.package(skill_dir)

    def _find_skill_dir(self, name: str, cwd: Path | None = None) -> Path:
        """查找技能目录"""
        if cwd is None:
            cwd = Path.cwd()

        search_dirs = [
            cwd / ".auton" / "skill",  # 工作区/项目
            self.get_user_skills_dir(),  # 用户
        ]

        for base in search_dirs:
            skill_dir = base / name
            if skill_dir.exists():
                return skill_dir

        raise FileNotFoundError(f"Skill '{name}' not found")
