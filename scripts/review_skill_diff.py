"""
review_skill_diff.py — Mechanical subset of skill-authoring-standard's review-checklist
(RA-continuous-moa §6.4)

Checks the three items from Pi-Dev-Ops/skills/skill-authoring-standard/references/review-checklist.md
that are unambiguously mechanical:
  1. Structure gate: "SKILL.md <= 200 lines."
  2. Trigger gate: "No banned fields (version, owner_role, status, metadata.requires)
     without a stated reason."
  3. Design-elements gate (file-scope reading): the diff touches only the one target
     SKILL.md, nothing else.

Qualitative gates (duplication / single-source-of-truth, leading-word steering,
sediment/no-op pruning) are NOT mechanically checked here — they require reading
meaning, not counting lines. draft_skill_diff.py's dispatch prompt already
instructs the drafting agent to self-apply those; a human reviewing the PR is
the final gate for them, per design §6's "propose-via-PR only" framing.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

_MAX_LINES = 200
_BANNED_FRONTMATTER_FIELDS = ("version", "owner_role", "status", "metadata.requires")

_DIFF_FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)
_ADDED_LINE_RE = re.compile(r"^\+(?!\+\+)(.*)$", re.MULTILINE)


@dataclass
class ReviewResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


def _diff_target_files(diff_text: str) -> list[str]:
    return _DIFF_FILE_HEADER_RE.findall(diff_text)


def _added_lines(diff_text: str) -> list[str]:
    return _ADDED_LINE_RE.findall(diff_text)


def _resulting_line_count(skill_md_path: Path, diff_text: str) -> int:
    """Approximate the post-diff line count: current lines + net added lines
    (added minus removed). Good enough for a hard 200-line cap check without
    needing a real patch-apply dependency.
    """
    current = len(skill_md_path.read_text().splitlines())
    added = len(re.findall(r"^\+(?!\+\+)", diff_text, re.MULTILINE))
    removed = len(re.findall(r"^-(?!--)", diff_text, re.MULTILINE))
    return current + added - removed


def review_diff(diff_text: str, skill_md_path: Path) -> ReviewResult:
    failures: list[str] = []

    if diff_text.strip() == "NO_CHANGE_JUSTIFIED":
        return ReviewResult(passed=False, failures=["No change justified by drafting agent — nothing to review."])

    targets = _diff_target_files(diff_text)
    expected_name = skill_md_path.name
    if not targets:
        failures.append("Diff has no recognizable +++ b/ file header — cannot verify scope.")
    elif any(not t.endswith(expected_name) for t in targets):
        failures.append(
            f"Diff touches file(s) outside scope: {targets} — only {expected_name} is permitted."
        )
    if len(set(targets)) > 1:
        failures.append(f"Diff touches multiple files: {targets} — must be single-file, single-scoped.")

    if skill_md_path.exists():
        resulting_lines = _resulting_line_count(skill_md_path, diff_text)
        if resulting_lines > _MAX_LINES:
            failures.append(
                f"Resulting SKILL.md would be {resulting_lines} lines, over the {_MAX_LINES}-line cap."
            )

    for added in _added_lines(diff_text):
        for banned in _BANNED_FRONTMATTER_FIELDS:
            if re.match(rf"^\s*{re.escape(banned.split('.')[0])}\s*:", added):
                failures.append(f"Diff introduces banned frontmatter field: {banned}")

    return ReviewResult(passed=len(failures) == 0, failures=failures)
