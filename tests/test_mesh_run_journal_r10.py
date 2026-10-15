# ruff: noqa: F811
"""tests/test_mesh_run_journal_r10.py — review round 10 of UNI-2963 (Codex, FAIL at 0d926f05).

#1 P0 MISSING-PID-LIVE-RELEASE: a handle whose pid is None counted as reaped once its direct
   child exited, because RunRecord._group_gone() trusted a SEEN agent with no group. On POSIX an
   unreadable pid now always holds (consistent with the owner's fail-closed decision).
#3 P1 REAPED-UNSEEN-NOPID-TICKER-HOLD: a Ctrl-C during the first pid read sets `unseen_agent`;
   the handle is then re-adopted and stop() genuinely proves the group gone (`reaped` True), yet
   no_agent() refused the proof, so after a rejected report the run was held forever. A saved
   handle that stop() proved reaped is now proof, even when the start was interrupted.
#2 P0 DETACHED-DESCENDANT-LIVE-RELEASE: OUT OF SCOPE for slice 1 (coordinator ruling). A child
   that calls setsid() leaves the agent's process group, so a group can be proven empty while it
   writes on. Pinned below as a STRICT xfail: it alerts the day the behaviour changes.
Probes: ~/session-handoffs/durable-slice1-review-r10-codex-evidence/ (none_pid_gate_probe.py,
detached_worktree_writer_probe.py).
"""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from test_mesh_run_journal import agent, journals, run  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it
from test_mesh_run_journal_r7 import _no_pid_in_journal, _reject_terminal, _rt  # noqa: E402
from test_mesh_run_journal_r8 import GROW_TIMEOUT, InterruptOnPid, _group_alive, _grows, _kill, _wrap_agent_popen  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")


@pytest.fixture(autouse=True)
def _fresh_memory(runner):
    runner.run_journal.PENDING.clear()
    runner.run_journal.NEVER_LAUNCHED.clear()


class MissingPid:
    """A real child behind a handle that cannot say its pid (the reviewer's none_pid_gate_probe)."""

    pid = None

    def __init__(self, proc):
        self._proc = proc

    def __getattr__(self, name):
        return getattr(self._proc, name)


def test_r10_a_handle_without_a_pid_is_never_reaped(runner, tmp_path):
    pulse = tmp_path / "pulse"
    proc = subprocess.Popen(["sh", "-c", f"while :; do printf x >> {shlex.quote(str(pulse))}; sleep 0.05; done & exit 0"],
                            start_new_session=True)
    try:
        proc.wait(timeout=5)
        deadline = time.monotonic() + GROW_TIMEOUT
        while not pulse.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        rec = runner.run_record.RunRecord("abcd1234", tmp_path)
        rec.proc = MissingPid(proc)  # a SEEN agent: no unseen_agent flag
        rec.stop()
        assert rec.reaped is not True and runner.run_record.unreaped(rec), "an unknown group was counted gone"
        assert _grows(pulse), "precondition: the descendant is really still writing"
    finally:
        if _group_alive(proc.pid):
            os.killpg(proc.pid, signal.SIGKILL)


def test_r10_an_interrupted_start_that_stop_reaped_settles_after_a_rejected_report(runner, monkeypatch, tmp_path):
    """Interrupt at the first pid read -> handle re-adopted -> stop() reaps the group -> report rejected
    -> the runner's own Ticker sends exactly one terminal update and clears everything."""
    agent(runner, monkeypatch, tmp_path, "sleep 30")
    spawned = _wrap_agent_popen(runner, monkeypatch, InterruptOnPid)
    _no_pid_in_journal(runner, monkeypatch)
    posts = _reject_terminal(runner, monkeypatch)
    try:
        with pytest.raises(KeyboardInterrupt):
            run(runner)
        rid = journals(runner)[0].stem
        assert not _group_alive(spawned[0].pid), "precondition: stop() really ended the group"
        assert [p["state"] for p in posts] == ["working", "failed", "failed", "failed"]
        assert rid in runner.run_journal.NEVER_LAUNCHED, "a saved handle stop() reaped is proof"
        sent: list = []
        runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
        assert [b["state"] for b in sent] == ["failed"] and sent[0]["run_id"] == rid
        assert journals(runner) == [] and runner.run_journal.PENDING == {} and runner.run_journal.NEVER_LAUNCHED == set()
    finally:
        _kill(spawned)


def test_r10_the_no_agent_rule_with_an_interrupted_start(runner):
    no_agent, ns = sys.modules["run_settle"].no_agent, types.SimpleNamespace
    assert no_agent([ns(proc=object(), reaped=True, unseen_agent=True)]) is True     # #3: handle saved, reaped
    assert no_agent([ns(proc=None, reaped=None, unseen_agent=True)]) is False      # no handle: never proof
    assert no_agent([ns(proc=None, reaped=True, unseen_agent=True)]) is False      # reaped without a handle
    assert no_agent([ns(proc=object(), reaped=None, unseen_agent=True)]) is False


DETACH = ("import os,time,pathlib,sys\nos.setsid()\np=pathlib.Path(sys.argv[1])\n"
          "pathlib.Path(sys.argv[2]).write_text(str(os.getpid()))\n"
          "while True:\n    p.open('a').write('x'); time.sleep(0.05)\n")


@pytest.mark.xfail(strict=True, reason="ACCEPTED LIMIT (slice 1, coordinator ruling at r10): a child that calls "
                   "setsid() leaves the agent's process group, so stop() can prove the group empty while it "
                   "writes on. Needs a containment boundary (sandbox/cgroup/session tracking) in a later slice.")
def test_r10_accepted_limit_a_setsid_child_escapes_the_group(runner, monkeypatch, tmp_path):
    pulse, pidfile, script = tmp_path / "pulse", tmp_path / "child.pid", tmp_path / "detach.py"
    script.write_text(DETACH)
    agent(runner, monkeypatch, tmp_path, f"{shlex.quote(sys.executable)} {shlex.quote(str(script))} "
          f"{shlex.quote(str(pulse))} {shlex.quote(str(pidfile))} & sleep 0.5; exit 1")
    try:
        run(runner)
        assert not _grows(pulse), "a detached descendant is still writing after the run ended"
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
