"""tests/test_mesh_run_record_stop.py — a failed run never leaves its agent running (UNI-2796).

Split from tests/test_mesh_run_record.py at the 300-line size gate. Review
rounds 7 and 9 found an agent left running while its claim was reported
terminal and its worktree removed: first when the wait raised, then when
poll() itself raised. RunRecord.stop() must terminate (then kill) and reap
whatever it cannot prove has exited, and never raise.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import load_module as _load  # noqa: E402

rr = _load("mesh_run_record_stop_under_test", "mesh/run_record.py")


def test_a_wait_failure_stops_the_agent_before_returning(tmp_path):
    """Round 7: a wait that raised left the agent running while the claim was reported failed."""
    plan: dict = {}

    def broken_wait(_proc, _plan):
        raise OSError("wait failed")

    rec = rr.run_agent(lambda: ["sleep", "30"], str(tmp_path), tmp_path, "0a0a0a06", plan, broken_wait)
    assert plan["state"] == "failed"
    assert rec.proc.poll() is not None, "agent still running after run_agent returned"
    assert rec._log.closed


class _FakeAgent:
    """A Popen stand-in whose poll() fails the way round 9 planted it."""

    def __init__(self, poll_error):
        self.poll_error, self.terminated, self.killed, self.returncode = poll_error, False, False, None

    def poll(self):
        raise self.poll_error

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_a_failing_poll_still_terminates_the_agent_and_never_raises(tmp_path, monkeypatch):
    """Round 9: poll() raising OSError skipped termination; ValueError escaped the boundary."""
    for error in (OSError("waitpid failed"), ValueError("poll broke")):
        fake = _FakeAgent(error)
        monkeypatch.setattr(rr.subprocess, "Popen", lambda *_a, **_k: fake)
        plan: dict = {}

        def broken_wait(_proc, _plan):
            raise OSError("wait failed")

        run_id = "0a0a0a07" if isinstance(error, OSError) else "0a0a0a17"  # O_EXCL: never reuse an id
        rec = rr.run_agent(lambda: ["agent"], str(tmp_path), tmp_path, run_id, plan, broken_wait)
        assert plan["state"] == "failed", error
        assert fake.terminated, f"{error!r}: agent was not terminated"
        assert rec._log.closed


def test_an_agent_that_ignores_terminate_is_killed(tmp_path, monkeypatch):
    fake = _FakeAgent(OSError("x"))

    def stuck(timeout=None):
        if timeout is not None:
            raise rr.subprocess.TimeoutExpired("agent", timeout)
        return 0

    fake.wait = stuck
    rec = rr.RunRecord("0a0a0a08", tmp_path)
    rec.proc = fake
    rec.stop()
    assert fake.terminated and fake.killed
