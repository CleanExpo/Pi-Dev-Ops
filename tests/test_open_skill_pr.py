"""tests/test_open_skill_pr.py — PR-opening step for skill self-improvement (RA-continuous-moa §6.5)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.open_skill_pr import branch_name, ensure_label_exists, open_pr, pr_body, pr_title  # noqa: E402


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


def _fake_run_recorder(calls, apply_returncode=0):
    """Build a hermetic fake for subprocess.run that records every invoked
    argv into `calls` and never shells out to real git/gh. Mirrors just
    enough of subprocess.CompletedProcess to satisfy open_pr's real code
    path (it only reads .returncode on the `git apply` result and .stdout
    on the `gh pr create` result).
    """

    class FakeResult:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["git", "apply"]:
            if apply_returncode != 0:
                return FakeResult(returncode=apply_returncode, stdout="", stderr="patch does not apply")
            return FakeResult(returncode=0)
        if cmd[:3] == ["gh", "label", "list"]:
            return FakeResult(returncode=0, stdout="skill-self-update\tsomething\n")
        if cmd[:3] == ["gh", "pr", "create"]:
            return FakeResult(returncode=0, stdout="https://github.com/CleanExpo/Pi-Dev-Ops/pull/123\n")
        return FakeResult(returncode=0)

    return fake_run


def test_open_pr_real_mode_runs_well_formed_git_gh_sequence(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_run_recorder(calls))

    lessons = _lessons()
    result = open_pr("skill-authoring-standard", "--- a/x\n+++ b/x\n", lessons, repo_path=tmp_path)

    # Never shells out for real — every recorded call came through our fake.
    assert calls, "expected subprocess.run to have been invoked via the fake"

    # Extract only the git/gh command calls in the order they were made,
    # ignoring the `gh label list` probe (from ensure_label_exists, which
    # is a pre-existing side step, not part of the core PR-opening sequence).
    core_calls = [c for c in calls if c[:3] != ["gh", "label", "list"]]

    assert core_calls[0] == ["git", "checkout", "main"]
    assert core_calls[1] == ["git", "pull", "--ff-only"]

    branch = core_calls[2][-1]
    assert core_calls[2][:3] == ["git", "checkout", "-b"]
    assert branch.startswith("skill-self-update/skill-authoring-standard-")

    assert core_calls[3][:2] == ["git", "apply"]

    assert core_calls[4] == ["git", "add", "skills/skill-authoring-standard/SKILL.md"]

    assert core_calls[5][:2] == ["git", "commit"]
    assert "-m" in core_calls[5]

    assert core_calls[6] == ["git", "push", "-u", "origin", branch]

    pr_create = core_calls[7]
    assert pr_create[:3] == ["gh", "pr", "create"]
    assert "--head" in pr_create
    assert pr_create[pr_create.index("--head") + 1] == branch

    # Branch name is used consistently everywhere it appears.
    assert core_calls[2][-1] == branch
    assert core_calls[6][-1] == branch
    assert pr_create[pr_create.index("--head") + 1] == branch

    # Label + title conventions reach gh pr create specifically.
    assert "--label" in pr_create
    assert pr_create[pr_create.index("--label") + 1] == "skill-self-update"
    assert "--title" in pr_create
    title = pr_create[pr_create.index("--title") + 1]
    assert title.startswith("skill-learn(skill-authoring-standard): ")

    assert result == "https://github.com/CleanExpo/Pi-Dev-Ops/pull/123"


def test_open_pr_real_mode_raises_runtime_error_on_git_apply_failure(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", _fake_run_recorder(calls, apply_returncode=1))

    with pytest.raises(RuntimeError):
        open_pr("skill-authoring-standard", "--- a/x\n+++ b/x\n", _lessons(), repo_path=tmp_path)

    # Failure happens at the git apply step — commit/push/gh pr create must
    # never have been reached.
    called_cmds = [c[:2] for c in calls]
    assert ["git", "commit"] not in called_cmds
    assert ["git", "push"] not in called_cmds
    assert calls[-1][:2] == ["git", "apply"]
