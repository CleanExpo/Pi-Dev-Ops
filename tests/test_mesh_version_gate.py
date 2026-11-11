"""tests/test_mesh_version_gate.py — a runner claims only on approved code (fleet version gate, 08/11/2026).

Found on the live fleet: the Mini claimed RA-7487 five commits behind main, because
the version was only looked at every 15 idle minutes and claiming never asked. Two
runtimes with local edits refused every update into one log line and kept claiming
on old code. HARD_STOP exited 0, so launchd never restarted the runner and the
MacBook sat dead for 2.4 days after the file was gone.

The loop tests run the real `main()` with claiming faked; the gate tests use REAL git
repositories built the same way as tests/test_mesh_self_update.py.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import Break as _Break, load_module as _load  # noqa: E402
from test_mesh_self_update import commit_preflight, git, origin_and_runtime  # noqa: E402

OLD, NEW = "a" * 40, "b" * 40
REFUSED = "update refused: runtime has local edits (or status failed)"


class FakeGate:
    """Returns the queued verdicts in turn, then repeats the last one."""

    def __init__(self, *statuses: str):
        self._queue = [SimpleNamespace(running=OLD, approved=None if s == "unknown" else (OLD if s == "current" else NEW),
                                       status=s, reason=f"{s}: planted", fetched=True) for s in statuses]
        self.last, self.blocker, self.calls = None, None, 0

    def check(self):
        self.calls += 1
        self.last = self._queue.pop(0) if len(self._queue) > 1 else self._queue[0]
        return self.last


class FakeUpdater:
    def __init__(self, outcome: str, events: list):
        self.outcome, self.events = outcome, events

    def due(self) -> bool:
        return False  # the old 15-minute timer never fires inside a test

    def try_update(self) -> str:
        self.events.append("update")
        return self.outcome


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The real loop with claiming, running and sleeping faked; gate and updater injected per test."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_version_gate", "mesh/runner.py")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "IDLE_RECLAIM_DELAY", 0.01)
    monkeypatch.setattr(mod, "active_agent_count", lambda *a, **k: 0)
    mod.events = []
    monkeypatch.setattr(mod, "get_work", lambda: mod.events.append("get_work") or [])
    monkeypatch.setattr(mod, "SELF_UPDATE_ENABLED", True)
    mod.sleeps = []

    def sleep(secs):
        mod.sleeps.append(secs)
        if len([s for s in mod.sleeps if s == mod.POLL_INTERVAL]) >= getattr(mod, "polls", 1):
            raise _Break()

    monkeypatch.setattr(mod.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["runner"])
    return mod


def _arm(monkeypatch, runner, gate: FakeGate, outcome: str = REFUSED) -> FakeUpdater:
    updater = FakeUpdater(outcome, runner.events)
    monkeypatch.setattr(runner, "GATE", gate, raising=False)
    monkeypatch.setattr(runner.self_update, "Updater", lambda *a, **k: updater)
    return updater


def _state(runner) -> dict:
    return json.loads(runner.STATE_FILE.read_text())


def test_outdated_runner_claims_nothing_when_update_is_refused(runner, monkeypatch):
    _arm(monkeypatch, runner, FakeGate("outdated"))
    with pytest.raises(_Break):
        runner.main()
    assert "get_work" not in runner.events          # held: never reached the claim path
    state = _state(runner)
    assert state["state"] == "outdated"
    assert state["hold_reason"] == ("outdated: runtime has local edits; "
                                    "checkpoint them, then restore the runtime to HEAD")
    assert state["approved_version"] == NEW and state["version_status"] == "outdated"


def test_outdated_idle_runner_attempts_update_before_claiming(runner, monkeypatch):
    _arm(monkeypatch, runner, FakeGate("outdated"), outcome="updated")
    assert runner.main() == 3                        # restart on the new code, as the idle path does
    assert runner.events == ["update"]               # immediately, not after the 15-minute timer
    assert _state(runner)["last_update"]["outcome"] == "updated"


def test_unknown_version_claims_nothing_then_rechecks_each_poll(runner, monkeypatch):
    gate = FakeGate("unknown", "current")
    _arm(monkeypatch, runner, gate)
    runner.polls = 2
    with pytest.raises(_Break):
        runner.main()
    assert gate.calls >= 2                            # re-checked on the next poll, by itself
    assert runner.events == ["get_work"]              # only after the version became known
    assert runner.sleeps[0] == runner.POLL_INTERVAL   # the unknown turn held and waited


def test_unknown_version_writes_version_unknown_state(runner, monkeypatch):
    _arm(monkeypatch, runner, FakeGate("unknown"))
    with pytest.raises(_Break):
        runner.main()
    assert "get_work" not in runner.events
    assert _state(runner)["state"] == "version-unknown"


def test_busy_runner_is_not_interrupted_by_the_gate(runner, monkeypatch):
    gate = FakeGate("current", "outdated")            # main moves while the claim runs
    _arm(monkeypatch, runner, gate)
    monkeypatch.setattr(runner, "get_work", lambda: runner.events.append("get_work") or [{"linear_id": "RA-1"}])

    def run_claim(claim, dry_run):
        runner.events.append("claim-start")
        assert gate.calls == 1                        # nothing looked at the version mid-run
        runner.events.append("claim-end")
        return {"linear_id": "RA-1", "state": "done"}

    monkeypatch.setattr(runner, "run_claim", run_claim)
    with pytest.raises(_Break):
        runner.main()
    assert runner.events[:4] == ["get_work", "claim-start", "claim-end", "update"]
    assert _state(runner)["last_job"]["linear_id"] == "RA-1"


def test_hard_stop_holds_then_resumes_without_exit(runner, monkeypatch):
    """Was: HARD_STOP returned 0 and launchd (KeepAlive SuccessfulExit:false) never restarted it."""
    monkeypatch.setattr(runner, "GATE", None, raising=False)
    runner.HARD_STOP.write_text("stop")
    seen: list[str] = []

    def sleep(secs):
        seen.append(_state(runner)["state"])
        runner.HARD_STOP.unlink(missing_ok=True)     # the person removes the file
        if len(seen) >= 2:
            raise _Break()

    monkeypatch.setattr(runner.time, "sleep", sleep)
    with pytest.raises(_Break):                       # still looping: it never returned
        runner.main()
    assert seen[0] == "hard_stop"
    assert runner.events == ["get_work"]              # resumed claiming by itself


def test_breadcrumb_fields_persist_across_restart(runner, monkeypatch, tmp_path):
    gate = FakeGate("outdated")
    gate.check()
    monkeypatch.setattr(runner, "GATE", gate, raising=False)
    runner.breadcrumb.remember(runner.STATE_FILE, "last_update", {"outcome": REFUSED, "ts": 1})
    runner.breadcrumb.remember(runner.STATE_FILE, "last_job", {"linear_id": "RA-9", "state": "done", "ts": 2})
    runner.write_state(None, "idle")
    restarted = _load("mesh_runner_version_gate_restarted", "mesh/runner.py")
    monkeypatch.setattr(restarted, "STATE_FILE", runner.STATE_FILE)
    monkeypatch.setattr(restarted, "GATE", None, raising=False)
    restarted.write_state(None, "idle")
    state = _state(runner)
    assert state["last_update"] == {"outcome": REFUSED, "ts": 1}
    assert state["last_job"] == {"linear_id": "RA-9", "state": "done", "ts": 2}
    assert state["approved_version"] is None          # the new process has not checked yet: unknown, not carried
    assert set(state) >= {"version_status", "version_reason", "local_edits"}


def test_the_gate_is_off_in_unit_tests_like_preflight():
    import os
    assert os.environ.get("MESH_VERSION_GATE") == "0"


# ── the gate itself, on real git ─────────────────────────────────────────────

@pytest.fixture
def vg():
    """Imported per test, as the runner imports it, so on code without it each test fails on its own."""
    sys.path.insert(0, str(REPO_ROOT / "mesh"))
    import importlib
    return importlib.import_module("version_gate")


def test_gate_reads_current_and_outdated_from_origin_main(vg, tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    assert vg.VersionGate(runtime, old).check().status == "current"
    new = commit_preflight(origin, 0, "ok")
    verdict = vg.VersionGate(runtime, old).check()
    assert (verdict.running, verdict.approved, verdict.status) == (old, new, "outdated")
    assert git(runtime, "rev-parse", vg.self_update.MAIN_REF) == new   # the self-update ref, no second path


def test_an_unmerged_branch_is_never_approved(vg, tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    git(origin, "checkout", "-q", "-b", "feature")
    commit_preflight(origin, 0, "ok")
    assert vg.VersionGate(runtime, old).check().approved == old


def test_gate_caches_the_fetch_but_rechecks_unknown_every_call(vg, tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    now = [0.0]
    gate = vg.VersionGate(runtime, old, clock=lambda: now[0], every=300)
    assert gate.check().fetched is True
    commit_preflight(origin, 0, "ok")
    assert gate.check().status == "current" and gate.last.fetched is False   # cached
    now[0] = 301
    assert gate.check().status == "outdated"
    subprocess.run(["git", "-C", str(runtime), "remote", "set-url", "origin", str(tmp_path / "gone")], check=True)
    now[0] = 700
    assert gate.check().status == "unknown"
    assert gate.check().fetched is True                # unknown is never served from cache


def test_unreadable_running_commit_is_unknown_not_guessed(vg, tmp_path):
    _, runtime, _ = origin_and_runtime(tmp_path)
    verdict = vg.VersionGate(runtime, "unknown").check()
    assert (verdict.running, verdict.status) == (None, "unknown")


@pytest.mark.parametrize("outcome, blocker", [
    (REFUSED, "outdated: runtime has local edits; checkpoint them, then restore the runtime to HEAD"),
    ("update refused: runtime is on a branch (or HEAD unreadable)", "outdated: runtime is on a branch"),
    ("update refused: origin/main is not a fast-forward of this runtime", "outdated: runtime has commits main"),
    ("update refused: an agent this node could not stop may still be running", "outdated: an agent this node"),
    ("rolled back: agent could not write", "outdated: main failed its preflight on this machine"),
])
def test_every_refusal_names_its_blocker_and_next_action(vg, outcome, blocker):
    reason = vg.blocker(outcome)
    assert reason.startswith(blocker)
    assert "; " in reason                             # "<blocker>; <next action>", the tile splits on it


def test_local_edits_counts_tracked_changes_or_none(vg, tmp_path):
    _, runtime, _ = origin_and_runtime(tmp_path)
    assert vg.local_edits(runtime) == 0
    (runtime / "mesh" / "preflight.py").write_text("changed\n")
    assert vg.local_edits(runtime) == 1
    assert vg.local_edits(tmp_path / "not-a-repo") is None
