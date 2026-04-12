"""Unit tests for SkillPerfTracker

覆盖：
- SKILL_PERF.json 自动初始化
- record_invocation_start / end 的增量更新
- 累积统计与 7 日窗口统计的正确性
- should_optimize() 阈值逻辑
- get_config / set_config 持久化
- get_fragments(failed_only=True) 过滤逻辑
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from auton.skills.types import Skill, SkillPerfConfig, SkillSource
from auton.skills.perf_tracker import SkillPerfTracker, SkillPerfStats


# ─── Fixture ──────────────────────────────────────────────────────────────────


def _make_skill(tmp_path: Path, name: str = "test-skill") -> Skill:
    """在 tmp_path 中创建最简 Skill（SKILL.md 存在）。"""
    skill_dir = tmp_path / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: test-skill\ndescription: 测试技能。\n---\n\n正文内容。\n",
        encoding="utf-8",
    )
    return Skill(
        name=name,
        description="测试技能。",
        body="正文内容。",
        source=SkillSource.USER,
        path=skill_file,
    )


def _record_end(
    tracker: SkillPerfTracker,
    fragment_id: str,
    *,
    success: bool = True,
    tool_calls: int = 3,
    turns: int = 2,
    duration_ms: float = 500.0,
    query: str = "测试查询",
    error: str | None = None,
) -> None:
    tracker.record_invocation_end(
        fragment_id=fragment_id,
        session_id="sess-1",
        turn_index=0,
        tool_calls_count=tool_calls,
        llm_turns=turns,
        duration_ms=duration_ms,
        success=success,
        error_message=error,
        query=query,
    )


# ─── 初始化 ────────────────────────────────────────────────────────────────────


def test_perf_tracker_init_creates_file(tmp_path: Path) -> None:
    """SkillPerfTracker 构造时自动创建 SKILL_PERF.json。"""
    skill = _make_skill(tmp_path)
    perf_file = skill.skill_dir / "SKILL_PERF.json"
    assert not perf_file.exists()

    SkillPerfTracker(skill)

    assert perf_file.exists()
    import json
    data = json.loads(perf_file.read_text())
    assert data["skill_name"] == "test-skill"
    assert "cumulative" in data
    assert "window_7d" in data
    assert "thresholds" in data


def test_perf_tracker_idempotent_init(tmp_path: Path) -> None:
    """第二次构造不覆盖已有数据。"""
    skill = _make_skill(tmp_path)
    t = SkillPerfTracker(skill)
    fid = t.record_invocation_start("auto", "query", 0)
    _record_end(t, fid, tool_calls=5)

    # 重新构造
    t2 = SkillPerfTracker(skill)
    cum = t2.get_stats("cumulative")
    assert cum.total_invocations == 1


# ─── 统计累积 ─────────────────────────────────────────────────────────────────


def test_cumulative_stats_increment(tmp_path: Path) -> None:
    """累积统计随调用次数正确增量。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(5):
        fid = tracker.record_invocation_start("auto", f"query-{i}", i)
        _record_end(tracker, fid, success=True, tool_calls=4, turns=2)

    cum = tracker.get_stats("cumulative")
    assert cum.total_invocations == 5
    assert cum.successful_invocations == 5
    assert cum.failed_invocations == 0
    assert cum.success_rate == pytest.approx(1.0)
    assert cum.avg_tool_calls == pytest.approx(4.0)
    assert cum.avg_turns == pytest.approx(2.0)


def test_cumulative_tracks_failures(tmp_path: Path) -> None:
    """失败调用正确计入累积统计。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(3):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid, success=True)

    fid = tracker.record_invocation_start("auto", "fail", 3)
    _record_end(tracker, fid, success=False, error="timeout")

    cum = tracker.get_stats("cumulative")
    assert cum.total_invocations == 4
    assert cum.successful_invocations == 3
    assert cum.failed_invocations == 1
    assert cum.success_rate == pytest.approx(0.75)


# ─── 7 日窗口 ─────────────────────────────────────────────────────────────────


def test_window_7d_reflects_recent_invocations(tmp_path: Path) -> None:
    """7 日窗口统计与累积统计一致（全部在 7 天内）。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(5):
        fid = tracker.record_invocation_start("manual", f"q-{i}", i)
        _record_end(tracker, fid, success=(i % 2 == 0), tool_calls=i + 1, turns=1)

    stats7 = tracker.get_stats("7d")
    assert stats7.total_invocations == 5
    assert stats7.successful_invocations == 3   # i=0,2,4


# ─── should_optimize() ───────────────────────────────────────────────────────


def test_should_optimize_not_triggered_low_count(tmp_path: Path) -> None:
    """调用次数不足 3 时不触发优化。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    fid = tracker.record_invocation_start("auto", "q", 0)
    _record_end(tracker, fid, success=False, error="err")

    should, reason = tracker.should_optimize()
    assert should is False
    assert "too few" in reason


def test_should_optimize_triggered_by_low_success_rate(tmp_path: Path) -> None:
    """成功率低于阈值（0.70）时触发优化。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    # 调低阈值到 0.9（更容易触发）
    tracker.set_config(SkillPerfConfig(success_rate_min=0.9, avg_tool_calls_max=100, avg_turns_max=100))

    for i in range(5):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid, success=(i < 2))   # 2/5 = 40%

    should, reason = tracker.should_optimize()
    assert should is True
    assert "success_rate" in reason


def test_should_optimize_not_triggered_healthy(tmp_path: Path) -> None:
    """指标健康时不触发优化。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)
    tracker.set_config(SkillPerfConfig(success_rate_min=0.70, avg_tool_calls_max=15, avg_turns_max=5))

    for i in range(5):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid, success=True, tool_calls=3, turns=2)

    should, _ = tracker.should_optimize()
    assert should is False


# ─── get_config / set_config ──────────────────────────────────────────────────


def test_config_persistence(tmp_path: Path) -> None:
    """set_config 后再次读取返回更新后的值。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    new_cfg = SkillPerfConfig(success_rate_min=0.85, avg_tool_calls_max=8.0, avg_turns_max=3.0)
    tracker.set_config(new_cfg)

    # 新实例重新读取
    tracker2 = SkillPerfTracker(skill)
    cfg = tracker2.get_config()
    assert cfg.success_rate_min == pytest.approx(0.85)
    assert cfg.avg_tool_calls_max == pytest.approx(8.0)
    assert cfg.avg_turns_max == pytest.approx(3.0)


# ─── get_fragments ────────────────────────────────────────────────────────────


def test_get_fragments_returns_all(tmp_path: Path) -> None:
    """get_fragments() 返回所有片段记录。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(4):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid, success=(i < 3))

    records = tracker.get_fragments()
    assert len(records) == 4


def test_get_fragments_failed_only(tmp_path: Path) -> None:
    """failed_only=True 只返回失败记录。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(5):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid, success=(i % 2 == 0), error=None if i % 2 == 0 else "err")

    failures = tracker.get_fragments(failed_only=True)
    assert all(not r.success for r in failures)
    assert len(failures) == 2   # i=1,3


def test_get_fragments_limit(tmp_path: Path) -> None:
    """limit 参数正确截断返回结果。"""
    skill = _make_skill(tmp_path)
    tracker = SkillPerfTracker(skill)

    for i in range(10):
        fid = tracker.record_invocation_start("auto", f"q-{i}", i)
        _record_end(tracker, fid)

    records = tracker.get_fragments(limit=3)
    assert len(records) == 3
