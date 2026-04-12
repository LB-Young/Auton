"""Unit tests for SkillOptimizer

覆盖：
- _parse_llm_output：三分隔块解析（正常/降级）
- _apply_to_skill_md：frontmatter 保留 + body 替换
- _append_experiences：创建新文件 + 追加到已有文件
- optimize(force=True)：端到端流程，使用 mock LLM
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auton.skills.types import Skill, SkillSource
from auton.skills.optimizer import SkillOptimizer, OptimizationResult
from auton.skills.perf_tracker import SkillPerfTracker


# ─── Fixtures ─────────────────────────────────────────────────────────────────


SKILL_MD_CONTENT = """\
---
name: test-skill
description: 测试技能，用于单元测试。
---

## 当前 Body

使用本 skill 完成测试任务。
"""


def _make_skill(tmp_path: Path, name: str = "test-skill") -> Skill:
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(SKILL_MD_CONTENT, encoding="utf-8")
    return Skill(
        name=name,
        description="测试技能，用于单元测试。",
        body="## 当前 Body\n\n使用本 skill 完成测试任务。\n",
        source=SkillSource.USER,
        path=skill_file,
    )


def _make_tracker(skill: Skill) -> SkillPerfTracker:
    return SkillPerfTracker(skill)


def _make_mock_llm(response_text: str) -> MagicMock:
    """构造一个模拟 LLM，stream() 返回包含指定文本的事件。"""

    async def _fake_stream(_ctx):
        class Chunk:
            def __init__(self, t: str):
                self.text = t

        yield Chunk(response_text)

    llm = MagicMock()
    llm.model_name = "mock-model"
    llm.stream = _fake_stream
    return llm


# ─── _parse_llm_output ────────────────────────────────────────────────────────


def test_parse_llm_output_full(tmp_path: Path) -> None:
    """三个分隔块均正确解析。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    raw = """\
===ANALYSIS===
成功率低，主要因为步骤 3 缺乏错误处理。

===NEW_SKILL_MD===
## 优化后的 Body

改进了错误处理逻辑。

===EXPERIENCE_ENTRY===
### 2026-01-01: 错误处理缺失
- **场景**：步骤 3 无错误处理导致超时
- **教训**：增加 retry 逻辑
- **标签**：#error-handling
"""

    analysis, new_body, experience = optimizer._parse_llm_output(raw)

    assert "成功率低" in analysis
    assert "优化后的 Body" in new_body
    assert "错误处理缺失" in experience


def test_parse_llm_output_missing_sections(tmp_path: Path) -> None:
    """分隔块缺失时优雅降级。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    raw = "纯分析文本，没有分隔符。"
    analysis, new_body, experience = optimizer._parse_llm_output(raw)

    assert "纯分析文本" in analysis
    assert new_body == ""
    assert experience == ""


def test_parse_llm_output_empty(tmp_path: Path) -> None:
    """LLM 返回空字符串时不抛出异常。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    analysis, new_body, experience = optimizer._parse_llm_output("")
    assert analysis == ""
    assert new_body == ""
    assert experience == ""


# ─── _apply_to_skill_md ──────────────────────────────────────────────────────


def test_apply_to_skill_md_preserves_frontmatter(tmp_path: Path) -> None:
    """更新 body 后 frontmatter 保持不变。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    new_body = "## 优化后内容\n\n这是全新的 body。\n"
    optimizer._apply_to_skill_md(new_body)

    updated = skill.path.read_text(encoding="utf-8")
    assert "name: test-skill" in updated            # frontmatter 保留
    assert "description: 测试技能" in updated       # frontmatter 保留
    assert "优化后内容" in updated                   # 新 body 写入
    assert "当前 Body" not in updated               # 旧 body 删除


def test_apply_to_skill_md_no_frontmatter(tmp_path: Path) -> None:
    """无 frontmatter 的 SKILL.md 直接覆盖写入。"""
    skill = _make_skill(tmp_path)
    skill.path.write_text("原始内容（无 frontmatter）\n", encoding="utf-8")

    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    optimizer._apply_to_skill_md("新内容")
    assert "新内容" in skill.path.read_text(encoding="utf-8")


# ─── _append_experiences ──────────────────────────────────────────────────────


def test_append_experiences_creates_file(tmp_path: Path) -> None:
    """experiences/README.md 不存在时自动创建并写入条目。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    exp_path = skill.experiences_path
    assert not exp_path.exists()

    entry = "### 2026-01-01: 初次经验\n- **教训**：要加 retry"
    optimizer._append_experiences(entry)

    assert exp_path.exists()
    content = exp_path.read_text(encoding="utf-8")
    assert "初次经验" in content
    assert "要加 retry" in content


def test_append_experiences_appends_to_existing(tmp_path: Path) -> None:
    """已有 experiences/README.md 时追加到末尾。"""
    skill = _make_skill(tmp_path)
    exp_path = skill.experiences_path
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    exp_path.write_text("# 旧内容\n\n## 第一条经验\n- 之前的教训\n", encoding="utf-8")

    tracker = _make_tracker(skill)
    optimizer = SkillOptimizer(tracker, MagicMock())

    optimizer._append_experiences("### 2026-06-01: 新经验\n- **教训**：新的教训")
    content = exp_path.read_text(encoding="utf-8")

    assert "旧内容" in content
    assert "之前的教训" in content
    assert "新经验" in content


# ─── optimize() 端到端 ────────────────────────────────────────────────────────


LLM_RESPONSE = """\
===ANALYSIS===
调用失败率高，主要原因是超时处理缺失，建议增加重试逻辑。

===NEW_SKILL_MD===
## 优化后 Body（LLM 生成）

增加了超时处理和重试机制。

===EXPERIENCE_ENTRY===
### 2026-01-01: 超时导致失败率上升
- **场景**：网络不稳定时工具调用超时
- **教训**：增加 retry 配置
- **标签**：#timeout #retry
"""


@pytest.mark.asyncio
async def test_optimize_force_returns_result(tmp_path: Path) -> None:
    """force=True 时执行完整优化并返回 OptimizationResult。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    llm = _make_mock_llm(LLM_RESPONSE)

    optimizer = SkillOptimizer(tracker, llm)
    result = await optimizer.optimize(force=True)

    assert isinstance(result, OptimizationResult)
    assert result.skill_name == "test-skill"
    assert result.trigger_reason != "skipped"
    assert "超时处理缺失" in result.analysis
    assert result.skill_md_updated is True
    assert result.experiences_appended is True
    assert result.error is None


@pytest.mark.asyncio
async def test_optimize_skipped_without_force(tmp_path: Path) -> None:
    """未达阈值且 force=False 时跳过优化（只有 1 条记录）。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)

    # 仅 1 条记录，不满足 should_optimize 的 >= 3 调用条件
    fid = tracker.record_invocation_start("auto", "q", 0)
    tracker.record_invocation_end(
        fragment_id=fid, session_id="s", turn_index=0,
        tool_calls_count=2, llm_turns=1, duration_ms=100,
        success=True,
    )

    llm = _make_mock_llm(LLM_RESPONSE)
    optimizer = SkillOptimizer(tracker, llm)
    result = await optimizer.optimize(force=False)

    assert result.trigger_reason == "skipped"
    assert result.skill_md_updated is False
    assert result.experiences_appended is False


@pytest.mark.asyncio
async def test_optimize_updates_skill_md_content(tmp_path: Path) -> None:
    """optimize() 执行后 SKILL.md 的 body 已更新。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)
    llm = _make_mock_llm(LLM_RESPONSE)

    optimizer = SkillOptimizer(tracker, llm)
    await optimizer.optimize(force=True)

    updated = skill.path.read_text(encoding="utf-8")
    assert "优化后 Body（LLM 生成）" in updated
    assert "name: test-skill" in updated   # frontmatter 保留


@pytest.mark.asyncio
async def test_optimize_llm_error_returns_error_result(tmp_path: Path) -> None:
    """LLM 调用抛出异常时，optimize 返回 error 字段非空的结果。"""
    skill = _make_skill(tmp_path)
    tracker = _make_tracker(skill)

    async def _broken_stream(_ctx):
        raise RuntimeError("LLM unavailable")
        yield  # make it a generator

    llm = MagicMock()
    llm.model_name = "mock-model"
    llm.stream = _broken_stream

    optimizer = SkillOptimizer(tracker, llm)
    result = await optimizer.optimize(force=True)

    assert result.error is not None
    assert "LLM unavailable" in result.error
    assert result.skill_md_updated is False
