# ruff: noqa: F811
"""tests/test_mesh_run_journal_review.py — review round 1 of UNI-2963 (Codex, FAIL at 0dc92e2e).

One test (or more) per blocking finding, each written to fail on 0dc92e2e:

  P0 WIP-ERROR-DATA-LOSS        a failed WIP commit still reported, removed and forgot
  P0 DETACHED-WIP-LOST          WIP committed on a detached HEAD became unreachable
  P0 LIVE-RUNNER-FALSE-RELEASE  a stale heartbeat outvoted a live runner pid
  P0 NO-PGID-LIVE-DESCENDANT    no process group + a dead agent pid released the claim
  P0 GROUP-GUARD-TEST-BLIND     the group guard could be deleted with every test green
  P1 ORPHAN-RELEASE-BEFORE-WIP  reconcile released a claim whose work it failed to keep
  P1 MISSING-JOURNAL-ACCEPTED   the runner reported `working` with no journal on disk
  P1 CLEAR-RACE-RESURRECTS      a late heartbeat write recreated a cleared journal
  P2                            a malformed journal crashed reconcile; concurrent settles
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_mesh_kill9_recovery import git, show, sleeper  # noqa: E402
from test_mesh_run_journal import agent, journals, orphan, reconcile, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


def _refs_with(repo, name, content) -> list:
    """Every branch whose tree has `name` with `content`."""
    refs = git(repo, "for-each-ref", "--format=%(refname)", "refs/heads/").splitlines()
    return [r for r in refs if show(repo, r, name) == content]


# ── P0 WIP-ERROR-DATA-LOSS ───────────────────────────────────────────────────

def test_review_a_failed_wip_commit_holds_claim_worktree_and_journal(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo precious > wip.txt\nexit 1")
    monkeypatch.setattr(runner.run_journal.ship_run, "commit_leftovers",
                        lambda *a, **k: "stage failed: disk full")

    run(runner)

    assert states(runner) == ["working"], "a claim whose work was not kept must stay held"
    worktrees = list((tmp_path / "wts").iterdir())
    assert len(worktrees) == 1 and (worktrees[0] / "wip.txt").read_text() == "precious\n"
    assert len(journals(runner)) == 1


# ── P0 DETACHED-WIP-LOST ─────────────────────────────────────────────────────

def test_review_wip_on_a_detached_head_stays_reachable(runner, monkeypatch, tmp_path):
    """The agent detaches, commits a.txt itself, then leaves b.txt uncommitted."""
    agent(runner, monkeypatch, tmp_path, "\n".join([
        "git checkout -q --detach", "echo a > a.txt", "git add a.txt",
        "git -c user.name=a -c user.email=a@x.invalid commit -q -m a", "echo b > b.txt", "exit 1"]))

    plan = run(runner)

    assert not any((tmp_path / "wts").iterdir()), "kept work lets the worktree go"
    kept = _refs_with(runner.repo, "b.txt", "b\n")
    assert kept and all(r.startswith(f"refs/heads/{plan['branch']}") for r in kept), kept
    assert show(runner.repo, kept[0], "a.txt") == "a\n"


def test_review_wip_on_another_branch_stays_reachable(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "git checkout -q -b elsewhere\necho c > c.txt\nexit 1")

    plan = run(runner)

    kept = [r for r in _refs_with(runner.repo, "c.txt", "c\n") if r.startswith(f"refs/heads/{plan['branch']}")]
    assert kept, "the WIP must hang off the run's own mesh/ branch name"


def test_review_an_unverified_wip_ref_holds_the_claim(runner, monkeypatch, tmp_path):
    """If the WIP ref cannot be created, nothing may claim the work is kept."""
    agent(runner, monkeypatch, tmp_path, "git checkout -q --detach\necho d > d.txt\nexit 1")
    ship_run, real = runner.run_journal.ship_run, runner.run_journal.ship_run._git
    monkeypatch.setattr(ship_run, "_git", lambda wt, *a: subprocess.CompletedProcess(a, 1, "", "locked")
                        if a[0] == "update-ref" else real(wt, *a))

    run(runner)

    assert states(runner) == ["working"]
    assert len(list((tmp_path / "wts").iterdir())) == 1 and len(journals(runner)) == 1


# ── P0 LIVE-RUNNER-FALSE-RELEASE ─────────────────────────────────────────────

@pytest.mark.parametrize("phase", ["agent", "preparing"])
def test_review_a_live_owner_always_wins_over_a_stale_heartbeat(runner, tmp_path, phase):
    live = sleeper()
    try:
        stale = time.time() - 10 * 24 * 3600
        extra = {} if phase == "agent" else {"agent_pid": None, "agent_pgid": None}
        _entry, wt, path = orphan(runner, tmp_path, owner_pid=live.pid, ts=stale, phase=phase, **extra)
        _out, calls = reconcile(runner)
    finally:
        live.kill()
        live.wait()
    assert calls == [] and wt.exists() and path.exists()


def test_review_heartbeat_write_failures_are_surfaced(runner, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(runner.run_journal, "write", lambda *a: False)
    beat = runner.run_journal.Beat(tmp_path, "abcd1234", {"phase": "agent"})
    beat.beat()
    beat.beat()
    assert beat.write_failures == 2
    assert "heartbeat" in capsys.readouterr().err


# ── P0 NO-PGID-LIVE-DESCENDANT and GROUP-GUARD-TEST-BLIND ───────────────────

def test_review_no_process_group_holds_the_claim(runner, tmp_path):
    """Without a group there is no proof the agent's descendants are gone (the Windows path)."""
    _entry, wt, path = orphan(runner, tmp_path, agent_pgid=None)
    out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()
    assert out[0]["held"] == "no process group to prove the agent's descendants gone", out


def test_review_a_dead_leader_with_a_live_group_holds_the_claim(runner, tmp_path):
    """The direct agent pid is DEAD and reaped; only its group survives. Only the group
    guard can hold this, so deleting that guard must turn this test red."""
    leader = subprocess.Popen(["sh", "-c", "sleep 60 & exit 0"], start_new_session=True)
    leader.wait()
    try:
        assert runner.run_journal.left_running._alive(leader.pid) is False, "precondition: leader gone"
        assert runner.run_journal.left_running._group_alive(leader.pid), "precondition: group alive"
        _entry, wt, path = orphan(runner, tmp_path, agent_pid=leader.pid, agent_pgid=leader.pid)
        _out, calls = reconcile(runner)
    finally:
        os.killpg(leader.pid, 9)
    assert calls == [] and wt.exists() and path.exists()


# ── P1 ORPHAN-RELEASE-BEFORE-WIP ─────────────────────────────────────────────

def test_review_reconcile_never_releases_work_it_failed_to_keep(runner, monkeypatch, tmp_path):
    _entry, wt, path = orphan(runner, tmp_path)
    monkeypatch.setattr(runner.run_journal.ship_run, "commit_leftovers",
                        lambda *a, **k: "commit failed: disk full")
    for _ in range(2):
        out, calls = reconcile(runner)
        assert calls == [] and wt.exists() and path.exists()
    assert out[0]["released"] is False and "disk full" in out[0]["wip_error"]


# ── P1 MISSING-JOURNAL-ACCEPTED ──────────────────────────────────────────────

def test_review_an_unwritable_journal_fails_the_claim_before_working(runner, monkeypatch, tmp_path):
    marker = tmp_path / "agent-ran"
    agent(runner, monkeypatch, tmp_path, f"touch '{marker}'")
    monkeypatch.setattr(runner.run_journal, "write", lambda *a: False)

    plan = run(runner)

    assert states(runner) == ["failed"] and plan["state"] == "failed"
    assert not marker.exists(), "the agent must not start without a journal"


# ── P1 CLEAR-RACE-RESURRECTS ─────────────────────────────────────────────────

def test_review_a_late_heartbeat_write_cannot_recreate_a_cleared_journal(runner, monkeypatch, tmp_path):
    rj = runner.run_journal
    real, inside, go = rj.write, threading.Event(), threading.Event()

    def slow_write(*a):
        inside.set()
        go.wait(5)
        return real(*a)

    beat = rj.Beat(tmp_path, "abcd1234", {"phase": "agent"})
    monkeypatch.setattr(rj, "write", slow_write)
    writer = threading.Thread(target=beat.beat)
    writer.start()
    assert inside.wait(5)
    clearer = threading.Thread(target=beat.clear)
    clearer.start()
    time.sleep(0.2)
    go.set()
    writer.join(5)
    clearer.join(10)
    assert not rj.path(tmp_path, "abcd1234").exists()
    beat.beat()
    assert not rj.path(tmp_path, "abcd1234").exists(), "a beat after clear wrote the journal back"


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_review_a_malformed_journal_does_not_stop_reconcile(runner, tmp_path):
    _entry, _wt, path = orphan(runner, tmp_path)
    bad = path.with_name("ffff0000.json")
    bad.write_text(json.dumps({**json.loads(path.read_text()), "run_id": "ffff0000",
                               "ts": "not-a-number", "owner_pid": "x", "agent_pid": [1]}))
    out, calls = reconcile(runner)
    assert [c["state"] for c in calls] == ["released"], out
    assert bad.exists()


def test_review_a_journal_that_raises_is_held_and_the_rest_still_settle(runner, monkeypatch, tmp_path):
    _entry, _wt, path = orphan(runner, tmp_path)
    bad = path.with_name("00000000.json")
    bad.write_text(json.dumps({**json.loads(path.read_text()), "run_id": "00000000"}))
    real = runner.run_journal.blocker

    def blocker(entry, host, own=False):
        if entry["run_id"] == "00000000":
            raise RuntimeError("boom")
        return real(entry, host, own)

    monkeypatch.setattr(runner.run_journal, "blocker", blocker)
    out, calls = reconcile(runner)
    assert [c["state"] for c in calls] == ["released"] and bad.exists()
    assert {"journal": "00000000.json", "held": "reconcile raised RuntimeError"} in out


def test_review_a_journal_being_settled_elsewhere_is_held(runner, tmp_path):
    import fcntl  # here, not at the top: collection must survive Windows, where the skip applies (r2 P2)
    _entry, wt, path = orphan(runner, tmp_path)
    with open(path.with_suffix(".lock"), "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()
