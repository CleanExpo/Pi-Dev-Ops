"""tests/test_mesh_run_journal.py — a mesh run stops losing work (UNI-2963, Durable Agent Harness slice 1).

Three losses in the live runner, each pinned here against REAL git:

  * WIP: a run that did not end `done` force-removed its worktree, and whatever the
    agent had not committed went with it. Only `done` ever committed (ship_run.settle).
  * HEARTBEAT: nothing on disk said which claim a run held, or that its runner was
    still alive, so nothing could tell a live run from one whose runner was killed.
  * RECONCILE: a runner killed with SIGKILL never reaches `run_claim`'s finally. Its
    claim sat `working` for good: the reaper skips a machine whose heartbeat daemon is
    fresh, and `fleet_state.my_claims` only hands back `claimed` rows.

The kill -9 end-to-end proof, with a real runner process, is
tests/test_mesh_kill9_recovery.py.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mesh"))

from mesh_helpers import load_module  # noqa: E402

from test_mesh_kill9_recovery import HOST, dead_pid, git, make_repo, show, sleeper  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The runner on real git with only the network faked; worktrees under tmp_path."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = load_module("mesh_runner_journal", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", HOST)
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "home" / "state.json")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "MESH_KILL_POLL_SECONDS", 0.02)
    monkeypatch.setattr(mod.claim_lifecycle, "temp_root", lambda: tmp_path / "wts")
    (tmp_path / "wts").mkdir()
    mod.calls = []
    monkeypatch.setattr(mod, "_api", lambda m, p, b=None: mod.calls.append((p, dict(b or {}))) or {})
    mod.repo = make_repo(tmp_path)
    return mod


def agent(runner, monkeypatch, tmp_path, body: str) -> None:
    script = tmp_path / "agent.sh"
    script.write_text("#!/bin/sh\n" + body + "\n")
    script.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(script))


def run(runner):
    claim = {"linear_id": "UNI-W", "id": "11111111-2222-3333-4444-555555555555",
             "repo_dir": str(runner.repo), "title": "t", "description": "d"}
    return runner.run_claim(claim, dry_run=False)


def states(runner):
    return [b.get("state") for p, b in runner.calls if p == "/api/mesh/claim/update"]


def journals(runner) -> list:
    return sorted((runner.STATE_FILE.parent / "mesh-runs").glob("*.json"))


# ── WIP on every exit ────────────────────────────────────────────────────────

def test_wip_of_a_failed_run_survives_on_its_branch(runner, monkeypatch, tmp_path):
    """THE LOSS: the agent wrote work, exited non-zero, and the worktree was force-removed."""
    agent(runner, monkeypatch, tmp_path, "echo half-done > wip.txt\nexit 3")

    plan = run(runner)

    assert plan["state"] == "failed"
    assert show(runner.repo, plan["branch"], "wip.txt") == "half-done\n"
    assert not any((tmp_path / "wts").iterdir()), "the worktree should still be removed"
    assert journals(runner) == [], "an ended run must clear its journal"


def test_wip_of_a_hard_stop_release_is_committed(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, f"echo partial > wip.txt\ntouch '{runner.HARD_STOP}'\nexec sleep 30")

    plan = run(runner)

    assert plan["state"] == "released"
    assert states(runner) == ["working", "released"]
    assert show(runner.repo, plan["branch"], "wip.txt") == "partial\n"


def test_wip_commit_leaves_the_done_path_as_it_was(runner, monkeypatch, tmp_path):
    """GREEN CONTROL: `done` still ships exactly the one commit settle makes."""
    agent(runner, monkeypatch, tmp_path, "echo finished > out.txt")

    plan = run(runner)

    assert plan["state"] == "done", plan
    origin = tmp_path / "origin.git"
    assert git(origin, "rev-list", "--count", f"main..{plan['branch']}") == "1"
    assert show(origin, plan["branch"], "out.txt") == "finished\n"


def test_wip_is_not_touched_while_the_agent_may_still_be_running(runner, monkeypatch, tmp_path):
    """An unstoppable agent keeps its claim and worktree; committing under it is not safe either."""
    agent(runner, monkeypatch, tmp_path, "echo live > wip.txt\nexit 1")
    monkeypatch.setattr(runner.run_record, "unreaped", lambda rec: True)

    plan = run(runner)

    assert show(runner.repo, plan["branch"], "wip.txt") is None
    worktrees = list((tmp_path / "wts").iterdir())
    assert len(worktrees) == 1 and (worktrees[0] / "wip.txt").exists()
    assert len(journals(runner)) == 1, "the journal must outlive the runner for a later reconcile"


# ── per-run heartbeat ────────────────────────────────────────────────────────

def test_heartbeat_journal_exists_before_the_working_update(runner, monkeypatch, tmp_path):
    """Journal before act: a kill right after `working` must still leave a record."""
    agent(runner, monkeypatch, tmp_path, "exit 1")
    seen: list = []

    def api(_m, path, body=None):
        if (body or {}).get("state") == "working":
            seen.extend(json.loads(p.read_text()) for p in journals(runner))
            seen.append(body)
        return {}

    monkeypatch.setattr(runner, "_api", api)
    plan = run(runner)

    entry, working = seen
    assert entry["claim_id"] == plan["claim_id"] and entry["branch"] == plan["branch"]
    assert entry["host"] == HOST and entry["owner_pid"] == os.getpid()
    assert entry["worktree"] and entry["repo_dir"] == str(runner.repo)
    assert working["run_id"] == entry["run_id"]


def test_heartbeat_refreshes_ts_and_names_the_agent(runner, monkeypatch, tmp_path):
    pidfile = tmp_path / "agent.pid"
    agent(runner, monkeypatch, tmp_path, f"echo $$ > '{pidfile}'\nsleep 1\nexit 1")
    monkeypatch.setattr(runner.run_journal, "BEAT_SECONDS", 0.05)
    written: list = []
    real = runner.run_journal.write

    def spy(base_dir, run_id, entry):
        written.append(dict(entry))
        return real(base_dir, run_id, entry)

    monkeypatch.setattr(runner.run_journal, "write", spy)
    run(runner)

    pid = int(pidfile.read_text())
    named = [e for e in written if e.get("agent_pid") == pid]
    assert named and named[-1]["agent_pgid"] == pid
    stamps = [e["ts"] for e in named]
    assert len(stamps) >= 3 and stamps == sorted(stamps) and stamps[-1] > stamps[0]


# ── startup reconcile ────────────────────────────────────────────────────────

def orphan(runner, tmp_path, **override):
    """The state a SIGKILLed runner leaves: a journal and a worktree with uncommitted work."""
    run_id = "abcd1234"
    branch = f"mesh/testnode/uni-r-{run_id}"
    wt = tmp_path / "wts" / f"mesh-UNI-R-{run_id}"
    git(runner.repo, "worktree", "add", "-q", "-b", branch, str(wt))
    (wt / "wip.txt").write_text("unsaved\n")
    entry = {"run_id": run_id, "linear_id": "UNI-R", "claim_id": "c-1", "branch": branch,
             "repo_dir": str(runner.repo), "worktree": str(wt), "host": HOST,
             "owner_pid": dead_pid(), "agent_pid": dead_pid(), "agent_pgid": dead_pid(),
             "phase": "agent", "ts": time.time()}
    entry.update(override)
    path = runner.STATE_FILE.parent / "mesh-runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry))
    return entry, wt, path


def reconcile(runner, reply=None):
    calls: list = []
    out = runner.run_journal.reconcile(runner.STATE_FILE.parent, HOST,
                                       lambda m, p, b=None: calls.append(b) or (reply or {}))
    return out, calls


def test_reconcile_releases_a_dead_runs_claim_and_keeps_its_work(runner, tmp_path):
    entry, wt, path = orphan(runner, tmp_path)

    out, calls = reconcile(runner)

    assert [(c["state"], c["claim_id"], c["host"], c["linear_id"]) for c in calls] == [
        ("released", "c-1", HOST, "UNI-R")]
    assert show(runner.repo, entry["branch"], "wip.txt") == "unsaved\n"
    assert not wt.exists() and not path.exists()
    assert out and out[0]["released"] is True


def test_reconcile_leaves_a_live_runners_claim_alone(runner, tmp_path):
    live = sleeper()
    try:
        entry, wt, path = orphan(runner, tmp_path, owner_pid=live.pid)
        out, calls = reconcile(runner)
    finally:
        live.kill()
        live.wait()
    assert calls == [] and wt.exists() and path.exists()
    assert show(runner.repo, entry["branch"], "wip.txt") is None


def test_reconcile_waits_for_a_surviving_agent_group(runner, tmp_path):
    """SIGKILL ends the runner, not the agent: it leads its own session and keeps writing."""
    live = sleeper()
    try:
        _entry, wt, path = orphan(runner, tmp_path, agent_pid=live.pid, agent_pgid=live.pid)
        _out, calls = reconcile(runner)
    finally:
        live.kill()
        live.wait()
    assert calls == [] and wt.exists() and path.exists()


def test_reconcile_never_touches_another_hosts_journal(runner, tmp_path):
    _entry, wt, path = orphan(runner, tmp_path, host="OTHERNODE")
    _out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()


def test_reconcile_with_no_journal_does_nothing(runner):
    out, calls = reconcile(runner)
    assert out == [] and calls == []


def test_reconcile_holds_an_agent_that_may_have_started_unrecorded(runner, tmp_path):
    _entry, wt, path = orphan(runner, tmp_path, phase="launching", agent_pid=None, agent_pgid=None)
    _out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()


def test_reconcile_holds_a_run_killed_before_its_agent_was_recorded(runner, tmp_path):  # review r2 P0
    _entry, wt, path = orphan(runner, tmp_path, phase="preparing", agent_pid=None, agent_pgid=None)
    _out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()


def test_reconcile_a_stale_heartbeat_never_outvotes_a_live_runner_pid(runner, tmp_path):
    """Review r1 P0: a live owner whose heartbeat writes failed was released. A pid reused
    after a reboot now holds the claim instead, which fails safe."""
    live = sleeper()
    try:
        _entry, wt, path = orphan(runner, tmp_path, owner_pid=live.pid, ts=time.time() - 10 * 24 * 3600)
        _out, calls = reconcile(runner)
    finally:
        live.kill()
        live.wait()
    assert calls == [] and wt.exists() and path.exists()


def test_reconcile_keeps_the_journal_when_the_server_rejects_the_release(runner, tmp_path):
    entry, wt, path = orphan(runner, tmp_path)
    out, calls = reconcile(runner, reply={"error": "HTTP 502"})
    assert calls and path.exists(), "an unreleased claim must be retried on the next start"
    assert show(runner.repo, entry["branch"], "wip.txt") == "unsaved\n"
    assert out[0]["released"] is False


def test_reconcile_runs_at_startup_before_any_claim(runner, monkeypatch):
    order: list = []

    class Stop(BaseException):  # on_start absorbs an Exception (review r1 P2); this must escape
        pass

    def fake_reconcile(base_dir, host, api):
        order.append(("reconcile", host))
        raise Stop

    monkeypatch.setattr(runner, "default_repo_dir_problem", lambda: "")
    monkeypatch.setattr(runner.run_journal, "reconcile", fake_reconcile)
    monkeypatch.setattr(runner, "get_work", lambda: order.append("get_work") or [])
    monkeypatch.setattr(sys, "argv", ["runner.py", "--once"])
    with pytest.raises(Stop):
        runner.main()
    assert order == [("reconcile", HOST)]


def test_reconcile_does_not_run_under_hard_stop(runner, monkeypatch):
    runner.HARD_STOP.touch()
    monkeypatch.setattr(runner, "default_repo_dir_problem", lambda: "")
    monkeypatch.setattr(runner.run_journal, "reconcile",
                        lambda *a: pytest.fail("reconcile ran under HARD_STOP"))
    monkeypatch.setattr(sys, "argv", ["runner.py", "--once"])
    assert runner.main() == 0
