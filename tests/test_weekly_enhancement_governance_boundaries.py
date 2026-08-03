"""RED regressions for weekly-loop governance and mutation gates.

All provider, git and GitHub interactions are fakes.  The current implementation
should fail these assertions until each gate is enforced before mutation.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "weekly_enhancement_loop.py"


@pytest.fixture
def loop(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "FAKE_PROVIDER_CREDENTIAL_FOR_TEST")
    monkeypatch.setenv("GH_ENHANCE_PAT", "FAKE_GITHUB_CREDENTIAL_FOR_TEST")
    name = "weekly_enhancement_loop_governance_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_kill_switch_tripped", lambda: None)
    return module


def cp(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def arrange_changed_repo(loop, monkeypatch, tmp_path, *, status=" M safe.py", review="PASS score=10"):
    git_calls = []
    pr_calls = []
    phases = []
    monkeypatch.setattr(loop, "WORKSPACE_ROOT", tmp_path / "workspaces")
    monkeypatch.setattr(loop, "_clone", lambda repo, dest: dest.mkdir(parents=True, exist_ok=True))

    def fake_phase(role, model, prompt, cwd, timeout, spent):
        phases.append(role)
        return review if role == "evaluator" else "fake bounded output"

    def fake_git(cwd, *args):
        git_calls.append(args)
        if args == ("status", "--porcelain"):
            return cp(args, stdout=status)
        return cp(args)

    def fake_open_pr(repo, branch, date):
        pr_calls.append((repo, branch, date))
        return f"https://github.com/{repo}/pull/123"

    monkeypatch.setattr(loop, "run_phase", fake_phase)
    monkeypatch.setattr(loop, "_git", fake_git)
    monkeypatch.setattr(loop, "_open_pr", fake_open_pr)
    return git_calls, pr_calls, phases


def mutating_git_calls(calls):
    mutators = {"checkout", "add", "commit", "push"}
    return [args for args in calls if any(part in mutators for part in args)]


def test_dry_run_performs_no_commit_push_or_pr_mutation(loop, monkeypatch, tmp_path):
    git_calls, pr_calls, _ = arrange_changed_repo(loop, monkeypatch, tmp_path)

    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", True, {"usd": 0.0})

    assert result["outcome"] == "dry-run"
    assert mutating_git_calls(git_calls) == []
    assert pr_calls == []


def test_protected_path_diff_blocks_before_staging(loop, monkeypatch, tmp_path):
    git_calls, pr_calls, _ = arrange_changed_repo(
        loop, monkeypatch, tmp_path, status=" M app/server/config.py\n M safe.py"
    )

    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert result["outcome"].startswith("blocked-protected-path:")
    assert mutating_git_calls(git_calls) == []
    assert pr_calls == []


def test_changed_file_count_ceiling_blocks_before_staging(loop, monkeypatch, tmp_path):
    status = "\n".join(f" M file_{index}.py" for index in range(6))
    git_calls, pr_calls, _ = arrange_changed_repo(loop, monkeypatch, tmp_path, status=status)

    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert result["outcome"] == "blocked-file-count: 6 > 5"
    assert mutating_git_calls(git_calls) == []
    assert pr_calls == []


@pytest.mark.parametrize("failed_operation", ["checkout", "add", "commit"])
def test_every_git_failure_stops_all_later_mutation(loop, monkeypatch, tmp_path, failed_operation):
    git_calls, pr_calls, _ = arrange_changed_repo(loop, monkeypatch, tmp_path)

    def failing_git(cwd, *args):
        git_calls.append(args)
        if args == ("status", "--porcelain"):
            return cp(args, stdout=" M safe.py")
        if failed_operation in args:
            return cp(args, returncode=7, stderr=f"fake {failed_operation} failure")
        return cp(args)

    git_calls.clear()
    monkeypatch.setattr(loop, "_git", failing_git)
    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert result["outcome"].startswith(f"git-failed-{failed_operation}:")
    assert not any("push" in args for args in git_calls)
    assert pr_calls == []


def test_negative_evaluator_verdict_blocks_commit_and_push(loop, monkeypatch, tmp_path):
    git_calls, pr_calls, phases = arrange_changed_repo(
        loop, monkeypatch, tmp_path, review="FAIL score=2 unsafe diff"
    )

    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert phases[-1] == "evaluator"
    assert result["outcome"].startswith("review-failed:")
    assert mutating_git_calls(git_calls) == []
    assert pr_calls == []


def test_repository_specific_tests_are_required_before_commit(loop, monkeypatch, tmp_path):
    git_calls, pr_calls, _ = arrange_changed_repo(loop, monkeypatch, tmp_path)
    test_calls = []

    def fake_repo_tests(repo, cwd):
        test_calls.append((repo, cwd))
        return cp(["fake-repo-test"], returncode=1, stderr="fake repository test failure")

    monkeypatch.setattr(loop, "_run_repo_tests", fake_repo_tests, raising=False)
    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert len(test_calls) == 1
    assert result["outcome"].startswith("tests-failed:")
    assert mutating_git_calls(git_calls) == []
    assert pr_calls == []


def test_duplicate_weekly_branch_and_pr_are_skipped_idempotently(loop, monkeypatch, tmp_path):
    git_calls, pr_calls, _ = arrange_changed_repo(loop, monkeypatch, tmp_path)
    branch_creations = {"count": 0}

    def duplicate_aware_git(cwd, *args):
        git_calls.append(args)
        if args == ("status", "--porcelain"):
            return cp(args, stdout=" M safe.py")
        if "checkout" in args:
            branch_creations["count"] += 1
            if branch_creations["count"] > 1:
                return cp(args, returncode=128, stderr="fake branch already exists")
        return cp(args)

    git_calls.clear()
    monkeypatch.setattr(loop, "_git", duplicate_aware_git)
    first = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})
    second = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert first["outcome"] == "pr-opened"
    assert second["outcome"] == "duplicate-skipped"
    assert len(pr_calls) == 1


def test_null_pr_creation_result_is_never_classified_pr_opened(loop, monkeypatch, tmp_path):
    _, _, _ = arrange_changed_repo(loop, monkeypatch, tmp_path)
    monkeypatch.setattr(loop, "_open_pr", lambda repo, branch, date: None)

    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert result["pr"] is None
    assert result["outcome"] != "pr-opened"


def test_mismatched_github_pr_readback_is_never_classified_pr_opened(loop, monkeypatch, tmp_path):
    arrange_changed_repo(loop, monkeypatch, tmp_path)
    readbacks = []

    def fake_readback(repo, branch, pr_url):
        readbacks.append((repo, branch, pr_url))
        return {"url": pr_url, "repo": "OtherOrg/OtherRepo", "head": "wrong-branch", "state": "OPEN"}

    monkeypatch.setattr(loop, "_read_back_pr", fake_readback, raising=False)
    result = loop.enhance_repo("CleanExpo/Pi-Dev-Ops", False, {"usd": 0.0})

    assert len(readbacks) == 1
    assert result["outcome"].startswith("pr-readback-mismatch:")


def test_main_treats_pr_opened_without_verified_pr_as_failure(loop, monkeypatch, tmp_path):
    monkeypatch.setattr(loop, "_openrouter_key", lambda: "FAKE")
    monkeypatch.setattr(loop, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(loop, "load_repos", lambda: ["CleanExpo/Pi-Dev-Ops"])
    monkeypatch.setattr(
        loop,
        "enhance_repo",
        lambda repo, dry_run, spent: {"repo": repo, "outcome": "pr-opened", "pr": None},
    )
    monkeypatch.setattr(sys, "argv", ["weekly_enhancement_loop.py"])

    assert loop.main() == 1
