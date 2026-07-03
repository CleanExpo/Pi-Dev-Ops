"""tests/test_scan_skill_lessons.py — threshold-scan job for skill-process lessons."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.scan_skill_lessons import (  # noqa: E402
    find_flagged_skills,
    group_by_skill,
    load_skill_lessons,
)


def _entry(skill: str, days_ago: int, severity: str = "warn", lesson: str = "x") -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "ts": ts,
        "source": "test",
        "category": "process",
        "applies_to_skill": skill,
        "lesson": lesson,
        "severity": severity,
    }


def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def test_load_skill_lessons_filters_out_entries_without_applies_to_skill(tmp_path):
    path = tmp_path / "lessons.jsonl"
    _write_jsonl(path, [
        {"ts": "2026-07-01T00:00:00Z", "source": "x", "category": "security", "lesson": "domain lesson", "severity": "warn"},
        _entry("agent-expert", days_ago=1),
    ])
    result = load_skill_lessons(path)
    assert len(result) == 1
    assert result[0]["applies_to_skill"] == "agent-expert"


def test_load_skill_lessons_missing_file_returns_empty(tmp_path):
    result = load_skill_lessons(tmp_path / "does-not-exist.jsonl")
    assert result == []


def test_load_skill_lessons_skips_malformed_json_lines(tmp_path):
    path = tmp_path / "lessons.jsonl"
    path.write_text('{"applies_to_skill": "agent-expert", "ts": "2026-07-01T00:00:00Z"}\nnot json\n')
    result = load_skill_lessons(path)
    assert len(result) == 1


def test_group_by_skill_groups_correctly():
    lessons = [
        _entry("agent-expert", days_ago=1),
        _entry("agent-expert", days_ago=2),
        _entry("skill-authoring-standard", days_ago=1),
    ]
    groups = group_by_skill(lessons)
    assert set(groups.keys()) == {"agent-expert", "skill-authoring-standard"}
    assert len(groups["agent-expert"]) == 2
    assert len(groups["skill-authoring-standard"]) == 1


def test_find_flagged_skills_respects_min_count_default_3():
    groups = {
        "agent-expert": [_entry("agent-expert", days_ago=1) for _ in range(3)],
        "boardroom": [_entry("boardroom", days_ago=1) for _ in range(2)],
    }
    flagged = find_flagged_skills(groups)
    assert "agent-expert" in flagged
    assert "boardroom" not in flagged


def test_find_flagged_skills_excludes_entries_outside_window_days_30():
    old_entries = [_entry("agent-expert", days_ago=45) for _ in range(5)]
    groups = {"agent-expert": old_entries}
    flagged = find_flagged_skills(groups, min_count=3, window_days=30)
    assert "agent-expert" not in flagged


def test_find_flagged_skills_mixed_window_counts_only_recent():
    entries = (
        [_entry("agent-expert", days_ago=45) for _ in range(5)]
        + [_entry("agent-expert", days_ago=1) for _ in range(2)]
    )
    groups = {"agent-expert": entries}
    flagged = find_flagged_skills(groups, min_count=3, window_days=30)
    assert "agent-expert" not in flagged  # only 2 within window, threshold is 3


def test_find_flagged_skills_custom_min_count_override():
    groups = {"agent-expert": [_entry("agent-expert", days_ago=1) for _ in range(2)]}
    flagged = find_flagged_skills(groups, min_count=2, window_days=30)
    assert "agent-expert" in flagged
