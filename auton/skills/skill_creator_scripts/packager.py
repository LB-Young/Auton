"""Skills — packager: creates and extracts .skill packages (zip files)."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


class PackageError(Exception):
    """打包/解压错误"""


@dataclass
class PackageInfo:
    """.skill 包元信息"""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    path: Path | None = None


class SkillPackager:
    """技能打包器

    .skill 文件本质是 zip 包，后缀为 .skill
    结构：
      skill-name/
        SKILL.md
        scripts/
        references/
        assets/
        experiences/
    """

    REQUIRED_FILE = "SKILL.md"

    def __init__(self) -> None:
        self._logger = logger.bind(name="SkillPackager")

    def package(self, skill_dir: Path, output_dir: Path | None = None) -> Path:
        """将 skill 目录打包为 .skill 文件

        Args:
            skill_dir: skill 目录（如 ~/.auton/skill/github/）
            output_dir: 输出目录（默认与 skill_dir 同级）

        Returns:
            生成的 .skill 文件路径
        """
        if not skill_dir.exists() or not skill_dir.is_dir():
            raise PackageError(f"Skill directory not found: {skill_dir}")

        skill_file = skill_dir / self.REQUIRED_FILE
        if not skill_file.exists():
            raise PackageError(f"SKILL.md not found in {skill_dir}")

        if output_dir is None:
            output_dir = skill_dir.parent

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        pkg_path = output_dir / f"{skill_dir.name}.skill"

        with zipfile.ZipFile(pkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in skill_dir.rglob("*"):
                if file_path.is_file():
                    # 跳过 symlink（安全限制）
                    if file_path.is_symlink():
                        self._logger.warning("skipping symlink: {p}", p=file_path)
                        continue
                    # 计算在 zip 中的路径
                    arcname = file_path.relative_to(skill_dir)
                    zf.write(file_path, arcname)

        self._logger.info("packaged skill {n} -> {p}", n=skill_dir.name, p=pkg_path)
        return pkg_path

    def extract(self, pkg_path: Path, dest_dir: Path) -> Path:
        """解压 .skill 包到目标目录

        Args:
            pkg_path: .skill 文件路径
            dest_dir: 解压目标目录

        Returns:
            解压到的 skill 目录路径
        """
        if not pkg_path.exists():
            raise PackageError(f"Package not found: {pkg_path}")

        if not pkg_path.suffix == ".skill":
            raise PackageError(f"Not a .skill file: {pkg_path}")

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(pkg_path, "r") as zf:
            # 验证内容
            names = zf.namelist()
            if not any(n.endswith("SKILL.md") for n in names):
                raise PackageError("Invalid .skill package: SKILL.md not found")

            # 检查路径遍历攻击
            for name in names:
                resolved = (dest_dir / name).resolve()
                if not str(resolved).startswith(str(dest_dir.resolve())):
                    raise PackageError(f"Path traversal detected: {name}")

            zf.extractall(dest_dir)

        # 确定 skill 目录（包内顶层目录名）
        skill_name = pkg_path.stem  # xxx.skill -> xxx
        skill_dir = dest_dir / skill_name
        self._logger.info("extracted skill to {d}", d=skill_dir)
        return skill_dir

    def get_info(self, pkg_path: Path) -> PackageInfo:
        """读取 .skill 包元信息（从顶层 SKILL.md）"""
        if not pkg_path.exists():
            raise PackageError(f"Package not found: {pkg_path}")

        skill_name = pkg_path.stem
        info = PackageInfo(name=skill_name, path=pkg_path)

        try:
            with zipfile.ZipFile(pkg_path, "r") as zf:
                skill_md_name = f"{skill_name}/SKILL.md"
                for name in zf.namelist():
                    if name.endswith("SKILL.md"):
                        skill_md_name = name
                        break

                content = zf.read(skill_md_name).decode("utf-8")
                # 简单解析 frontmatter
                info.description = self._extract_description(content)
        except Exception as exc:
            self._logger.warning("failed to read package info: {e}", e=exc)

        return info

    def _extract_description(self, text: str) -> str:
        """从 SKILL.md 提取 description"""
        import yaml

        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return ""
        end = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end = i
                break
        if end is None:
            return ""
        yaml_text = "\n".join(lines[1:end])
        try:
            data = yaml.safe_load(yaml_text) or {}
            return str(data.get("description", ""))
        except Exception:
            return ""

    def validate(self, skill_dir: Path) -> list[str]:
        """验证 skill 目录格式，返回错误列表"""
        errors: list[str] = []

        if not skill_dir.exists():
            errors.append(f"Directory not found: {skill_dir}")
            return errors

        if not skill_dir.is_dir():
            errors.append(f"Not a directory: {skill_dir}")
            return errors

        skill_file = skill_dir / self.REQUIRED_FILE
        if not skill_file.exists():
            errors.append(f"SKILL.md not found in {skill_dir}")

        # 检查 frontmatter
        if skill_file.exists():
            try:
                from ..frontmatter import parse_skill_file

                parse_skill_file(skill_file)
            except Exception as exc:
                errors.append(f"SKILL.md frontmatter error: {exc}")

        # 检查 symlink
        for p in skill_dir.rglob("*"):
            if p.is_symlink():
                errors.append(f"Symlink not allowed: {p}")

        return errors
