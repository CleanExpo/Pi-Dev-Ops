# ruff: noqa: F811
"""tests/test_mesh_run_journal_r9.py — review round 9 of UNI-2963 (Codex, FAIL at d5a208e8).

P0 R9-1 STOP-INTERRUPT-LIVE-RELEASE: a Ctrl-C landing at RunRecord.stop()'s entry escaped with
`reaped` still None. `unreaped()` counted only `reaped is False` as alive and `left_running.track`
skipped None, so the ending removed the worktree, reported and cleared the journal while the
agent's group was still writing. Rounds 8 and 9 were both windows of one class: the verdict
depended on how far stop() got. The rule is now inverted, in one place
(`left_running.may_be_running`): a record holding a process handle, or one that may have started
a child unseen, is ALIVE unless `reaped is True`. unreaped() and track() both use it.

Each injection point below interrupts the real stop() of a real agent that has forked a writing
descendant; at every point nothing may settle while the group lives.
"""
from __future__ import annotations

import os
import shlex
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
from test_mesh_run_journal_r8 import GROW_TIMEOUT, _group_alive, _grows, _kill  # noqa: E402
from test_mesh_run_journal_r7 import _rt  # noqa: E402
from test_mesh_run_journal_r8 import NoPid  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"


class Once:
    """Raise KeyboardInterrupt the first time it is called, then behave like `real`."""

    def __init__(self, real):
        self.real, self.fired = real, False

    def __call__(self, *a, **k):
        if not self.fired:
            self.fired = True
            raise KeyboardInterrupt("injected inside stop()")
        return self.real(*a, **k)


class ProcProxy:
    """The agent's real Popen, with one method armed to be interrupted once inside stop()."""

    def __init__(self, proc, method):
        self._proc, self._method, self.armed = proc, method, False
        self._once = Once(getattr(proc, method))

    def __getattr__(self, name):
        if name == self._method and self.armed:
            return self._once
        return getattr(self._proc, name)


def _inject(runner, monkeypatch, point: str, proxies: list, spawned: list, ready) -> list:
    """Arm the interrupt at `point`; returns the Once objects, so the test can prove it fired."""
    rr = runner.run_record
    if point == "popen-unseen":  # the pid is never readable (unseen child), then stop() is cut at entry
        _unreadable_agent_pid(runner, monkeypatch, spawned, ready)
        point = "stop-entry"
    if point == "stop-entry":  # the reviewer's case: before stop() takes a single step
        once = Once(lambda self: None)
        monkeypatch.setattr(rr.RunRecord, "stop", once)
        return [once]
    if point in ("signal_group", "end_group"):
        once = Once(getattr(rr.agent_sandbox, point))
        monkeypatch.setattr(rr.agent_sandbox, point, once)
        return [once]
    if point == "close":
        once = Once(rr.RunRecord.close)
        monkeypatch.setattr(rr.RunRecord, "close", lambda self: once(self))
        return [once]
    real_adopt = rr.RunRecord._adopt  # a method of the agent's own handle: poll, terminate, wait

    def adopt(self, proc):
        proxies.append(ProcProxy(proc, point))
        real_adopt(self, proxies[-1])

    monkeypatch.setattr(rr.RunRecord, "_adopt", adopt)
    return []


def _unreadable_agent_pid(runner, monkeypatch, spawned: list, ready) -> None:
    real = runner.run_record.subprocess.Popen

    def popen(cmd, *a, **k):
        proc = real(cmd, *a, **k)
        if not (cmd and cmd[0] == runner.AGENT_CMD):
            return proc
        spawned.append(proc)
        _wait_for_file(ready)
        return NoPid(proc)

    monkeypatch.setattr(runner.run_record.subprocess, "Popen", popen)


def _wait_for_file(path) -> None:
    deadline = time.monotonic() + 4 * GROW_TIMEOUT  # bounded; a starved fork can take seconds at loadavg 80+
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "precondition: the descendant writer never started"


POINTS = ["stop-entry", "poll", "signal_group", "terminate", "wait", "end_group", "close", "popen-unseen"]
# Derived from RunRecord.stop(): an interrupt at its entry leaves `reaped` None, and one inside
# end_group leaves the group unproven (`reaped` False). Both hold the claim (agent_alive) and record
# no outcome. At every other point stop() still reaches end_group's SIGKILL and proves the group
# empty, so the run settles: one terminal report, worktree removed, journal cleared.
HELD_AT_END = {"stop-entry", "end_group", "popen-unseen"}
# 'popen-unseen' leaves no handle and no journaled pid: nothing can ever prove the child gone, so even
# after the group empties the Ticker keeps holding (fail closed; the owner's decision for unknowns).
HELD_FOREVER = {"popen-unseen"}
# TERM-resistant: only end_group's SIGKILL can end the writer (proves a LIVE hold). TERM-responsive:
# stop()'s SIGTERM ends it, and its handler leaves a mark first, so the graceful exit is OBSERVED.
WRITERS = {"term-resistant": "trap '' TERM; ", "term-responsive": "trap 'echo term >> {term}; exit 0' TERM; "}
# Derived from RunRecord.stop(): it sends the group SIGTERM right after its first poll, so an interrupt at
# poll, terminate, wait or close still lets SIGTERM through before end_group (and end_group itself comes
# after it). stop-entry and popen-unseen never run stop(), and at signal_group that very SIGTERM is the
# interrupted call: none of those three may see a TERM.
TERM_POINTS = {"poll", "terminate", "wait", "end_group", "close"}


def _wait_until(check, timeout: float = 4 * GROW_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.02)
    return False


def _observe_end_group(runner, monkeypatch, term_file) -> list:
    """Before end_group's SIGKILL: did the writer take the TERM path, and was its group already gone?"""
    real, seen = runner.run_record.agent_sandbox.end_group, []

    def observed(pgid):
        if not seen:
            seen.append((_wait_until(term_file.exists), _wait_group_gone(pgid)))
        return real(pgid)

    monkeypatch.setattr(runner.run_record.agent_sandbox, "end_group", observed)
    return seen


def _assert_term_path(point: str, term_file, before_kill: list) -> None:
    if point not in TERM_POINTS:
        assert not term_file.exists(), "no SIGTERM may reach the writer at " + point
    elif point == "end_group":  # the interrupted call: the TERM sent before it must still have ended the writer
        assert _wait_until(term_file.exists), "the writer never took the TERM path"
    else:
        assert before_kill == [(True, True)], "TERM must end the writer and empty the group before end_group's SIGKILL"


def _wait_group_gone(pgid: int, timeout: float = 4 * GROW_TIMEOUT) -> bool:
    """Bounded; generous because the last members are orphans launchd reaps, slowly at loadavg 80+."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _group_alive(pgid):
            return True
        time.sleep(0.02)
    return False


def _members(pgid: int) -> str:
    """What is left in the group, for the failure message (diagnosis, not a check)."""
    import subprocess
    try:  # r13: a hung ps must not hang the failure path
        out = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,pgid=,stat=,comm="], capture_output=True, text=True,
                             timeout=10).stdout
    except subprocess.TimeoutExpired:
        return "(ps timed out)"
    return "\n".join(line for line in out.splitlines() if line.split()[2:3] == [str(pgid)]) or "(none listed)"


def _assert_settled(runner, tmp_path, pgid, alive_at_terminal) -> None:
    assert alive_at_terminal == [False], "expected exactly one terminal report, sent after the group was gone"
    assert journals(runner) == [] and not any((tmp_path / "wts").iterdir()), "settled runs leave nothing behind"
    assert not _group_alive(pgid)


def _assert_held_then_settled(runner, tmp_path, leader, marker, writer_alive: bool, alive_at_terminal,
                              forever: bool = False) -> None:
    pgid = leader.pid
    assert alive_at_terminal == [], "no terminal report at all while the agent is unproven"
    assert len(journals(runner)) == 1 and len(list((tmp_path / "wts").iterdir())) == 1
    if writer_alive:  # the hold really protects a live writer; then the agent ends
        assert runner.left_running.any_alive(), "self-update must stay blocked while it runs"
        assert _grows(marker), "precondition: the held case really has a live writer"
        os.killpg(pgid, 9)
    else:  # TERM already ended it; the claim is still held until the group is proven empty
        assert not _grows(marker, 1.0), "precondition: SIGTERM really ended the TERM-responsive writer"
    leader.wait(timeout=GROW_TIMEOUT)  # the runner's own child: an unreaped leader is a zombie member
    assert _wait_group_gone(pgid), "the agent's group never emptied:\n" + _members(pgid)
    sent: list = []
    runner.run_journal.Ticker()(_rt(runner, lambda m, p, b=None: sent.append(b) or {}), False)
    if forever:  # no pid, no handle, no proof: still held after the group is gone
        assert sent == [] and len(journals(runner)) == 1, "an unprovable run must never settle"
        return
    assert [b["state"] for b in sent] == ["released"], "the held run settles once, with no outcome recorded"
    assert journals(runner) == [] and not any((tmp_path / "wts").iterdir())


@pytest.mark.parametrize("mode", list(WRITERS))
@pytest.mark.parametrize("point", POINTS)
def test_r9_an_interrupt_anywhere_in_stop_settles_nothing_while_the_group_lives(runner, monkeypatch, tmp_path,
                                                                               point, mode):
    marker, term_file = tmp_path / "descendant-writes", tmp_path / "writer-got-term"
    writer = WRITERS[mode].format(term=shlex.quote(str(term_file)))
    agent(runner, monkeypatch, tmp_path, f"({writer}while :; do echo x >> {shlex.quote(str(marker))}; "
          f"sleep 0.05; done) & sleep 30")
    responsive = mode == "term-responsive"
    before_kill = (_observe_end_group(runner, monkeypatch, term_file)
                   if responsive and point in TERM_POINTS - {"end_group"} else [])
    proxies, spawned = [], []
    # Wait for the writer's FIRST WRITE, not its pid: the write comes after its `trap` is in place, so a
    # Ctrl-C can never land between the fork and the trap (2/30 runs at loadavg ~78 did exactly that).
    onces = _inject(runner, monkeypatch, point, proxies, spawned, marker)
    alive_at_terminal = _interrupt_the_run(runner, monkeypatch, marker, proxies, spawned)
    try:
        with pytest.raises(KeyboardInterrupt):
            run(runner)
        fired = [o.fired for o in onces + [p._once for p in proxies]]
        assert fired and all(fired), "precondition: the interrupt was never injected at " + point
        assert True not in alive_at_terminal, "a terminal report went out while the group still ran"
        if responsive:
            _assert_term_path(point, term_file, before_kill)
        if point in HELD_AT_END:
            writer_alive = point != "end_group" or mode == "term-resistant"  # no signal reached the others
            _assert_held_then_settled(runner, tmp_path, spawned[0], marker, writer_alive, alive_at_terminal,
                                      forever=point in HELD_FOREVER)
        else:
            _assert_settled(runner, tmp_path, spawned[0].pid, alive_at_terminal)
    finally:
        _kill(spawned)


def _interrupt_the_run(runner, monkeypatch, ready, proxies, spawned: list) -> list:
    """The agent runs until its descendant exists, then a Ctrl-C arrives, so run_agent calls stop()."""
    alive_at_terminal: list = []

    def wait(proc, _plan):
        spawned.append(proc)
        _wait_for_file(ready)
        for proxy in proxies:
            proxy.armed = True
        raise KeyboardInterrupt("Ctrl-C during the run")

    monkeypatch.setattr(runner, "_wait_for_agent", wait)
    monkeypatch.setattr(runner, "_api", lambda _m, _p, b=None: alive_at_terminal.append(
        _group_alive(spawned[0].pid)) if (b or {}).get("state") in ("done", "failed", "released") else {})
    return alive_at_terminal


def test_r9_the_rule_is_alive_unless_proven_reaped(runner):
    """One rule, both consumers: unreaped() and left_running.may_be_running()."""
    ns, lr, rr = types.SimpleNamespace, runner.left_running, runner.run_record
    cases = [
        (ns(proc=object(), reaped=None), True),                    # stop() never finished: alive
        (ns(proc=object(), reaped=False), True),
        (ns(proc=object(), reaped=True), False),                   # positive proof only
        (ns(proc=None, reaped=None, unseen_agent=True), True),
        (ns(proc=None, reaped=True, unseen_agent=True), False),
        (ns(proc=None, reaped=None), False),                       # no handle, nothing unseen: no agent
    ]
    for rec, alive in cases:
        assert lr.may_be_running(rec) is alive and rr.unreaped(rec) is alive, rec
    assert rr.unreaped(None) is False and lr.may_be_running(None) is False


def test_r9_track_records_a_handle_whose_stop_never_finished(runner, monkeypatch, tmp_path):
    path = tmp_path / "left.json"
    monkeypatch.setattr(runner.left_running, "PATH", path)
    runner.left_running.track(types.SimpleNamespace(proc=types.SimpleNamespace(pid=os.getpid()), pgid=None, reaped=None))
    assert path.exists() and '"pid"' in path.read_text()
    runner.left_running.track(types.SimpleNamespace(proc=types.SimpleNamespace(pid=os.getpid()), pgid=None, reaped=True))
    assert path.read_text().count('"pid"') == 1, "a proven-reaped agent must not be recorded"
