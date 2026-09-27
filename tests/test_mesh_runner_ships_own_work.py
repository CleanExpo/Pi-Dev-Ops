"""tests/test_mesh_runner_ships_own_work.py — a run is `done` only once its work is
on the remote (RA-7780).

The runner used to report `done` whenever the agent exited 0. Shipping was left to
a per-machine Claude Stop hook (`mesh/hooks/mesh_ship.sh`, wired by bootstrap.sh).
On a node without that hook — the Windows PC and the MacBook on 28/09/2026 — the
agent wrote its change, nothing committed or pushed it, `run_claim` then
force-removed the worktree, and the fleet recorded a success whose work no longer
existed anywhere. RA-7780 is that run: `done` on the server, 404 on GitHub.

`mesh/ship_run.py` makes the runner ship the branch it created, on any node, and
turn "nothing reached the remote" into `failed`.

These use REAL git against a local bare remote, because the defect lived in what
git did and did not do. A stubbed `subprocess.run` is exactly what let the old
green control report `done` for a run that shipped nothing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

import ship_run  # noqa: E402

BRANCH = "mesh/testnode/uni-a-1234abcd"


def _git(cwd, *args) -> str:
    """Run git for fixture setup, failing the test loudly on any error."""
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def fleet(tmp_path):
    """A bare `origin`, a checkout of it, and a mesh worktree on a fresh branch —
    the same shape `run_claim` builds before it launches the agent."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    repo = tmp_path / "checkout"
    _git(tmp_path, "clone", "-q", str(origin), str(repo))
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "README").write_text("base\n")
    _git(repo, "add", "README")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, str(wt))
    return repo, wt, origin


def _remote_has(origin, branch) -> str:
    return subprocess.run(["git", "-C", str(origin), "rev-parse", "--verify", "-q",
                           f"refs/heads/{branch}"], capture_output=True, text=True).stdout.strip()


def test_uncommitted_agent_output_is_committed_and_pushed(fleet):
    """THE RA-7780 CASE: the agent wrote a file and committed nothing."""
    repo, wt, origin = fleet
    (wt / "marker").write_text("PC active\n")

    error = ship_run.ship(repo, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error is None
    assert _remote_has(origin, BRANCH) == _git(wt, "rev-parse", "HEAD")
    assert _git(wt, "status", "--porcelain") == ""


def test_work_the_agent_committed_itself_is_pushed(fleet):
    """RA-7376's shape: a disciplined agent commits, leaving a clean tree."""
    repo, wt, origin = fleet
    (wt / "marker").write_text("x\n")
    _git(wt, "add", "marker")
    _git(wt, "commit", "-q", "-m", "agent's own commit")

    assert ship_run.ship(repo, wt, BRANCH, "UNI-A", "TESTNODE") is None
    assert _remote_has(origin, BRANCH) == _git(wt, "rev-parse", "HEAD")


def test_a_run_that_changed_nothing_is_an_error_and_pushes_nothing(fleet):
    """Exit 0 with no change is not a delivered ticket, and must not read as one."""
    repo, wt, origin = fleet

    error = ship_run.ship(repo, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and "no commits" in error
    assert _remote_has(origin, BRANCH) == ""


def test_a_failed_push_is_an_error(fleet):
    """The local commit exists but the remote never got it — still not shipped."""
    repo, wt, origin = fleet
    (wt / "marker").write_text("x\n")
    _git(repo, "remote", "set-url", "origin", str(origin.parent / "gone.git"))

    error = ship_run.ship(repo, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and error.startswith("push failed")


def test_only_mesh_work_branches_are_ever_pushed(fleet):
    """Same guard as mesh_ship.sh: never push main or a review branch."""
    repo, wt, _origin = fleet
    (wt / "marker").write_text("x\n")

    error = ship_run.ship(repo, wt, "main", "UNI-A", "TESTNODE")

    assert error and "refusing" in error


# ── run_claim wiring ─────────────────────────────────────────────────────────


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The runner with side effects neutralised; each test decides what ship returns."""
    from mesh_helpers import load_module
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = load_module("mesh_runner_ships", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    return mod


def _run(runner, monkeypatch, tmp_path, ship_result):
    from mesh_helpers import ImmediateProc
    reported = []
    runner._api = lambda m, p, b=None: reported.append((b or {}).get("state")) or {}
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: ImmediateProc())
    monkeypatch.setattr(runner.ship_run, "ship", lambda *a, **k: ship_result)
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    plan = runner.run_claim({"linear_id": "UNI-A", "repo_dir": str(repo)}, dry_run=False)
    return plan, [s for s in reported if s]


def test_run_claim_reports_failed_when_nothing_shipped(runner, monkeypatch, tmp_path):
    plan, reported = _run(runner, monkeypatch, tmp_path, "no commits: agent changed nothing")

    assert plan["state"] == "failed"
    assert "no commits" in plan["error"]
    assert reported == ["working", "failed"]


def test_run_claim_reports_done_only_after_a_ship(runner, monkeypatch, tmp_path):
    """GREEN CONTROL: a fix that failed every run would pass the test above."""
    plan, reported = _run(runner, monkeypatch, tmp_path, None)

    assert plan["state"] == "done", plan
    assert reported == ["working", "done"]
