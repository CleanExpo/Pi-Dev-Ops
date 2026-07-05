"""tests/test_mesh_claim_reap.py — UNI-2301.

Proves the stale-claim reaper: a runner that dies mid-claim (up to a 3600s
agent run per mesh/runner.py) must not lock a ticket in mesh_work_claims
forever behind the mesh_work_claims_one_open partial unique index.

* A claim past MESH_CLAIM_TTL_MINUTES is reaped (state -> released,
  released_at stamped) ONLY when the claiming machine's heartbeat is itself
  stale or absent (mesh_fleet.is_stale) — a live heartbeat means the runner
  may legitimately still be inside its run, so it is left alone.
* A reaped claim's Linear issue is moved back to the team's first
  unstarted-type state so it re-enters the mesh:auto pool and becomes
  claimable again.
* POST /api/mesh/claims/reap is auth-gated like every sibling route.

Fully offline: the HTTP/Supabase/Linear layers are mocked.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}


class FakeSupabase:
    """Models mesh_work_claims + mesh_fleet for the reap sweep.

    claims: {linear_id: {"id", "machine", "state", "claimed_at"}}
    fleet_stale: {host: is_stale bool}
    """

    def __init__(self, claims=None, fleet_stale=None):
        self.claims = claims or {}
        self.fleet_stale = fleet_stale or {}
        self.patched: list[str] = []  # linear_ids released

    def sb(self, method, path, body=None, *, prefer=""):
        if method == "GET" and path.startswith("mesh_work_claims?select=id,linear_id,machine,claimed_at"):
            cutoff_str = path.split("claimed_at=lt.")[1]
            import urllib.parse as _up
            cutoff = datetime.fromisoformat(_up.unquote(cutoff_str))
            rows = [
                {"id": lid, "linear_id": lid, "machine": c["machine"], "claimed_at": c["claimed_at"].isoformat()}
                for lid, c in self.claims.items()
                if c["state"] in ("claimed", "working") and c["claimed_at"] < cutoff
            ]
            return 200, json.dumps(rows)
        if method == "GET" and path == "mesh_fleet?select=host,is_stale":
            return 200, json.dumps([{"host": h, "is_stale": s} for h, s in self.fleet_stale.items()])
        if method == "PATCH" and path.startswith("mesh_work_claims?id=eq."):
            lid = path.split("id=eq.")[1].split("&")[0]
            if lid in self.claims and self.claims[lid]["state"] in ("claimed", "working"):
                self.claims[lid]["state"] = "released"
                self.patched.append(lid)
            return 204, ""
        return 200, "[]"


class FakeLinear:
    """Models the issue(id) lookup + team states + issueUpdate mutation used
    to move a reaped issue back to an unstarted state."""

    def __init__(self, *, team_of=None):
        self.team_of = team_of or {}  # linear_id -> team_id
        self.moved_to_unstarted: set[str] = set()

    def graphql(self, query: str) -> dict:
        if query.startswith("query{issue(id:"):
            lid = query.split('id:"')[1].split('"')[0]
            team_id = self.team_of.get(lid)
            if not team_id:
                return {"issue": None}
            return {"issue": {"id": lid, "team": {"id": team_id}}}
        if query.startswith("query{team"):
            return {"team": {"states": {"nodes": [
                {"id": "st-todo", "type": "unstarted", "position": 0},
                {"id": "st-progress", "type": "started", "position": 1}]}}}
        if query.startswith("mutation{issueUpdate"):
            issue_id = query.split('id:"')[1].split('"')[0]
            state_id = query.split('stateId:"')[1].split('"')[0]
            if state_id == "st-todo":
                self.moved_to_unstarted.add(issue_id)
            return {"issueUpdate": {"success": True}}
        return {}


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


def _old(minutes):
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def test_reap_endpoint_401_without_secret(mesh_client):
    client, _ = mesh_client
    assert client.post("/api/mesh/claims/reap").status_code == 401


def test_dead_runner_reaped_ticket_claimable_again(mesh_client):
    """working row past TTL + stale/absent heartbeat -> reaped, and the ticket
    is immediately claimable again through claim_self."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(100)}},
        fleet_stale={"nodeA": True},
    )
    fl = FakeLinear(team_of={"UNI-A": "team-1"})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == [{"linear_id": "UNI-A", "machine": "nodeA"}]
    assert fake.claims["UNI-A"]["state"] == "released"
    assert fl.moved_to_unstarted == {"UNI-A"}


def test_live_runner_not_reaped_when_heartbeat_fresh(mesh_client):
    """working row past TTL but a FRESH heartbeat for the claiming machine ->
    left alone, the runner may legitimately still be inside its run."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(100)}},
        fleet_stale={"nodeA": False},
    )
    mesh._sb = fake.sb
    mesh._linear_graphql = lambda q: pytest.fail("Linear should not be touched when nothing is reaped")
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == []
    assert fake.claims["UNI-A"]["state"] == "working"


def test_ttl_boundary_fresh_claim_not_reaped(mesh_client):
    """A claim younger than MESH_CLAIM_TTL_MINUTES is never a reap candidate,
    even with no heartbeat at all for its machine."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(5)}},
        fleet_stale={},
    )
    mesh._sb = fake.sb
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == []
    assert fake.claims["UNI-A"]["state"] == "working"


def test_reap_absent_machine_heartbeat_is_reaped(mesh_client):
    """machine has no mesh_fleet row at all (never heartbeated, or long gone)
    -> treated as absent -> reaped."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "ghost-node", "state": "claimed", "claimed_at": _old(200)}},
        fleet_stale={},  # no row for ghost-node
    )
    fl = FakeLinear(team_of={"UNI-A": "team-1"})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == [{"linear_id": "UNI-A", "machine": "ghost-node"}]


def test_claim_self_piggybacks_reap(mesh_client):
    """claim_self runs the sweep inline: a dead runner's stale claim is freed
    and the Linear issue re-enters the pool in the same request that then
    self-claims the now-free ticket."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(100)}},
        fleet_stale={"nodeA": True},
    )
    fl = FakeLinear(team_of={"UNI-A": "team-1"})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    client.post("/api/mesh/claim/self", json={"host": "nodeB"}, headers=HDR)
    # After the reap, UNI-A moved to unstarted so the mesh:auto query (also
    # faked via _linear_graphql) would surface it again in a real deployment;
    # here we assert the reap itself fired as part of the same call.
    assert fake.claims["UNI-A"]["state"] == "released"
    assert fl.moved_to_unstarted == {"UNI-A"}


def test_dispatch_piggybacks_reap(mesh_client):
    """dispatch runs the same sweep inline before assigning work."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(100)}},
        fleet_stale={"nodeA": True},
    )
    fl = FakeLinear(team_of={"UNI-A": "team-1"})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    client.post("/api/mesh/dispatch", json={"linear_ids": []}, headers=HDR)
    assert fake.claims["UNI-A"]["state"] == "released"
    assert fl.moved_to_unstarted == {"UNI-A"}
