"""tests/test_mesh_claim_lifecycle.py — from `working` on, every way out of a claim ends it (UNI-2796).

Review round 16 listed every remaining way `run_claim` could strand a claim:
an interrupt during the `working` update, during `git worktree add`, or during
a failed add's cleanup; an agent no shutdown step could stop; and a terminal
update the server rejected. Each case below runs `run_claim` end to end.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import load_module as _load  # noqa: E402
from test_mesh_run_record_claim import _runner, _sleeping_agent, _updates  # noqa: E402

cl = _load("claim_lifecycle_under_test", "mesh/claim_lifecycle.py")


def _state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text())["state"]


def test_finish_runs_every_step_even_when_one_raises():
    """Round 15: the terminal update raising skipped worktree removal and the idle state."""
    ran: list = []

    def broken():
        ran.append("report")
        raise ValueError("unknown url type")

    with pytest.raises(ValueError):
        cl.finish(broken, lambda: ran.append("remove"), lambda: ran.append("idle"))
    assert ran == ["report", "remove", "idle"]


def test_a_terminal_update_that_raises_still_cleans_up(monkeypatch, tmp_path):
    """Round 15, end to end: `_api` raising on the done update left the worktree and state `working`."""
    runner, _calls, removed, repo = _runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "AGENT_CMD", "true")

    def api(_method, _path, body=None):
        if (body or {}).get("state") in ("done", "failed"):
            raise ValueError("unknown url type")
        return {}

    monkeypatch.setattr(runner, "_api", api)
    with pytest.raises(ValueError):
        runner.run_claim({"linear_id": "UNI-T", "repo_dir": str(repo)}, dry_run=False)
    assert removed, "worktree was not cleaned up"
    assert _state(tmp_path) == "idle"


@pytest.mark.parametrize("where", ["working update", "worktree add", "failed-add cleanup"])
def test_an_interrupt_anywhere_after_working_still_ends_the_claim(monkeypatch, tmp_path, where):
    """Round 16 P1s 1-3: each interrupt left the claim `working`, state.json `working`, nothing removed."""
    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)
    removals: list = []

    def api(_method, path, body=None):
        calls.append((path, body or {}))
        if where == "working update" and (body or {}).get("state") == "working":
            raise KeyboardInterrupt
        return {}

    def git(args, **_kw):
        if "add" in args:
            if where == "worktree add":
                raise KeyboardInterrupt
            return subprocess.CompletedProcess(args, 1 if where == "failed-add cleanup" else 0)
        removals.append(args[-1])
        if where == "failed-add cleanup":
            raise KeyboardInterrupt
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(runner, "_api", api)
    monkeypatch.setattr(runner.subprocess, "run", git)
    with pytest.raises(KeyboardInterrupt):
        runner.run_claim({"linear_id": "UNI-K", "repo_dir": str(repo)}, dry_run=False)
    assert [b["state"] for b in _updates(calls)] == ["working", "failed"]
    assert removals, "worktree removal was never attempted"
    assert _state(tmp_path) == "idle"


class _Unkillable:
    """A real, running child whose every shutdown call fails (round 16 P1 4)."""

    def __init__(self, proc):
        self.proc, self.returncode = proc, None

    def poll(self):
        return None

    def terminate(self):
        raise OSError("terminate failed")

    kill = terminate

    def wait(self, timeout=None):
        raise OSError("wait failed")


def test_an_agent_that_cannot_be_stopped_keeps_its_claim_and_worktree(monkeypatch, tmp_path):
    """Round 16 P1 4: the claim was reported failed and the worktree removed with the agent alive."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)
    _sleeping_agent(runner, monkeypatch, tmp_path)
    real_popen = runner.run_record.subprocess.Popen
    children: list = []

    def popen(*a, **k):
        children.append(real_popen(*a, **k))
        return _Unkillable(children[-1])

    def broken_wait(_proc, _plan):
        raise OSError("wait failed")

    monkeypatch.setattr(runner.run_record.subprocess, "Popen", popen)
    monkeypatch.setattr(runner, "_wait_for_agent", broken_wait)
    try:
        runner.run_claim({"linear_id": "UNI-U", "repo_dir": str(repo)}, dry_run=False)
        assert children[0].poll() is None, "the planted agent should still be running"
        assert [b["state"] for b in _updates(calls)] == ["working"]
        assert not removed, "a live agent's worktree was removed"
        assert _state(tmp_path) == "working"
    finally:
        children[0].kill()
        children[0].wait()


def test_a_rejected_terminal_update_is_retried(monkeypatch, tmp_path):
    """Round 16 P1 5, runner side: an error reply means the claim is still `working` on the server."""
    runner, calls, removed, repo = _runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "AGENT_CMD", "true")
    for failures, sent in ((1, 2), (5, cl.REPORT_ATTEMPTS)):
        calls.clear()
        rejected = [failures]

        def api(_method, path, body=None, rejected=rejected):
            calls.append((path, body or {}))
            if (body or {}).get("state") == "done" and rejected[0] > 0:
                rejected[0] -= 1
                return {"error": "HTTP 502"}
            return {}

        monkeypatch.setattr(runner, "_api", api)
        runner.run_claim({"linear_id": "UNI-R", "repo_dir": str(repo)}, dry_run=False)
        assert [b["state"] for b in _updates(calls)] == ["working"] + ["done"] * sent
        assert removed and _state(tmp_path) == "idle"


def test_a_ship_that_raises_fails_the_run_and_ships_before_removal(monkeypatch, tmp_path):
    """RA-7780 inside the protected block: settle() raising must not report `done`,
    and shipping must happen while the worktree still exists."""
    import types

    runner, calls, _removed, repo = _runner(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "AGENT_CMD", "true")
    order: list = []

    def settle(plan, *_a):
        order.append("ship")
        raise subprocess.TimeoutExpired("git", 120)

    real_remove = runner.claim_lifecycle.remove_worktree
    monkeypatch.setattr(runner, "ship_run", types.SimpleNamespace(
        start_point=lambda *_a: "0" * 40, settle=settle))
    monkeypatch.setattr(runner.claim_lifecycle, "remove_worktree",
                        lambda *a: order.append("remove") or real_remove(*a))
    plan = runner.run_claim({"linear_id": "UNI-S", "repo_dir": str(repo)}, dry_run=False)
    assert plan["state"] == "failed"
    assert _updates(calls)[-1]["state"] == "failed"
    assert order == ["ship", "remove"]
