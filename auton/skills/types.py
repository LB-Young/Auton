"""Skills — core types"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SkillPerfConfig:
    """Skill 性能追踪阈值配置（持久化到 SKILL_PERF.json thresholds 字段）。

    触发优化的条件（OR 关系）：
      - window_7d.success_rate < success_rate_min
      - window_7d.avg_tool_calls > avg_tool_calls_max
      - window_7d.avg_turns > avg_turns_max
    """
    success_rate_min: float = 0.70      # 7 日成功率下限
    avg_tool_calls_max: float = 15.0    # 7 日平均工具调用次数上限
    avg_turns_max: float = 5.0          # 7 日平均 LLM 轮次上限


class SkillSource(enum.Enum):
    """技能来源（优先级从高到低）"""

    WORKSPACE = "workspace"  # .auton/skills/（当前工作目录）
    PROJECT = "project"  # .auton/skills/（项目根）
    USER = "user"  # ~/.auton/skills/
    BUILTIN = "builtin"  # ~/.auton/buildin_skills/（安装时从包内复制）


# 优先级：workspace > project > user > builtin
SKILL_SOURCE_PRIORITY: dict[SkillSource, int] = {
    SkillSource.WORKSPACE: 1,
    SkillSource.PROJECT: 2,
    SkillSource.USER: 3,
    SkillSource.BUILTIN: 4,
}


@dataclass
class Skill:
    """一个完整 Skill 的内存表示"""

    name: str  # 唯一标识
    description: str  # 何时使用/何时不用
    body: str  # SKILL.md body（不含 frontmatter）
    source: SkillSource  # 来源
    path: Path  # SKILL.md 的路径
    disable_model_invocation: bool = False  # 禁止 LLM 自动调用
    user_invocable: bool = True  # 允许用户手动触发
    load_experiences: bool = False  # 自动加载 experiences/
    emoji: str = ""
    required_bins: list[str] = field(default_factory=list)  # 依赖的二进制命令

    @property
    def skill_dir(self) -> Path:
        """技能目录路径"""
        return self.path.parent

    @property
    def experiences_path(self) -> Path:
        """experiences/README.md 路径"""
        return self.skill_dir / "experiences" / "README.md"

    @property
    def has_experiences(self) -> bool:
        """是否有 experiences/ 目录"""
        return self.experiences_path.exists()

    def get_experiences(self) -> str:
        """读取 experiences/README.md"""
        if not self.has_experiences:
            return ""
        return self.experiences_path.read_text(encoding="utf-8")

    def list_references(self) -> list[Path]:
        """列出 references/ 目录下的所有文件"""
        refs = self.skill_dir / "references"
        if not refs.exists():
            return []
        return [p for p in refs.iterdir() if p.is_file()]

    def list_scripts(self) -> list[Path]:
        """列出 scripts/ 目录下的所有文件"""
        scripts = self.skill_dir / "scripts"
        if not scripts.exists():
            return []
        return [p for p in scripts.iterdir() if p.is_file() and p.name != "__init__.py"]

    def list_assets(self) -> list[Path]:
        """列出 assets/ 目录下的所有文件"""
        assets = self.skill_dir / "assets"
        if not assets.exists():
            return []
        return [p for p in assets.rglob("*") if p.is_file()]

    def get_full_content(self) -> str:
        """获取完整内容（frontmatter + body），供注入 context"""
        fm = self._build_frontmatter()
        return f"---\n{fm}---\n\n{self.body}"

    def _build_frontmatter(self) -> str:
        """构建 frontmatter YAML 字符串"""
        import yaml
        import io

        d: dict[str, object] = {"name": self.name, "description": self.description}
        if self.disable_model_invocation:
            d["disable-model-invocation"] = True
        if not self.user_invocable:
            d["user-invocable"] = False
        if self.load_experiences:
            d["load-experiences"] = True
        if self.emoji or self.required_bins:
            meta: dict[str, object] = {}
            if self.emoji:
                meta["emoji"] = self.emoji
            if self.required_bins:
                meta["requires"] = {"bins": self.required_bins}
            d["metadata"] = {"openclaw": meta}

        buf = io.StringIO()
        yaml.dump(d, buf, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return buf.getvalue()

    def to_summary(self) -> str:
        """摘要行（供 /skill list 显示）"""
        emoji = f"{self.emoji} " if self.emoji else ""
        src_label = {
            SkillSource.WORKSPACE: "[工作区]",
            SkillSource.PROJECT: "[项目]",
            SkillSource.USER: "[用户]",
            SkillSource.BUILTIN: "[内置]",
        }[self.source]
        bins = f" (需要: {', '.join(self.required_bins)})" if self.required_bins else ""
        return f"{emoji}{self.name} {src_label} — {self.description[:60]}{bins}"
