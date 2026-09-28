"""tests/test_mesh_run_record_claim.py — `run_claim` reports every run's outcome and never strands a claim (UNI-2796).

Split from tests/test_mesh_run_record.py at the 300-line size gate. These run
`run_claim` end to end with a stubbed `git worktree` and a real child process,
and pin the lifecycle guarantee: whatever fails — the agent, git, the prompt,
the run record itself — the claim reaches a terminal state, the worktree is
removed, and only closed-set facts are sent.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import hostile_exception as _hostile  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402
from mesh_helpers import secret_token as _token  # noqa: E402
from mesh_helpers import server_only_secret as _server_only_secret  # noqa: E402


def _runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_run_record", "mesh/runner.py")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0.01)
    removed: list = []

    def git(args, **_kw):
        """Stand in for `git worktree add/remove`: make or remove the directory only."""
        target = Path(args[-1])
        if "add" in args:
            target.mkdir(parents=True, exist_ok=True)
        elif "remove" in args:
            removed.append(target)
            shutil.rmtree(target, ignore_errors=True)

    monkeypatch.setattr(mod.subprocess, "run", git)
    calls: list = []
    monkeypatch.setattr(mod, "_api", lambda m, p, b=None: calls.append((p, b or {})) or {})
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    return mod, calls, removed, repo


def _updates(calls):
    return [b for p, b in calls if p == "/api/mesh/claim/update"]


def test_run_claim_reports_the_run_record_of_a_real_failing_agent(monkeypatch, tmp_path):
    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\necho agent-ran\nexit 3\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))

    plan = runner.run_claim({"linear_id": "UNI-X", "repo_dir": str(repo)}, dry_run=False)

    final = _updates(calls)[-1]
    assert plan["state"] == "failed"
    assert final["state"] == "failed"
    assert final["exit_code"] == 3
    assert final["error_code"] == "agent_exit"
    assert "agent-ran" in (tmp_path / "mesh-runs" / f"{final['run_id']}.log").read_text()


def test_a_record_that_cannot_be_built_still_ends_the_claim(monkeypatch, tmp_path):
    """Construction failing after `working` was reported must not strand the claim,
    and the exception's message — round 4's leak — must not be sent."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)

    def boom(*_a, **_k):
        raise OSError("Popen setup failed: " + _server_only_secret())

    monkeypatch.setattr(runner.run_record, "RunRecord", boom)
    runner.run_claim({"linear_id": "UNI-Z", "repo_dir": str(repo)}, dry_run=False)

    assert [b["state"] for b in _updates(calls)] == ["working", "failed"]
    assert _updates(calls)[-1]["error_code"] == "runner_exception_os"
    assert "qwertyuiop" not in repr(calls)
    assert removed, "worktree was not cleaned up"


def test_git_that_cannot_start_still_ends_the_claim(monkeypatch, tmp_path):
    """Round 5: an OSError spawning `git worktree add` used to leave the claim `working`."""
    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)

    def no_git(args, **_kw):
        raise OSError("git spawn failed")

    monkeypatch.setattr(runner.subprocess, "run", no_git)
    runner.run_claim({"linear_id": "UNI-G", "repo_dir": str(repo)}, dry_run=False)
    assert [b["state"] for b in _updates(calls)] == ["working", "failed"]
    assert _updates(calls)[-1]["error_code"] == "worktree_add_failed"


def test_a_prompt_that_cannot_be_built_still_ends_the_claim(monkeypatch, tmp_path):
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)

    def bad_prompt(*_a, **_k):
        raise _hostile(ValueError)("brief carried " + _server_only_secret())

    monkeypatch.setattr(runner, "build_prompt", bad_prompt)
    runner.run_claim({"linear_id": "UNI-P", "repo_dir": str(repo)}, dry_run=False)
    assert [b["state"] for b in _updates(calls)] == ["working", "failed"]
    assert _updates(calls)[-1]["error_code"] == "runner_exception"
    assert "qwertyuiop" not in repr(calls) and "SECRET_QWERTY" not in repr(calls)
    assert removed, "worktree was not cleaned up"


def test_a_claim_failed_before_running_sends_only_its_code(monkeypatch, tmp_path):
    runner, calls, _removed, _repo = _runner(monkeypatch, tmp_path)
    missing = tmp_path / ("not-a-checkout-" + _token())
    missing.mkdir()
    runner.run_claim({"linear_id": "UNI-Y", "repo_dir": str(missing)}, dry_run=False)
    final = _updates(calls)[-1]
    assert final["state"] == "failed"
    assert final["error_code"] == "repo_missing"
    assert _token() not in repr(calls)


def test_a_worktree_removal_failure_still_ends_the_claim(monkeypatch, tmp_path):
    """Round 6: the terminal update used to sit behind an unguarded `git worktree remove`."""
    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)
    real_git = runner.subprocess.run

    def git(args, **kw):
        if "remove" in args:
            raise OSError("remove-spawn-failed")
        return real_git(args, **kw)

    monkeypatch.setattr(runner.subprocess, "run", git)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexit 0\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))
    runner.run_claim({"linear_id": "UNI-R", "repo_dir": str(repo)}, dry_run=False)
    assert [b["state"] for b in _updates(calls)] == ["working", "done"]


def test_a_record_that_fails_to_report_still_ends_the_claim(monkeypatch, tmp_path):
    """Round 6: a log close raising inside fields() used to stop the terminal update."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)

    class Exploding:
        def fields(self, plan):
            raise OSError("log flush failed")

    def run_agent(_make_cmd, _cwd, _base, _run_id, plan, _wait):
        plan["state"] = "done"
        return Exploding()

    monkeypatch.setattr(runner.run_record, "run_agent", run_agent)
    runner.run_claim({"linear_id": "UNI-F", "repo_dir": str(repo)}, dry_run=False)
    assert [b["state"] for b in _updates(calls)] == ["working", "done"]
    assert removed, "worktree was not cleaned up"

