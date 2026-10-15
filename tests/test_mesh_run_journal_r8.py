# ruff: noqa: F811
"""tests/test_mesh_run_journal_r8.py — review round 8 of UNI-2963 (Codex, FAIL at 9b43a772).

P0 POST-POPEN-UNKNOWN-GROUP ("g2"): a Ctrl-C landing after Popen returned but before the
RunRecord saved the agent's process group left `proc` set, `pgid` None and `unseen_agent` set.
stop() then terminated only the direct child, `end_group(None)` answered True, the agent counted
as reaped, and the ending kept the work, removed the worktree, reported `failed` and cleared the
journal while a descendant was still writing (reproduced by the reviewer and the coordinator).

Two layers, each with its own test: (1) the handle and its group are adopted together, and
stop() falls back to proc.pid (start_new_session makes the agent its group's leader), so the
whole group is ended before anything is reported; (2) an unseen agent whose group is unknown is
never counted as reaped, and on POSIX `end_group(None)` / `group_empty(None)` prove nothing.
The real-child test is adapted from the reviewer's `test_r8_attack.py`.
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

from test_mesh_run_journal import agent, journals, run, states  # noqa: E402
from test_mesh_run_journal import runner  # noqa: E402,F401 — the shared fixture; F811 below is pytest injecting it

pytestmark = pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX process groups")
HOST = "TESTNODE"


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # darwin: a zombie still in the group
        return True
    return True


class InterruptOnPid:
    """The reviewer's probe: the first read of .pid raises the interrupt, after Popen returned."""

    def __init__(self, proc):
        self.proc, self.raised = proc, False

    @property
    def pid(self):
        if not self.raised:
            self.raised = True
            raise KeyboardInterrupt("after Popen returned")
        return self.proc.pid

    def __getattr__(self, name):
        return getattr(self.proc, name)


class NoPid(InterruptOnPid):
    """The pid is never readable: the group cannot be learned at all."""

    @property
    def pid(self):
        raise KeyboardInterrupt("pid never readable")


def _wrap_agent_popen(runner, monkeypatch, wrap, ready=None) -> list:
    """Start the agent for real, wait for `ready` to exist, then hand back `wrap(proc)`."""
    real, spawned = runner.run_record.subprocess.Popen, []

    def popen(cmd, *a, **k):
        proc = real(cmd, *a, **k)
        if not (cmd and cmd[0] == runner.AGENT_CMD):
            return proc
        spawned.append(proc)
        deadline = time.monotonic() + 3
        while ready is not None and not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        return wrap(proc)

    monkeypatch.setattr(runner.run_record.subprocess, "Popen", popen)
    return spawned


def _kill(spawned) -> None:
    for proc in spawned:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def _size(path) -> int:
    return path.stat().st_size if path.exists() else 0


def test_r8_g2_no_report_while_the_agents_group_still_runs(runner, monkeypatch, tmp_path):
    """A real agent forks a writer, then the interrupt lands right after Popen returned."""
    marker, pid_file = tmp_path / "descendant-writes", tmp_path / "descendant-pid"
    agent(runner, monkeypatch, tmp_path, f"(while :; do echo x >> {shlex.quote(str(marker))}; sleep 0.05; done) & "
          f"echo $! > {shlex.quote(str(pid_file))}; sleep 30")
    spawned = _wrap_agent_popen(runner, monkeypatch, InterruptOnPid, ready=pid_file)
    alive_at_terminal: list = []
    monkeypatch.setattr(runner, "_api", lambda _m, _p, b=None: alive_at_terminal.append(
        _group_alive(spawned[0].pid)) if (b or {}).get("state") in ("done", "failed", "released") else {})
    try:
        with pytest.raises(KeyboardInterrupt):
            run(runner)
        before = _size(marker)
        time.sleep(0.3)
        assert _size(marker) == before, "a descendant is still writing after the run ended"
        # layer 1: the adopted handle lets stop() end the whole group, and only then is `failed` sent
        assert alive_at_terminal == [False], "a terminal report went out while the group still ran"
        assert not _group_alive(spawned[0].pid)
    finally:
        _kill(spawned)


def test_r8_an_unseen_agent_whose_group_is_unknown_is_never_reaped(runner, tmp_path):
    """Layer 2, at the record: no group to prove empty means not reaped, whatever the handle says."""
    rec = runner.run_record.RunRecord("abcd1234", tmp_path)
    rec.proc = types.SimpleNamespace(pid=None, returncode=0, poll=lambda: 0, terminate=lambda: None,
                                     kill=lambda: None, wait=lambda timeout=None: 0)
    rec.unseen_agent = True
    rec.stop()
    assert rec.reaped is False and runner.run_record.unreaped(rec)


def test_r8_stop_falls_back_to_the_leaders_pid_for_the_group(runner, tmp_path):
    """Layer 1, at the record: a handle without a saved group still ends its whole group."""
    marker = tmp_path / "w"
    child = subprocess.Popen(["sh", "-c", f"(while :; do echo x >> '{marker}'; sleep 0.05; done) & sleep 30"],
                             start_new_session=True)
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:  # the descendant must exist first
            time.sleep(0.01)
        assert marker.exists(), "precondition: the descendant never started"
        rec = runner.run_record.RunRecord("abcd1234", tmp_path)
        rec.proc = child  # as if the interrupt landed before the group was saved
        rec.unseen_agent = True
        rec.stop()
        assert rec.reaped is True and not _group_alive(child.pid)
    finally:
        if _group_alive(child.pid):
            os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)


def test_r8_on_posix_an_unknown_group_proves_nothing(runner):
    sandbox = runner.agent_sandbox
    assert sandbox.GROUPS
    assert sandbox.end_group(None) is False and sandbox.group_empty(None, 0) is False


def test_r8_g2_held_run_stays_held_for_the_ticker(runner, monkeypatch, tmp_path):
    """When the group cannot be learned at all, the claim is held and the Ticker holds it too:
    with no pid on record nothing can later prove the child gone (fail closed, by design)."""
    agent(runner, monkeypatch, tmp_path, "sleep 30")
    spawned = _wrap_agent_popen(runner, monkeypatch, NoPid)
    try:
        with pytest.raises(KeyboardInterrupt):
            run(runner)
        assert states(runner) == ["working"]
        assert len(journals(runner)) == 1 and len(list((tmp_path / "wts").iterdir())) == 1
        sent: list = []
        rt = types.SimpleNamespace(killed=lambda: False, STATE_FILE=runner.STATE_FILE, HOST=HOST,
                                   _api=lambda m, p, b=None: sent.append(b) or {}, LOG=runner.LOG)
        runner.run_journal.Ticker()(rt, False)
        assert sent == [] and len(journals(runner)) == 1
    finally:
        _kill(spawned)
