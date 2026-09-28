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
    """A bare `origin`, a checkout with two commits, and a mesh worktree on a fresh
    branch. `start` is read before `worktree add`, exactly as `run_claim` reads it
    before the agent launches."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    repo = tmp_path / "checkout"
    _git(tmp_path, "clone", "-q", str(origin), str(repo))
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    for text in ("base\n", "second\n"):
        (repo / "README").write_text(text)
        _git(repo, "add", "README")
        _git(repo, "commit", "-q", "-m", text.strip())
    _git(repo, "push", "-q", "origin", "HEAD:refs/heads/main")
    start = ship_run.start_point(repo)
    wt = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", "-b", BRANCH, str(wt))
    return repo, wt, origin, start


def _remote_has(origin, branch) -> str:
    return subprocess.run(["git", "-C", str(origin), "rev-parse", "--verify", "-q",
                           f"refs/heads/{branch}"], capture_output=True, text=True).stdout.strip()


def test_uncommitted_agent_output_is_committed_and_pushed(fleet):
    """THE RA-7780 CASE: the agent wrote a file and committed nothing."""
    _repo, wt, origin, start = fleet
    (wt / "marker").write_text("PC active\n")

    error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error is None
    assert _remote_has(origin, BRANCH) == _git(wt, "rev-parse", "HEAD")
    assert _git(wt, "status", "--porcelain") == ""


def test_work_the_agent_committed_itself_is_pushed(fleet):
    """RA-7376's shape: a disciplined agent commits, leaving a clean tree."""
    _repo, wt, origin, start = fleet
    (wt / "marker").write_text("x\n")
    _git(wt, "add", "marker")
    _git(wt, "commit", "-q", "-m", "agent's own commit")

    assert ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE") is None
    assert _remote_has(origin, BRANCH) == _git(wt, "rev-parse", "HEAD")


def test_a_run_that_changed_nothing_is_an_error_and_pushes_nothing(fleet):
    """Exit 0 with no change is not a delivered ticket, and must not read as one."""
    _repo, wt, origin, start = fleet

    error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and "no commits" in error
    assert _remote_has(origin, BRANCH) == ""


def test_an_empty_run_stays_an_error_when_the_checkout_head_moves_back(fleet):
    """Codex review round 1, P1: the base used to be the checkout's HEAD read at ship
    time, so moving that HEAD behind the run's start made an unchanged worktree look
    ahead. The runner now holds the start from before the agent launched."""
    repo, wt, origin, start = fleet
    _git(repo, "checkout", "-q", "--detach", "HEAD~1")

    error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and "no commits" in error
    assert _remote_has(origin, BRANCH) == ""


def test_an_empty_run_stays_an_error_when_the_agent_rewrites_the_reflog(fleet):
    """Codex review round 2, P1: a reflog-derived start was agent-writable. This is
    that reproduction, run from inside the worktree the agent controls: expire the
    branch reflog, then move the branch away and back so its only entry is newer."""
    _repo, wt, origin, start = fleet
    _git(wt, "reflog", "expire", "--expire=now", f"refs/heads/{BRANCH}")
    _git(wt, "reset", "-q", "--hard", "HEAD~1")
    _git(wt, "reset", "-q", "--hard", start.sha)

    error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and "no commits" in error
    assert _remote_has(origin, BRANCH) == ""


def test_an_unreadable_start_ships_nothing(fleet):
    """No start point means no proof of new work, so it must fail closed."""
    _repo, wt, origin, start = fleet
    (wt / "marker").write_text("x\n")

    error = ship_run.ship(start._replace(sha=""), wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and "no commits" in error
    assert _remote_has(origin, BRANCH) == ""


def test_an_agent_redirected_push_url_still_ships_to_the_real_origin(fleet, tmp_path):
    """Codex review round 3, P1: `remote set-url --push origin <decoy>` inside the
    worktree sent the run to the decoy while settle read `done`. The runner pushes
    to the URL it read before the agent launched, so origin config cannot redirect it."""
    _repo, wt, origin, start = fleet
    decoy = tmp_path / "decoy.git"
    _git(tmp_path, "init", "-q", "--bare", str(decoy))
    _git(wt, "remote", "set-url", "--push", "origin", str(decoy))
    (wt / "marker").write_text("x\n")

    assert ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE") is None
    assert _remote_has(origin, BRANCH) == _git(wt, "rev-parse", "HEAD")
    assert _remote_has(decoy, BRANCH) == ""


def test_a_ship_publishes_the_run_branch_and_nothing_else(fleet):
    """Codex review round 3, P1: with `push.followTags` set in the worktree, the
    explicit branch push also published an agent-created annotated tag."""
    _repo, wt, origin, start = fleet
    (wt / "marker").write_text("x\n")
    _git(wt, "add", "marker")
    _git(wt, "commit", "-q", "-m", "work")
    _git(wt, "tag", "-a", "outside-scope", "-m", "t")
    _git(wt, "config", "push.followTags", "true")

    assert ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE") is None
    refs = _git(origin, "for-each-ref", "--format=%(refname)").split()
    assert refs == ["refs/heads/main", f"refs/heads/{BRANCH}"]


def test_an_unreadable_worktree_status_is_an_error_not_a_clean_tree(fleet):
    """Codex review round 4, P1: `git status` failing (here, a corrupt index) printed
    nothing, which read as "nothing left to commit". The committed half shipped, the
    rest was lost, and the run read `done`."""
    _repo, wt, origin, start = fleet
    (wt / "a").write_text("a\n")
    _git(wt, "add", "a")
    _git(wt, "commit", "-q", "-m", "a")
    (wt / "leftover").write_text("x\n")
    Path(_git(wt, "rev-parse", "--git-path", "index")).write_bytes(b"not an index")

    error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and error.startswith("status failed")
    assert _remote_has(origin, BRANCH) == ""


def test_a_failed_stage_is_an_error_not_a_partial_commit(fleet):
    """Codex review round 4, P1: `git add -A` failing on an unreadable file still let
    the commit run, shipping only what had been staged before."""
    _repo, wt, origin, start = fleet
    (wt / "staged").write_text("s\n")
    _git(wt, "add", "staged")
    locked = wt / "unreadable"
    locked.write_text("u\n")
    locked.chmod(0)
    try:
        error = ship_run.ship(start, wt, BRANCH, "UNI-A", "TESTNODE")
    finally:
        locked.chmod(0o644)

    assert error and error.startswith("stage failed")
    assert _remote_has(origin, BRANCH) == ""


def test_a_failed_push_is_an_error(fleet):
    """The local commit exists but the remote never got it — still not shipped."""
    _repo, wt, origin, start = fleet
    (wt / "marker").write_text("x\n")
    gone = start._replace(url=str(origin.parent / "gone.git"))

    error = ship_run.ship(gone, wt, BRANCH, "UNI-A", "TESTNODE")

    assert error and error.startswith("push failed")


def test_only_mesh_work_branches_are_ever_pushed(fleet):
    """Same guard as mesh_ship.sh: never push main or a review branch."""
    _repo, wt, _origin, start = fleet
    (wt / "marker").write_text("x\n")

    error = ship_run.ship(start, wt, "main", "UNI-A", "TESTNODE")

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
    """Run one claim with the agent stubbed to exit 0. Every start_point() read gets a
    fresh value and every step lands in `events`, so a re-read after the agent shows."""
    from mesh_helpers import ImmediateProc
    reported, events = [], []

    def _read_start(repo_dir):
        events.append(f"start-read-{sum(e.startswith('start-read') for e in events) + 1}")
        return events[-1]

    def _agent(*a, **k):
        events.append("agent")
        return ImmediateProc()

    runner._api = lambda m, p, b=None: reported.append((b or {}).get("state")) or {}
    monkeypatch.setattr(runner.subprocess, "Popen", _agent)
    monkeypatch.setattr(runner.ship_run, "start_point", _read_start)
    monkeypatch.setattr(runner.ship_run, "ship",
                        lambda start, *a: events.append(f"ship:{start}") or ship_result)
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    plan = runner.run_claim({"linear_id": "UNI-A", "repo_dir": str(repo)}, dry_run=False)
    return plan, [s for s in reported if s], events


def test_run_claim_reports_failed_when_nothing_shipped(runner, monkeypatch, tmp_path):
    plan, reported, _ = _run(runner, monkeypatch, tmp_path, "no commits: agent changed nothing")

    assert plan["state"] == "failed"
    assert "no commits" in plan["error"]
    assert reported == ["working", "failed"]


def test_run_claim_reports_done_only_after_a_ship(runner, monkeypatch, tmp_path):
    """GREEN CONTROL: a fix that failed every run would pass the test above."""
    plan, reported, _ = _run(runner, monkeypatch, tmp_path, None)

    assert plan["state"] == "done", plan
    assert reported == ["working", "done"]


def test_run_claim_ships_from_the_start_it_read_before_the_agent(runner, monkeypatch, tmp_path):
    """Codex review round 4, P0: a constant stub let a re-read AFTER the agent pass.
    The start must be read exactly once, before the agent, and that read is shipped."""
    _plan, _reported, events = _run(runner, monkeypatch, tmp_path, None)

    assert events == ["start-read-1", "agent", "ship:start-read-1"]
