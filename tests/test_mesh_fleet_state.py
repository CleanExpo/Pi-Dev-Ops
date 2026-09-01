"""tests/test_mesh_fleet_state.py — UNKNOWN must not read as EMPTY (RA-7392).

`GET /api/mesh/fleet` used to render a failed Supabase read as
`{"machines": [], "agents": [], "ships": [], "claims": []}`, identical to a
fleet nobody has joined. The endpoint half of that is fixed in
`tests/test_mesh_fleet_endpoint.py`; this file covers the consumer, where the
consequences actually landed:

  * `my_claims()` -> `[]` let `get_work()` conclude it held nothing and
    SELF-CLAIM another ticket while its real claims were merely invisible.
  * `active_agent_count()` -> `0` made `0 < MAX_PARALLEL` true, so the loop took
    its immediate-reclaim path (a 3 s floor) rather than the 30 s poll sleep.

Both push in the same direction: during an outage the runner claimed MORE work,
FASTER, on the strength of two numbers it could not actually read. The second
branch is the queue-drain accelerator rather than a spawn gate — its two halves
are pinned by `tests/test_mesh_runner_idle_autoclaim.py`, and an earlier draft
of this file called it "unbounded parallelism", which the code does not do.

Every test here was checked against a deliberately broken implementation, not
merely observed to pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "mesh"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fleet_state import active_agent_count, my_claims  # noqa: E402

HOST = "unite-mac-mini"

HEALTHY = {
    "claims": [
        {"linear_id": "RA-1", "machine": HOST, "state": "claimed"},
        {"linear_id": "RA-2", "machine": "other-box", "state": "claimed"},
        {"linear_id": "RA-3", "machine": HOST, "state": "working"},
    ],
    "agents": [
        {"machine": HOST, "state": "busy"},
        {"machine": "other-box", "state": "busy"},
    ],
    "degraded": False,
    "errors": [],
}


def api_returning(payload):
    """Stand in for `runner._api`, which always returns a dict."""
    def _api(method, path, body=None):
        return payload
    return _api


# --------------------------------------------------------------------------
# the green controls first, so a None result below cannot be vacuous
# --------------------------------------------------------------------------

def test_a_healthy_fleet_still_yields_this_hosts_claims():
    claims = my_claims(api_returning(HEALTHY), HOST)
    assert [c["linear_id"] for c in claims] == ["RA-1"]


def test_a_healthy_fleet_still_counts_this_hosts_agents():
    assert active_agent_count(api_returning(HEALTHY), HOST) == 1


def test_a_genuinely_empty_fleet_is_still_empty_not_unknown():
    """The distinction the whole ticket rests on.

    A fleet nobody has joined must keep reading as `[]` and `0` — otherwise
    the fix would simply move the ambiguity, blocking a runner on a healthy
    but idle fleet.
    """
    empty = {"claims": [], "agents": [], "degraded": False, "errors": []}
    assert my_claims(api_returning(empty), HOST) == []
    assert active_agent_count(api_returning(empty), HOST) == 0


# --------------------------------------------------------------------------
# the two failure layers
# --------------------------------------------------------------------------

def test_a_transport_error_reads_as_unknown():
    """`_api` renders any HTTP or transport failure as `{"error": ...}`."""
    broken = api_returning({"error": "HTTP 502", "detail": "bad gateway"})
    assert my_claims(broken, HOST) is None
    assert active_agent_count(broken, HOST) is None


def test_a_degraded_snapshot_reads_as_unknown():
    """A 200 whose body says one Supabase source failed.

    This is the case the endpoint fix introduced: the request succeeded, the
    lists are present and empty, and only `degraded` distinguishes it from a
    fleet nobody has joined.
    """
    degraded = {
        "claims": [], "agents": [],
        "degraded": True,
        "errors": [{"source": "claims", "status": 200, "reason": "not-json"}],
    }
    assert my_claims(api_returning(degraded), HOST) is None
    assert active_agent_count(api_returning(degraded), HOST) is None


def test_a_non_dict_response_reads_as_unknown():
    """Defence in depth: nothing downstream should assume the shape."""
    assert my_claims(api_returning(None), HOST) is None
    assert active_agent_count(api_returning("boom"), HOST) is None


def test_a_dict_where_rows_belong_does_not_crash_the_caller():
    """The pre-fix endpoint returned PostgREST's JSON error object verbatim.

    Iterating a dict yields its keys as strings, and `.get` on a string raises
    AttributeError — so this crashed the runner rather than misleading it. The
    endpoint no longer emits that shape; this pins that the consumer would
    survive it anyway, since it is the layer that would take the exception.
    """
    weird = {"claims": {"message": "permission denied"}, "agents": {"x": 1},
             "degraded": False, "errors": []}
    assert my_claims(api_returning(weird), HOST) == []
    assert active_agent_count(api_returning(weird), HOST) == 0


# --------------------------------------------------------------------------
# the consequence, at the level where it mattered
# --------------------------------------------------------------------------

def _runner(monkeypatch, api):
    """Load mesh/runner.py with `_api` stubbed and a known HOST."""
    from mesh_helpers import load_module
    monkeypatch.setenv("MESH_MAX_CLAIMS", "1")
    mod = load_module("mesh_runner_fleet_state", "mesh/runner.py")
    monkeypatch.setattr(mod, "_api", api)
    monkeypatch.setattr(mod, "HOST", HOST)
    return mod


def test_get_work_does_not_self_claim_while_the_fleet_is_unreadable(monkeypatch):
    """THE POINT OF THE RUNNER HALF.

    Pre-fix, an unreadable fleet gave `my_claims() == []`, which `get_work()`
    read as "I hold nothing" and answered by POSTing /api/mesh/claim/self —
    taking on NEW work during an outage while its existing claims were merely
    invisible. It must now hold instead, and specifically must not issue that
    POST at all.
    """
    calls = []

    def api(method, path, body=None):
        calls.append(path)
        if path == "/api/mesh/fleet":
            return {"error": "HTTP 502", "detail": "bad gateway"}
        return {"claimed": {"linear_id": "RA-NEW", "machine": HOST}}

    mod = _runner(monkeypatch, api)
    assert mod.get_work() == []
    assert "/api/mesh/claim/self" not in calls, "self-claimed during an outage"


def test_get_work_still_self_claims_when_the_fleet_is_genuinely_empty(monkeypatch):
    """GREEN CONTROL for the test above.

    An idle-but-healthy fleet must still reach the self-claim path, or the fix
    would have stopped the runner picking up work at all — trading a silent
    failure for a silent stall.
    """
    def api(method, path, body=None):
        if path == "/api/mesh/fleet":
            return {"claims": [], "agents": [], "degraded": False, "errors": []}
        return {"claimed": {"linear_id": "RA-NEW", "machine": HOST}}

    mod = _runner(monkeypatch, api)
    assert [c["linear_id"] for c in mod.get_work()] == ["RA-NEW"]


# --------------------------------------------------------------------------
# the agent-count half, at the loop level where its branch actually sits
# --------------------------------------------------------------------------

class FleetDegradesAfterFirstRead:
    """A mesh API whose fleet read succeeds once, then fails.

    Not a contrived shape: `get_work()` and the reclaim branch issue TWO
    separate `GET /api/mesh/fleet` calls per iteration, so the second can fail
    after the first succeeded. That is the only path by which a None agent
    count is reachable at all — an outage that starts earlier is caught by
    `get_work()` returning `[]` — so it is the case the guard has to cover.
    """

    def __init__(self, queue):
        self.queue = list(queue)
        self.fleet_reads = 0
        self.worked: list[str] = []
        self.healthy_reads = 1

    def api(self, method, path, body=None):
        if path == "/api/mesh/fleet":
            self.fleet_reads += 1
            if self.fleet_reads > self.healthy_reads:
                return {"error": "HTTP 502", "detail": "bad gateway"}
            return {"claims": [], "agents": [], "degraded": False, "errors": []}
        if path == "/api/mesh/claim/self":
            if not self.queue:
                return {"claimed": None}
            return {"claimed": {"linear_id": self.queue.pop(0), "machine": HOST}}
        if path == "/api/mesh/claim/update":
            if body["state"] == "done":
                self.worked.append(body["linear_id"])
        return {}


def _loop(monkeypatch, tmp_path, server):
    """`mesh/runner.py` wired for one pass of `main()`, no real processes.

    `time.sleep` raises on the full poll interval, so reaching it IS the
    assertion that the loop chose to back off rather than re-claim.
    """
    from mesh_helpers import Break, ImmediateProc, load_module
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    monkeypatch.delenv("MESH_MAX_CLAIMS", raising=False)
    mod = load_module("mesh_runner_agent_count", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", HOST)
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MAX_PARALLEL", 4)   # never at capacity
    monkeypatch.setattr(mod, "MAX_CLAIMS", 0)
    monkeypatch.setattr(mod, "IDLE_RECLAIM_DELAY", 0.01)
    monkeypatch.setattr(mod, "_api", server.api)
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: ImmediateProc())
    sleeps: list[float] = []

    def fake_sleep(secs):
        sleeps.append(secs)
        if secs == mod.POLL_INTERVAL:
            raise Break()

    monkeypatch.setattr(mod.time, "sleep", fake_sleep)
    return mod, sleeps, Break


def _drive(mod, Break):
    """Run `main()` to the poll sleep, which `_loop` turns into `Break`."""
    argv = sys.argv
    sys.argv = ["runner"]
    try:
        import pytest
        with pytest.raises(Break):
            mod.main()
    finally:
        sys.argv = argv


def test_an_unreadable_agent_count_backs_off_instead_of_reclaiming(monkeypatch, tmp_path):
    """THE AGENT-COUNT HALF.

    Pre-fix `active_agent_count()` returned 0 for an unreadable fleet, `0 <
    MAX_PARALLEL` was true, and the loop skipped its 30 s poll sleep to
    re-claim after 3 s — accelerating exactly when it had least information.
    It must now fall through to the poll sleep, and must not take a second
    ticket in the same wake.
    """
    server = FleetDegradesAfterFirstRead(["RA-A", "RA-B"])
    mod, sleeps, Break = _loop(monkeypatch, tmp_path, server)
    _drive(mod, Break)
    assert server.worked == ["RA-A"], "took more work while the fleet was unreadable"
    assert mod.IDLE_RECLAIM_DELAY not in sleeps, "re-claimed instead of backing off"
    assert sleeps.count(mod.POLL_INTERVAL) == 1


def test_a_readable_agent_count_still_drains_the_queue(monkeypatch, tmp_path):
    """GREEN CONTROL.

    With the fleet readable throughout, the reclaim branch must still fire —
    otherwise the guard would have turned every drain into a 30 s wait and
    traded a wrong number for a slow runner.
    """
    server = FleetDegradesAfterFirstRead(["RA-A", "RA-B"])
    server.healthy_reads = 99
    mod, sleeps, Break = _loop(monkeypatch, tmp_path, server)
    _drive(mod, Break)
    assert server.worked == ["RA-A", "RA-B"]
    assert mod.IDLE_RECLAIM_DELAY in sleeps
