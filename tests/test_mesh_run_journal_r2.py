# ruff: noqa: F811
"""tests/test_mesh_run_journal_r2.py — review round 2 of UNI-2963 (Codex, FAIL at 636dd690).

Each test was written to fail at 636dd690:

  P0 PREPARING-JOURNAL-RELEASES-LIVE-AGENT  a failed `launching` write still started the agent,
                                            and a `preparing` journal with no pid was released
  P1 MISSING-GIT-METADATA-FALSELY-PRESERVED a worktree without `.git` counted as never created,
                                            and an unchecked failed `worktree remove` still released
  P1 HELD-CLAIM-NO-LIVE-RUNNER-RETRY        a held settlement was retried only at the next restart
  P2                                        settlement `.lock` files were never removed
"""
from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import Break  # noqa: E402
from test_mesh_kill9_recovery import show  # noqa: E402
from test_mesh_run_journal import agent, journals, orphan, reconcile, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


# ── P0 PREPARING-JOURNAL-RELEASES-LIVE-AGENT ────────────────────────────────

def test_r2_a_failed_launching_write_never_starts_the_agent(runner, monkeypatch, tmp_path):
    marker = tmp_path / "agent-ran"
    agent(runner, monkeypatch, tmp_path, f"touch '{marker}'\nexec sleep 30")
    real, writes = runner.run_journal.write, []

    def first_only(*a):
        """Only the main thread's writes count (r3 P2: a heartbeat could land between them);
        the first succeeds, every later write, the heartbeat's included, fails."""
        if threading.current_thread() is not threading.main_thread():
            return False
        writes.append(a[2].get("phase"))
        return real(*a) if len(writes) == 1 else False

    monkeypatch.setattr(runner.run_journal, "write", first_only)
    plan = run(runner)

    assert writes[:2] == ["preparing", "launching"]
    assert not marker.exists(), "the agent started although its journal never said `launching`"
    assert plan["state"] == "failed" and states(runner) == ["working", "failed"]


def test_r2_a_preparing_journal_without_a_pid_is_held(runner, tmp_path):
    """Uncertain is not dead: hold it, whatever else the journal says."""
    _entry, wt, path = orphan(runner, tmp_path, phase="preparing", agent_pid=None, agent_pgid=None)
    out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()
    assert out[0]["held"] == "agent may be running unrecorded", out


# ── P1 MISSING-GIT-METADATA-FALSELY-PRESERVED ───────────────────────────────

def test_r2_a_worktree_missing_its_git_metadata_is_held(runner, tmp_path):
    _entry, wt, path = orphan(runner, tmp_path)
    (wt / ".git").unlink()
    out, calls = reconcile(runner)
    assert calls == [] and (wt / "wip.txt").exists() and path.exists()
    assert "metadata" in (out[0]["wip_error"] or ""), out


def test_r2_a_worktree_that_would_not_go_holds_the_claim(runner, monkeypatch, tmp_path):
    entry, wt, path = orphan(runner, tmp_path)
    monkeypatch.setattr(runner.run_journal.claim_lifecycle, "remove_worktree", lambda *a: False)
    out, calls = reconcile(runner)
    assert calls == [] and wt.exists() and path.exists()
    assert show(runner.repo, entry["branch"], "wip.txt") == "unsaved\n", "the work itself is kept"
    assert out[0]["released"] is False


def test_r2_remove_worktree_reports_whether_the_worktree_is_gone(runner, tmp_path):
    _entry, wt, _path = orphan(runner, tmp_path)
    lifecycle = runner.claim_lifecycle
    assert lifecycle.remove_worktree(tmp_path / "not-a-repo", wt) is False
    assert lifecycle.remove_worktree(runner.repo, wt) is True and not wt.exists()


def test_r2_the_runner_keeps_its_journal_when_its_worktree_would_not_go(runner, monkeypatch, tmp_path):
    agent(runner, monkeypatch, tmp_path, "echo x > wip.txt\nexit 1")
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree", lambda *a: False)
    run(runner)
    assert len(journals(runner)) == 1, "a worktree left behind must stay journaled for a retry"


# ── P1 HELD-CLAIM-NO-LIVE-RUNNER-RETRY ───────────────────────────────────────

def _rt(runner, api):
    return types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=runner.HOST,
                                 _api=api, LOG=runner.LOG)


def test_r2_a_held_settlement_is_retried_while_the_runner_lives(runner, monkeypatch, tmp_path):
    """This runner's OWN journal, held after a transient failure, settles on a later tick."""
    entry, _wt, path = orphan(runner, tmp_path, owner_pid=os.getpid())
    ship_run, real = runner.run_journal.ship_run, runner.run_journal.ship_run.commit_leftovers
    fail = [True]
    monkeypatch.setattr(ship_run, "commit_leftovers",
                        lambda *a, **k: "stage failed: disk full" if fail[0] else real(*a, **k))
    sent: list = []
    rt, clock = _rt(runner, lambda m, p, b=None: sent.append(b) or {}), [1000.0]
    tick = runner.run_journal.Ticker(clock=lambda: clock[0])

    tick(rt, False)
    assert sent == [] and path.exists()
    fail[0] = False
    tick(rt, False)
    assert sent == [], "retries are bounded: not again within the interval"
    clock[0] += runner.run_journal.RECONCILE_EVERY_S + 1
    tick(rt, False)
    assert [b["state"] for b in sent] == ["released"] and not path.exists()
    assert show(runner.repo, entry["branch"], "wip.txt") == "unsaved\n"


def test_r2_the_runner_loop_reconciles_on_every_cycle(runner, monkeypatch):
    ticks: list = []
    monkeypatch.setattr(runner, "default_repo_dir_problem", lambda: "")
    monkeypatch.setattr(runner.run_journal, "Ticker", lambda: lambda rt, dry: ticks.append(dry))
    monkeypatch.setattr(runner, "get_work", lambda: [])
    monkeypatch.setattr(runner.runner_idle, "idle", lambda *a, **k: None)
    sleeps: list = []

    def sleep(_s):
        sleeps.append(_s)
        if len(sleeps) >= 2:
            raise Break

    monkeypatch.setattr(runner.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["runner.py"])
    with pytest.raises(Break):
        runner.main()
    assert ticks == [False, False]


# ── P2 ───────────────────────────────────────────────────────────────────────

def test_r2_settlement_leaves_no_lock_file_behind(runner, tmp_path):
    _entry, _wt, path = orphan(runner, tmp_path)
    _out, calls = reconcile(runner)
    assert [c["state"] for c in calls] == ["released"]
    assert list(path.parent.glob("*.lock")) == []
