"""Bounded Markdown section edits; caller cannot replace unrelated asset content."""

import difflib
import hashlib
import re
from dataclasses import dataclass

from auton.constitution.secrets import Redactor
from auton.evolve.contracts import EvolutionConfig, GateSignal, SectionPatch
from auton.kernel.ports import ApplicationError


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    body: str
    level: int


def headings(content: str) -> tuple[tuple[int, int, str, int], ...]:
    result: list[tuple[int, int, str, int]] = []
    offset = 0
    fence: tuple[str, int] | None = None
    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", stripped)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = (value[0], len(value))
            elif value[0] == fence[0] and len(value) >= fence[1] and not marker.group(2).strip():
                fence = None
        elif fence is None:
            match = re.match(r"^(#{1,6}) [^\n]+$", stripped)
            if match:
                result.append((offset, offset + len(line), stripped, len(match.group(1))))
        offset += len(line)
    if fence is not None:
        raise ApplicationError(422, "skill_unclosed_fence", "Skill has an unclosed code fence")
    return tuple(result)


class TextSectionField:
    def locate(self, content: str, heading: str) -> Section:
        values = headings(content)
        selected = [item for item in values if item[2] == heading]
        if len(selected) != 1:
            raise ApplicationError(
                422, "skill_section_ambiguous", "Choose one existing unique heading"
            )
        _, start, _, level = selected[0]
        end = next(
            (position for position, _, _, depth in values if position >= start and depth <= level),
            len(content),
        )
        return Section(start, end, content[start:end], level)

    def apply(
        self, content: str, expected_digest: str, patch: SectionPatch, config: EvolutionConfig
    ) -> tuple[str, str, tuple[GateSignal, ...]]:
        if hashlib.sha256(content.encode()).hexdigest() != expected_digest:
            raise ApplicationError(
                409, "skill_parent_changed", "Skill does not match the selected parent digest"
            )
        field = self.locate(content, patch.heading)
        if patch.before != field.body:
            raise ApplicationError(
                409,
                "skill_section_changed",
                "Before text must exactly match the selected section body",
            )
        if Redactor().text(patch.after) != patch.after:
            raise ApplicationError(
                403, "credential_in_patch", "Credentials cannot enter Skill proposals"
            )
        candidate = content[: field.start] + patch.after + content[field.end :]
        signals = []
        reasons = []
        if patch.after == patch.before:
            reasons.append("no_local_change")
        try:
            if any(depth <= field.level for _, _, _, depth in headings(patch.after)):
                reasons.append("section_boundary_escape")
        except ApplicationError:
            reasons.append("unclosed_patch_fence")
        if field.end < len(content) and not patch.after.endswith("\n"):
            reasons.append("following_heading_would_be_joined")
        # One bounded edit region; avoid quadratic character matching on untrusted text.
        prefix = 0
        while (
            prefix < min(len(patch.before), len(patch.after))
            and patch.before[prefix] == patch.after[prefix]
        ):
            prefix += 1
        suffix = 0
        while (
            suffix < min(len(patch.before), len(patch.after)) - prefix
            and patch.before[-1 - suffix] == patch.after[-1 - suffix]
        ):
            suffix += 1
        changed = max(len(patch.before), len(patch.after)) - prefix - suffix
        if (
            changed > config.max_patch_characters
            or changed > len(content) * config.max_changed_fraction
        ):
            reasons.append("patch_too_broad")
        if len(candidate.strip()) < 0.7 * len(content.strip()):
            reasons.append("over_simplification")
        if len(candidate) > 32000:
            reasons.append("candidate_asset_length_limit")
        signals.append(
            GateSignal(
                name="G1_structure", verdict="fail" if reasons else "pass", reasons=tuple(reasons)
            )
        )
        diff = "".join(
            difflib.unified_diff(
                content.splitlines(keepends=True),
                candidate.splitlines(keepends=True),
                fromfile="parent/skill.md",
                tofile="candidate/skill.md",
            )
        )
        return candidate, diff, tuple(signals)


class OptimizableFieldFactory:
    def create(self) -> TextSectionField:
        return TextSectionField()
