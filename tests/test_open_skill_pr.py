"""tests/test_open_skill_pr.py — PR-opening step for skill self-improvement (RA-continuous-moa §6.5)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.open_skill_pr import branch_name, ensure_label_exists, pr_body, pr_title  # noqa: E402


def _lessons():
    return [
        {"ts": "2026-07-01T00:00:00Z", "source": "x", "applies_to_skill": "skill-authoring-standard",
         "lesson": "Line-count cap doesn't say whether frontmatter counts.", "severity": "warn"},
    ]


def test_pr_title_follows_skill_learn_convention():
    title = pr_title("skill-authoring-standard", _lessons())
    assert title.startswith("skill-learn(skill-authoring-standard):")
    assert "Line-count cap doesn't say whether frontmatter counts." in title


def test_pr_title_truncates_long_lesson_text():
    long_lesson = [{"lesson": "x" * 300, "severity": "warn", "source": "y", "ts": "2026-07-01T00:00:00Z",
                     "applies_to_skill": "test-skill"}]
    title = pr_title("test-skill", long_lesson)
    assert len(title) < 120


def test_branch_name_includes_skill_name_and_is_git_safe():
    name = branch_name("skill-authoring-standard")
    assert "skill-authoring-standard" in name
    assert " " not in name
    assert name.startswith("skill-self-update/")


def test_pr_body_includes_triggering_lesson_excerpt():
    body = pr_body("skill-authoring-standard", _lessons())
    assert "Line-count cap doesn't say whether frontmatter counts." in body
    assert "skill-authoring-standard" in body


def test_pr_body_includes_review_disclaimer():
    body = pr_body("skill-authoring-standard", _lessons())
    assert "auto-generated" in body.lower() or "review" in body.lower()


def test_ensure_label_exists_creates_when_missing(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "label", "list"]:
            class R:
                stdout = "bug\tSomething isn't working\n"
                returncode = 0
            return R()
        class R:
            stdout = ""
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    ensure_label_exists(repo="CleanExpo/Pi-Dev-Ops")
    create_calls = [c for c in calls if c[:3] == ["gh", "label", "create"]]
    assert len(create_calls) == 1
    assert "skill-self-update" in create_calls[0]


def test_ensure_label_exists_skips_when_present(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["gh", "label", "list"]:
            class R:
                stdout = "skill-self-update\tAuto-generated skill process fix\n"
                returncode = 0
            return R()
        class R:
            stdout = ""
            returncode = 0
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    ensure_label_exists(repo="CleanExpo/Pi-Dev-Ops")
    create_calls = [c for c in calls if c[:3] == ["gh", "label", "create"]]
    assert len(create_calls) == 0
