"""tests/test_mesh_node_health.py — a node proves it can work, and stops when it can't (RA-7802).

On 28/09 two nodes failed every claim and kept claiming: the PC raised before
its agent started (RA-7801), the Mini's agent could not write files. Each took
a ticket every few seconds, up to MESH_MAX_CLAIMS (25). These tests pin:

  * no claim until preflight passes, and a failed or crashed preflight blocks;
  * FAILURE_LIMIT failed claims in a row quarantine the node, and a delivered
    claim resets the count;
  * the runner's loop honours both: a node that fails every claim takes exactly
    FAILURE_LIMIT tickets, not 25, and a node that fails preflight takes none.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import Break as _Break  # noqa: E402
from mesh_helpers import load_module as _load  # noqa: E402

nh = _load("mesh_node_health_under_test", "mesh/node_health.py")


class Clock:
    """A clock the test moves by hand."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_failed_preflight_blocks_and_is_rechecked_only_when_due():
    results, clock = ["agent could not write a file", ""], Clock()
    calls = []

    def preflight():
        calls.append(1)
        return results[len(calls) - 1]

    health = nh.NodeHealth(preflight, clock=clock, limit=2, recheck=600)
    assert health.may_claim() is False
    assert (health.state, health.reason) == ("blocked", "agent could not write a file")
    clock.now = 599
    assert health.may_claim() is False and len(calls) == 1   # not due: no re-run
    clock.now = 600
    assert health.may_claim() is True and health.state == "healthy"


def test_a_preflight_that_raises_blocks_rather_than_passes():
    def preflight():
        raise RuntimeError("boom")

    health = nh.NodeHealth(preflight, clock=Clock())
    assert health.may_claim() is False
    assert health.reason == "preflight raised RuntimeError"


def test_consecutive_failures_quarantine_and_a_delivery_resets_the_count():
    health = nh.NodeHealth(lambda: "", clock=Clock(), limit=2)
    assert health.may_claim()
    health.record([{"state": "failed", "error_code": "runner_exception"}])
    health.record([{"state": "done"}])
    health.record([{"state": "failed", "error_code": "agent_failed"}])
    assert health.state == "healthy"          # reset by the delivered claim in between
    health.record([{"state": "failed", "error_code": "agent_failed"}])
    assert health.state == "quarantined"
    assert health.reason == "2 failed claims in a row, last: agent_failed"
    assert health.may_claim() is False        # quarantine holds until the recheck is due


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The real loop, preflight ON, with claiming and running faked."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = _load("mesh_runner_health", "mesh/runner.py")
    monkeypatch.setattr(mod, "PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "IDLE_RECLAIM_DELAY", 0.01)
    monkeypatch.setattr(mod, "active_agent_count", lambda *a, **k: 0)
    mod.claims = []
    monkeypatch.setattr(mod, "get_work", lambda: mod.claims.append(1) or [{"linear_id": "RA-1"}])
    monkeypatch.setattr(mod, "run_claim", lambda claim, dry_run: {
        "linear_id": claim["linear_id"], "state": "failed", "error_code": "runner_exception"})

    def sleep(secs):
        if secs == mod.POLL_INTERVAL:
            raise _Break()

    monkeypatch.setattr(mod.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["runner"])
    return mod


def test_a_node_failing_every_claim_stops_at_the_failure_limit(runner, monkeypatch):
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "")
    with pytest.raises(_Break):
        runner.main()
    assert len(runner.claims) == nh.FAILURE_LIMIT      # not MESH_MAX_CLAIMS (25)
    assert '"state": "quarantined"' in (runner.STATE_FILE.read_text())


def test_a_node_failing_preflight_claims_nothing(runner, monkeypatch):
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "agent could not write a file")
    with pytest.raises(_Break):
        runner.main()
    assert runner.claims == []
    assert '"state": "blocked"' in runner.STATE_FILE.read_text()


def test_a_batch_stops_at_the_failure_limit_and_hands_back_the_rest(runner, monkeypatch):
    """Codex round 1: the breaker counted only after the whole batch ran, so a node
    assigned four tickets failed all four before it noticed."""
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "")
    batch = [{"linear_id": f"RA-{n}", "id": f"c-RA-{n}"} for n in range(1, 5)]
    monkeypatch.setattr(runner, "get_work", lambda: batch)
    ran, sent = [], []
    monkeypatch.setattr(runner, "run_claim", lambda claim, dry_run: ran.append(claim["linear_id"]) or {
        "linear_id": claim["linear_id"], "state": "failed", "error_code": "runner_exception"})
    monkeypatch.setattr(runner, "_api", lambda method, path, body=None: sent.append((path, body)) or {})
    monkeypatch.setattr(sys, "argv", ["runner", "--once"])
    runner.main()
    assert ran == ["RA-1", "RA-2"]
    assert sent == [("/api/mesh/claim/update", {"linear_id": lid, "state": "released", "host": runner.HOST,
                                                "claim_id": f"c-{lid}"}) for lid in ("RA-3", "RA-4")]


class _StuckUpdater:
    def due(self):
        return True

    def try_update(self):
        return "stuck: could not return to 0123456789ab (rolled back: agent could not write a file)"


def test_a_stuck_update_stops_the_runner_and_says_so(runner, monkeypatch):
    """A runtime that could not return to its old commit must not restart onto
    the rejected one: exit 0 so KeepAlive{SuccessfulExit:false} leaves it down."""
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "")
    monkeypatch.setattr(runner, "get_work", lambda: [])
    monkeypatch.setattr(runner, "SELF_UPDATE_ENABLED", True)
    monkeypatch.setattr(runner.self_update, "Updater", lambda *a, **k: _StuckUpdater())
    assert runner.main() == 0
    assert '"state": "stuck"' in runner.STATE_FILE.read_text()
    # Codex round 2: exit 0 is not "stays down" — the PC's task restarts every 5 min,
    # and a reboot restarts any node. The next start must refuse without claiming.
    monkeypatch.setattr(runner, "get_work", lambda: pytest.fail("a stuck node claimed work"))
    runner.STATE_FILE.unlink()
    assert runner.main() == 0
    assert '"state": "stuck"' in runner.STATE_FILE.read_text()
    hb = _load("mesh_heartbeat_stuck", "mesh/heartbeat.py")
    assert hb.node_status([], {"state": "stuck"}) == "stuck"


def test_a_stuck_marker_that_cannot_be_written_never_lets_the_runner_exit(tmp_path, monkeypatch):
    """Codex round 3: a failed marker write escaped, the runner exited, and a restart
    found no marker. Unmarked, it must hold, not exit, until the marker is written."""
    import types
    ri = _load("mesh_runner_idle_under_test", "mesh/runner_idle.py")
    tries, sleeps, states = [], [], []

    def mark(path, outcome):
        tries.append(path)
        if len(tries) < 3:
            raise PermissionError("planted")
        path.write_text(outcome)
    monkeypatch.setattr(ri.self_update, "mark_stuck", mark)
    rt = types.SimpleNamespace(HOST="n", POLL_INTERVAL=30, stuck_file=lambda: tmp_path / "STUCK",
                               write_state=lambda lid, state: states.append(state), LOG=ri.Log(),
                               time=types.SimpleNamespace(sleep=sleeps.append))
    health = types.SimpleNamespace(state="healthy")
    assert ri.idle(rt, _StuckUpdater(), health, []) == 0
    assert len(tries) == 3 and sleeps == [30, 30] and (tmp_path / "STUCK").is_file()
    assert set(states) == {"stuck"}
