"""tests/test_skill_self_update.py — end-to-end orchestrator (RA-continuous-moa §6, full chain)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import skill_self_update  # noqa: E402


def _write_lessons(path: Path, skill: str, count: int) -> None:
    with path.open("w") as f:
        for i in range(count):
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "test",
                "applies_to_skill": skill,
                "lesson": f"lesson {i} about {skill}",
                "severity": "warn",
            }
            f.write(json.dumps(entry) + "\n")


def test_run_cycle_no_flagged_skills_returns_empty(tmp_path, monkeypatch):
    lessons_path = tmp_path / "lessons.jsonl"
    _write_lessons(lessons_path, "agent-expert", count=1)  # below default min_count=3

    def fail_dispatch(prompt: str) -> str:
        raise AssertionError("dispatch_fn should not be called when nothing is flagged")

    results = skill_self_update.run_cycle(lessons_path, dispatch_fn=fail_dispatch)
    assert results == []


def test_run_cycle_opens_pr_on_passing_diff(tmp_path, monkeypatch):
    lessons_path = tmp_path / "lessons.jsonl"
    _write_lessons(lessons_path, "agent-expert", count=3)

    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: agent-expert\n---\n\n# Agent Experts\n\ncontent\n")

    monkeypatch.setattr(
        skill_self_update, "_skill_md_path", lambda skill_name: skill_md
    )

    passing_diff = (
        "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -5,1 +5,2 @@\n content\n+- New scoped rule.\n"
    )

    def fake_dispatch(prompt: str) -> str:
        assert "agent-expert" in prompt
        return passing_diff

    opened = {}

    def fake_open_pr(skill_name, diff_text, lessons, repo_path=REPO_ROOT):
        opened["skill_name"] = skill_name
        opened["diff_text"] = diff_text
        return "https://github.com/CleanExpo/Pi-Dev-Ops/pull/999"

    monkeypatch.setattr(skill_self_update, "open_pr", fake_open_pr)

    results = skill_self_update.run_cycle(lessons_path, dispatch_fn=fake_dispatch)

    assert len(results) == 1
    assert results[0]["skill"] == "agent-expert"
    assert results[0]["outcome"] == "pr_opened"
    assert "999" in results[0]["detail"]
    assert opened["skill_name"] == "agent-expert"


def test_run_cycle_rejects_and_does_not_open_pr_on_failing_diff(tmp_path, monkeypatch):
    lessons_path = tmp_path / "lessons.jsonl"
    _write_lessons(lessons_path, "agent-expert", count=3)

    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: agent-expert\n---\n\n# Agent Experts\n\ncontent\n")
    monkeypatch.setattr(skill_self_update, "_skill_md_path", lambda skill_name: skill_md)

    failing_diff = "--- a/OTHER.md\n+++ b/OTHER.md\n@@ -1,1 +1,2 @@\n x\n+y\n"

    def fake_dispatch(prompt: str) -> str:
        return failing_diff

    def fail_open_pr(*args, **kwargs):
        raise AssertionError("open_pr should not be called when review fails")

    monkeypatch.setattr(skill_self_update, "open_pr", fail_open_pr)

    results = skill_self_update.run_cycle(lessons_path, dispatch_fn=fake_dispatch)

    assert len(results) == 1
    assert results[0]["outcome"] == "rejected"


def test_run_cycle_handles_no_change_justified(tmp_path, monkeypatch):
    lessons_path = tmp_path / "lessons.jsonl"
    _write_lessons(lessons_path, "agent-expert", count=3)

    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: agent-expert\n---\n\n# Agent Experts\n\ncontent\n")
    monkeypatch.setattr(skill_self_update, "_skill_md_path", lambda skill_name: skill_md)

    def fake_dispatch(prompt: str) -> str:
        return "NO_CHANGE_JUSTIFIED"

    def fail_open_pr(*args, **kwargs):
        raise AssertionError("open_pr should not be called on NO_CHANGE_JUSTIFIED")

    monkeypatch.setattr(skill_self_update, "open_pr", fail_open_pr)

    results = skill_self_update.run_cycle(lessons_path, dispatch_fn=fake_dispatch)

    assert len(results) == 1
    assert results[0]["outcome"] == "no_change_justified"
