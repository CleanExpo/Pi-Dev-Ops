"""tests/test_mesh_plan_lane_guards.py — the plan lane never loses track of a live agent (RA-7798).

When waiting on a plan agent fails, the agent may still run; it is recorded as left
running so self-update will not move the runtime under it, and a Ctrl-C arriving while it
is recorded waits until the claim has been reported and the runner marked idle.
"""
from __future__ import annotations

import types

import pytest

from test_mesh_self_update import REPO_ROOT


def test_a_plan_agent_left_running_after_a_wait_error_is_tracked(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))
    from mesh_helpers import load_module
    plan_lane = load_module("mesh_plan_lane_guard", "mesh/plan_lane.py")
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexec sleep 30\n")
    agent.chmod(0o755)
    tracked: list = []

    def wait_fails(proc, plan):
        raise OSError("wait failed")

    rt = types.SimpleNamespace(AGENT_CMD=str(agent), _wait_for_agent=wait_fails,
                               left_running=types.SimpleNamespace(track=tracked.append))
    try:
        assert plan_lane._run_agent({"linear_id": "UNI-P", "title": "t"}, {}, rt) == ""
        assert len(tracked) == 1 and tracked[0].proc.poll() is None
    finally:
        for rec in tracked:
            rec.proc.kill()
            rec.proc.wait()


def test_the_plan_error_handler_never_raises(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))
    from mesh_helpers import load_module
    plan_lane = load_module("mesh_plan_lane_guard_poll", "mesh/plan_lane.py")

    class Proc:
        def poll(self):
            raise OSError("poll failed")

    monkeypatch.setattr(plan_lane.subprocess, "Popen", lambda *a, **k: Proc())
    tracked: list = []

    def wait_fails(proc, plan):
        raise OSError("wait failed")

    rt = types.SimpleNamespace(AGENT_CMD="claude", _wait_for_agent=wait_fails,
                               left_running=types.SimpleNamespace(track=tracked.append))
    assert plan_lane._run_agent({"linear_id": "UNI-P", "title": "t"}, {}, rt) == ""
    assert len(tracked) == 1  # cannot tell whether it runs: recorded as left running


def test_a_real_sigint_while_tracking_a_plan_agent_still_ends_the_claim(tmp_path, monkeypatch):
    import signal
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))
    from mesh_helpers import load_module
    plan_lane = load_module("mesh_plan_lane_sigint", "mesh/plan_lane.py")
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexec sleep 30\n")
    agent.chmod(0o755)
    updates: list = []
    states: list = []
    tracked: list = []

    def wait_fails(proc, plan):
        raise OSError("wait failed")

    def track(rec):
        tracked.append(rec)
        signal.raise_signal(signal.SIGINT)

    def fail(plan, _linear_id, _branch, error):
        plan.update(state="failed", error=error)
        updates.append("failed")
        states.append("idle")
        return plan

    rt = types.SimpleNamespace(
        AGENT_CMD=str(agent), HOST="h", _wait_for_agent=wait_fails, _fail_claim=fail,
        left_running=types.SimpleNamespace(track=track),
        write_state=lambda _id, state, **_k: states.append(state),
        _api=lambda _m, _p, body=None: updates.append(body["state"]))
    try:
        with pytest.raises(KeyboardInterrupt):  # still delivered, but only after the claim ends
            plan_lane.run_plan_claim({"linear_id": "UNI-P", "title": "t"}, rt)
        assert updates == ["working", "failed"] and states[-1] == "idle"
        assert len(tracked) == 1 and tracked[0].proc.poll() is None
    finally:
        for rec in tracked:
            rec.proc.kill()
            rec.proc.wait()
