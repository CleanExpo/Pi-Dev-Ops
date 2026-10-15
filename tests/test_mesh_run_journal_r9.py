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

from test_mesh_run_journal import agent, journals, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it
from test_mesh_run_journal_r8 import _group_alive, _kill, _size  # noqa: E402

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


def _inject(runner, monkeypatch, point: str, proxies: list) -> list:
    """Arm the interrupt at `point`; returns the Once objects, so the test can prove it fired."""
    rr = runner.run_record
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


POINTS = ["stop-entry", "poll", "signal_group", "terminate", "wait", "end_group", "close"]


@pytest.mark.parametrize("point", POINTS)
def test_r9_an_interrupt_anywhere_in_stop_settles_nothing_while_the_group_lives(runner, monkeypatch, tmp_path, point):
    marker, pid_file = tmp_path / "descendant-writes", tmp_path / "descendant-pid"
    agent(runner, monkeypatch, tmp_path, f"(while :; do echo x >> {shlex.quote(str(marker))}; sleep 0.05; done) & "
          f"echo $! > {shlex.quote(str(pid_file))}; sleep 30")
    proxies: list = []
    onces = _inject(runner, monkeypatch, point, proxies)
    spawned: list = []

    def wait(proc, _plan):  # the agent is running; then a Ctrl-C arrives, so run_agent calls stop()
        spawned.append(proc)
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        for proxy in proxies:
            proxy.armed = True
        raise KeyboardInterrupt("Ctrl-C during the run")

    alive_at_terminal: list = []
    monkeypatch.setattr(runner, "_wait_for_agent", wait)
    monkeypatch.setattr(runner, "_api", lambda _m, _p, b=None: alive_at_terminal.append(
        _group_alive(spawned[0].pid)) if (b or {}).get("state") in ("done", "failed", "released") else {})
    try:
        with pytest.raises(KeyboardInterrupt):
            run(runner)
        fired = [o.fired for o in onces + [p._once for p in proxies]]
        assert fired and all(fired), "precondition: the interrupt was never injected at " + point
        assert True not in alive_at_terminal, "a terminal report went out while the group still ran"
        if _group_alive(spawned[0].pid):  # still running: everything must be held
            assert states(runner) == ["working"] and alive_at_terminal == []
            assert len(journals(runner)) == 1 and len(list((tmp_path / "wts").iterdir())) == 1
            assert runner.left_running.any_alive(), "self-update must stay blocked while it runs"
            before = _size(marker)
            time.sleep(0.2)
            assert _size(marker) > before, "precondition: the held case really has a live writer"
    finally:
        _kill(spawned)


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
