"""tests/test_mesh_runner_idle_autoclaim.py — UNI-2248.

Proves the acceptance logic for the mesh runner's idle detection + atomic
self-claim without needing two live nodes:

* Server `/api/mesh/claim/self` picks the top-priority unclaimed `mesh:auto`
  ticket and relies on the `mesh_work_claims_one_open` unique partial index so a
  racing double-claim is rejected (409) — two idle nodes never take the same
  ticket.
* The runner drains a queue: after a claim completes it immediately pulls the
  next (idle detection) instead of sleeping, honours the HARD_STOP kill switch
  and the MAX_CLAIMS cost cap, and writes the live-task breadcrumb.
* The heartbeat surfaces that breadcrumb as `current_task` per agent.

Fully offline: the HTTP/Supabase/Linear layers are mocked.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Fake Supabase enforcing the partial unique index ─────────────────────────
class FakeSupabase:
    """Models mesh_work_claims + the one-open partial unique index: a POST for a
    linear_id already in the open set is rejected with 409 (23505), exactly like
    the real index. This is the atomic guard the acceptance test relies on."""

    def __init__(self, open_ids=()):
        self.open = set(open_ids)
        self.inserts: list[str] = []

    def sb(self, method, path, body=None, *, prefer=""):
        if method == "POST" and path == "mesh_work_claims":
            lid = body["linear_id"]
            if lid in self.open:
                return 409, '{"code":"23505","message":"duplicate key"}'
            self.open.add(lid)
            self.inserts.append(lid)
            return 201, ""
        if method == "GET" and path.startswith("mesh_work_claims?select=linear_id"):
            return 200, json.dumps([{"linear_id": lid} for lid in sorted(self.open)])
        return 200, "[]"


@pytest.fixture
def mesh_client(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh


def _tickets(*specs):
    # specs: (identifier, priority)
    return {"issues": {"nodes": [{"id": i, "identifier": i, "title": i, "priority": p}
                                 for i, p in specs]}}


HDR = {"X-Pi-CEO-Secret": "test-secret"}


# ── Server: auth + priority + atomic guard ───────────────────────────────────
def test_claim_self_401_without_secret(mesh_client):
    client, _ = mesh_client
    assert client.post("/api/mesh/claim/self", json={"host": "nodeA"}).status_code == 401


def test_claim_self_picks_top_priority(mesh_client):
    client, mesh = mesh_client
    fake = FakeSupabase()
    # listed out of order; Urgent(1) must be claimed before Medium(3)/Low(4)
    monkeypatch_linear(mesh, _tickets(("UNI-C", 3), ("UNI-A", 1), ("UNI-B", 4)))
    mesh._sb = fake.sb
    r = client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR).json()
    assert r["claimed"] == {"linear_id": "UNI-A", "machine": "nodeA"}


def test_claim_self_empty_queue_returns_null(mesh_client):
    client, mesh = mesh_client
    monkeypatch_linear(mesh, _tickets())
    mesh._sb = FakeSupabase().sb
    assert client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR).json()["claimed"] is None


def test_two_node_race_never_double_claims(mesh_client):
    """Both nodes read an EMPTY open set (worst-case stale read) and both try to
    claim the only ticket. The unique index rejects the loser → exactly one claim."""
    client, mesh = mesh_client
    fake = FakeSupabase()
    monkeypatch_linear(mesh, _tickets(("UNI-A", 1)))
    mesh._sb = fake.sb
    # Force the stale-read race: both nodes believe nothing is claimed yet.
    monkeypatch_open(mesh, set())
    r1 = client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR).json()
    r2 = client.post("/api/mesh/claim/self", json={"host": "nodeB"}, headers=HDR).json()
    winners = [r for r in (r1, r2) if r["claimed"]]
    assert len(winners) == 1, (r1, r2)
    assert fake.inserts == ["UNI-A"]  # inserted exactly once fleet-wide


def test_three_tickets_two_nodes_drain_no_doublework(mesh_client):
    """Acceptance: 3 mesh:auto tickets, 2 nodes → queue drains, no ticket twice."""
    client, mesh = mesh_client
    fake = FakeSupabase()
    monkeypatch_linear(mesh, _tickets(("UNI-A", 1), ("UNI-B", 2), ("UNI-C", 3)))
    mesh._sb = fake.sb
    claimed = []
    for host in ("nodeA", "nodeB", "nodeA", "nodeB"):  # more calls than tickets
        r = client.post("/api/mesh/claim/self", json={"host": host}, headers=HDR).json()
        if r["claimed"]:
            claimed.append(r["claimed"]["linear_id"])
    assert sorted(claimed) == ["UNI-A", "UNI-B", "UNI-C"]      # every ticket taken
    assert len(claimed) == len(set(claimed))                   # none twice
    assert claimed[0] == "UNI-A"                               # highest priority first


def monkeypatch_linear(mesh, data):
    mesh._linear_graphql = lambda q: data


def monkeypatch_open(mesh, ids):
    mesh._open_claim_ids = lambda: set(ids)


# ── Runner: idle-detection drain, kill switch, cost cap, breadcrumb ──────────
class FakeMeshServer:
    """In-memory stand-in for the /api/mesh/* endpoints the runner calls."""

    def __init__(self, queue):
        self.queue = list(queue)        # unclaimed mesh:auto ids, top-priority first
        self.claims: dict[str, str] = {}  # linear_id -> state
        self.worked: list[str] = []

    def api(self, method, path, body=None):
        if path == "/api/mesh/fleet":
            open_claims = [{"linear_id": k, "machine": "TESTNODE", "state": v}
                           for k, v in self.claims.items() if v in ("claimed", "working")]
            return {"claims": open_claims, "agents": []}
        if path == "/api/mesh/claim/self":
            if not self.queue:
                return {"claimed": None}
            lid = self.queue.pop(0)
            self.claims[lid] = "claimed"
            return {"claimed": {"linear_id": lid, "machine": "TESTNODE"}}
        if path == "/api/mesh/claim/update":
            self.claims[body["linear_id"]] = body["state"]
            if body["state"] == "done":
                self.worked.append(body["linear_id"])
            return {"ok": True}
        return {}


class _Break(Exception):
    pass


@pytest.fixture
def runner(monkeypatch, tmp_path):
    mod = _load("mesh_runner", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "MAX_PARALLEL", 4)  # never at capacity in test
    monkeypatch.setattr(mod, "MAX_CLAIMS", 0)
    # Never spawn a real agent/git worktree.
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: (_ for _ in ()).throw(_Break()))
    return mod


def _run_main(mod, argv):
    import sys as _sys
    old = _sys.argv
    _sys.argv = argv
    try:
        with pytest.raises(_Break):
            mod.main()
    finally:
        _sys.argv = old


def _main_returns(mod):
    """Run main() to a clean return (no _Break) with a neutral argv."""
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["runner"]
    try:
        return mod.main()
    finally:
        _sys.argv = old


def test_runner_drains_queue_via_idle_detection(runner):
    """3 queued tickets → the runner pulls each one back-to-back (no sleep between)
    and drains the whole queue in a single wake, then sleeps only when empty."""
    server = FakeMeshServer(["UNI-A", "UNI-B", "UNI-C"])
    runner._api = server.api
    _run_main(runner, ["runner"])          # loops; _Break fires on the first sleep
    assert server.worked == ["UNI-A", "UNI-B", "UNI-C"]
    assert len(server.worked) == len(set(server.worked))  # no double-work


def test_runner_prefers_preassigned_over_self_claim(runner):
    server = FakeMeshServer([])            # nothing to self-claim
    server.claims["UNI-PRE"] = "claimed"   # dispatcher pre-assigned one
    runner._api = server.api
    _run_main(runner, ["runner"])
    assert server.worked == ["UNI-PRE"]


def test_runner_honours_kill_switch(runner, tmp_path):
    (tmp_path / "HARD_STOP").write_text("stop")
    server = FakeMeshServer(["UNI-A"])
    runner._api = server.api
    assert _main_returns(runner) == 0      # returns immediately, no _Break
    assert server.worked == []             # no work done under HARD_STOP


def test_runner_honours_max_claims_cost_cap(runner, monkeypatch):
    monkeypatch.setattr(runner, "MAX_CLAIMS", 2)
    server = FakeMeshServer(["UNI-A", "UNI-B", "UNI-C"])
    runner._api = server.api
    assert _main_returns(runner) == 0      # stops at the cap, never reaches sleep
    assert server.worked == ["UNI-A", "UNI-B"]  # capped at 2, UNI-C untouched


def test_runner_writes_live_task_breadcrumb(runner):
    server = FakeMeshServer([])
    runner._api = server.api
    runner.run_claim({"linear_id": "UNI-A"}, dry_run=False)
    # after completion the breadcrumb is reset to idle
    crumb = json.loads(runner.STATE_FILE.read_text())
    assert crumb["runtime"] == runner.AGENT_CMD
    assert crumb["state"] == "idle" and crumb["current_task"] is None
    # and the claim was reported working then done (working state surfaced live)
    assert server.claims["UNI-A"] == "done"


# ── Heartbeat: breadcrumb → current_task per agent ───────────────────────────
@pytest.fixture
def heartbeat(monkeypatch, tmp_path):
    mod = _load("mesh_heartbeat", "mesh/heartbeat.py")
    monkeypatch.setattr(mod, "MESH_RUNNER_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(mod, "_run", lambda *a, **k: "")  # no live procs found
    return mod, tmp_path


def _write_crumb(path, **kw):
    import time as _t
    base = {"runtime": "claude", "current_task": "UNI-2248", "state": "working", "ts": int(_t.time())}
    base.update(kw)
    Path(path).write_text(json.dumps(base))


def test_heartbeat_surfaces_current_task(heartbeat):
    mod, tmp_path = heartbeat
    _write_crumb(tmp_path / "state.json")
    agents = mod.running_agent_sessions()
    claude = [a for a in agents if a["runtime"] == "claude"]
    assert claude and claude[0]["current_task"] == "UNI-2248"
    assert claude[0]["state"] == "working"


def test_heartbeat_ignores_idle_breadcrumb(heartbeat):
    mod, tmp_path = heartbeat
    _write_crumb(tmp_path / "state.json", current_task=None, state="idle")
    assert mod.running_agent_sessions() == []  # no fabricated idle agent


def test_heartbeat_ignores_stale_breadcrumb(heartbeat):
    mod, tmp_path = heartbeat
    _write_crumb(tmp_path / "state.json", ts=0)  # ancient
    assert mod.running_agent_sessions() == []
