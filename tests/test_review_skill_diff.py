"""tests/test_review_skill_diff.py — mechanical subset of skill-authoring-standard's review-checklist."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.review_skill_diff import review_diff  # noqa: E402


def _make_skill_md(tmp_path: Path, line_count: int) -> Path:
    lines = ["---", "name: test-skill", "description: test", "---", "", "# Test Skill", ""]
    lines += [f"line {i}" for i in range(max(0, line_count - len(lines)))]
    path = tmp_path / "SKILL.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_passing_diff_under_200_lines_passes(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -5,1 +5,2 @@\n # Test Skill\n+- New scoped rule.\n"
    )
    result = review_diff(diff, skill_md)
    assert result.passed is True
    assert result.failures == []


def test_diff_that_pushes_file_over_200_lines_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=199)
    added_lines = "\n".join(f"+extra line {i}" for i in range(10))
    diff = f"--- a/SKILL.md\n+++ b/SKILL.md\n@@ -199,0 +199,10 @@\n{added_lines}\n"
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("200" in f or "line" in f.lower() for f in result.failures)


def test_diff_introducing_banned_frontmatter_field_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,4 +1,5 @@\n ---\n"
        " name: test-skill\n+version: 1.2.0\n description: test\n ---\n"
    )
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("version" in f.lower() or "banned" in f.lower() for f in result.failures)


def test_diff_introducing_banned_owner_role_field_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,4 +1,5 @@\n ---\n"
        " name: test-skill\n+owner_role: admin\n description: test\n ---\n"
    )
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("owner_role" in f.lower() or "banned" in f.lower() for f in result.failures)


def test_diff_introducing_banned_status_field_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,4 +1,5 @@\n ---\n"
        " name: test-skill\n+status: active\n description: test\n ---\n"
    )
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("status" in f.lower() or "banned" in f.lower() for f in result.failures)


def test_diff_introducing_banned_metadata_requires_field_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,4 +1,5 @@\n ---\n"
        " name: test-skill\n+metadata:\n description: test\n ---\n"
    )
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("metadata" in f.lower() or "banned" in f.lower() for f in result.failures)


def test_diff_touching_a_different_file_fails(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    diff = "--- a/OTHER.md\n+++ b/OTHER.md\n@@ -1,1 +1,2 @@\n content\n+new content\n"
    result = review_diff(diff, skill_md)
    assert result.passed is False
    assert any("file" in f.lower() or "scope" in f.lower() for f in result.failures)


def test_no_change_justified_sentinel_fails_cleanly(tmp_path):
    skill_md = _make_skill_md(tmp_path, line_count=50)
    result = review_diff("NO_CHANGE_JUSTIFIED", skill_md)
    assert result.passed is False
    assert any("no change" in f.lower() for f in result.failures)
