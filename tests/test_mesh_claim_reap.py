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

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_reap_helpers import HDR, FakeLinear, FakeSupabase  # noqa: E402


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


# ── UNI-2303: mesh hardening batch (4 non-blocking findings from the #510/#511
#    adversarial reviews) ────────────────────────────────────────────────────

def test_released_claim_update_reverses_linear_issue(mesh_client):
    """Kill-released Linear reversal: a claim_update to state='released' (e.g.
    a runner HARD_STOP) must move the Linear issue back to the team's
    unstarted state, same as a reaped claim — otherwise it strands In
    Progress forever even though the mesh_work_claims row is freed."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(1)}})
    fl = FakeLinear(team_of={"UNI-A": "team-1"})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    r = client.post("/api/mesh/claim/update",
                     json={"linear_id": "UNI-A", "state": "released"}, headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "linear_id": "UNI-A", "state": "released"}
    assert fl.moved_to_unstarted == {"UNI-A"}


def test_released_claim_update_succeeds_when_linear_errors(mesh_client):
    """The claim update itself must not fail even if the Linear reversal
    blows up outright — it's guarded and best-effort like _mark_issue_reaped."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(1)}})
    mesh._sb = fake.sb

    def _boom(q):
        raise RuntimeError("linear down")

    mesh._linear_graphql = _boom
    r = client.post("/api/mesh/claim/update",
                     json={"linear_id": "UNI-A", "state": "released"}, headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "linear_id": "UNI-A", "state": "released"}


def test_non_released_claim_update_does_not_touch_linear(mesh_client):
    """Only a released transition triggers the reversal — done/working/failed
    must not fire a spurious Linear transition."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(1)}})
    mesh._sb = fake.sb
    mesh._linear_graphql = lambda q: pytest.fail("Linear should not be touched for a non-released transition")
    r = client.post("/api/mesh/claim/update",
                     json={"linear_id": "UNI-A", "state": "done"}, headers=HDR)
    assert r.status_code == 200


def test_released_update_zero_row_does_not_touch_linear(mesh_client):
    """A `released` update whose PATCH matches 0 rows (claim already done, or
    absent entirely) must NOT fire the Linear reversal — otherwise a stale
    runner's HARD_STOP teardown for a claim the reaper already released and
    another runner re-claimed would yank the fresh claim's ticket back to
    Todo. The update itself still 200s (idempotent report)."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "done", "claimed_at": _old(1)}})
    mesh._sb = fake.sb
    mesh._linear_graphql = lambda q: pytest.fail("Linear must not be touched on a 0-row released update")
    # already-done claim
    r = client.post("/api/mesh/claim/update",
                     json={"linear_id": "UNI-A", "state": "released"}, headers=HDR)
    assert r.status_code == 200
    assert fake.claims["UNI-A"]["state"] == "done"  # untouched
    # claim absent entirely
    r = client.post("/api/mesh/claim/update",
                     json={"linear_id": "UNI-GHOST", "state": "released"}, headers=HDR)
    assert r.status_code == 200


def test_reap_zero_row_patch_records_nothing(mesh_client):
    """F1: a 0-row release PATCH (raced by a concurrent reap or the runner
    itself) must not record a reap or fire a redundant Linear transition."""
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working", "claimed_at": _old(100)}},
        fleet_stale={"nodeA": True},
        race_lids={"UNI-A"},
    )
    mesh._sb = fake.sb
    mesh._linear_graphql = lambda q: pytest.fail("Linear must not be touched on a 0-row race")
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == []


def test_claim_self_survives_reap_sweep_error(mesh_client):
    """F2: a Supabase hiccup in the inline reap sweep must not 502 claim_self —
    it degrades to a no-op sweep and the self-claim flow still runs."""
    client, mesh = mesh_client

    def _boom_sb(method, path, body=None, *, prefer=""):
        if path.startswith("mesh_work_claims?select=id,linear_id"):
            raise HTTPException(502, "supabase down")
        return 200, "[]"

    mesh._sb = _boom_sb
    mesh._linear_graphql = lambda q: {"issues": {"nodes": []}}
    r = client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR)
    assert r.status_code == 200
    assert r.json() == {"claimed": None, "reason": "queue empty or fully claimed"}


def test_dispatch_survives_reap_sweep_error(mesh_client):
    """F2: same guarantee on the dispatch hot path."""
    client, mesh = mesh_client

    def _boom_sb(method, path, body=None, *, prefer=""):
        if path.startswith("mesh_work_claims?select=id,linear_id"):
            raise HTTPException(502, "supabase down")
        return 200, "[]"

    mesh._sb = _boom_sb
    mesh._linear_graphql = lambda q: {"issues": {"nodes": []}}
    r = client.post("/api/mesh/dispatch", json={"linear_ids": []}, headers=HDR)
    assert r.status_code == 200
    assert r.json()["assigned"] == []


def test_explicit_reap_endpoint_still_propagates_errors(mesh_client):
    """The explicit POST /api/mesh/claims/reap trigger is NOT wrapped — ops
    wants to see a Supabase hiccup there, unlike the piggybacked hot paths."""
    client, mesh = mesh_client

    def _boom_sb(method, path, body=None, *, prefer=""):
        raise HTTPException(502, "supabase down")

    mesh._sb = _boom_sb
    r = client.post("/api/mesh/claims/reap", headers=HDR)
    assert r.status_code == 502


def _reload_mesh_with_ttl_env(monkeypatch, value):
    """Force a genuine reimport of app.server.routes.mesh so its module-level
    MESH_CLAIM_TTL_MINUTES picks up a monkeypatched MESH_CLAIM_TTL_MINUTES.
    NOTE: popping sys.modules alone is not enough — the parent package still
    holds a `mesh` attribute from the first import, and `from package import
    submodule` short-circuits on that attribute instead of re-executing the
    module (import's _handle_fromlist only imports what's missing) — so the
    parent attribute must be cleared too. Always reimports back to the
    un-set-env baseline afterward so later tests aren't left with a stale
    clamped value."""
    import importlib
    import app.server.routes as _routes_pkg

    def _hard_reimport():
        sys.modules.pop("app.server.routes.mesh", None)
        if hasattr(_routes_pkg, "mesh"):
            delattr(_routes_pkg, "mesh")
        return importlib.import_module("app.server.routes.mesh")

    monkeypatch.setenv("MESH_CLAIM_TTL_MINUTES", value)
    try:
        return _hard_reimport().MESH_CLAIM_TTL_MINUTES
    finally:
        monkeypatch.undo()
        _hard_reimport()


def test_ttl_floor_clamps_low_configured_value(monkeypatch):
    """F3: an operator setting MESH_CLAIM_TTL_MINUTES below the runner's
    3600s (60min) agent-run cap must be clamped up to the 65min floor."""
    assert _reload_mesh_with_ttl_env(monkeypatch, "30") == 65


def test_ttl_above_floor_passes_through(monkeypatch):
    """F3: a configured value already above the floor is left untouched."""
    assert _reload_mesh_with_ttl_env(monkeypatch, "90") == 90


def test_ttl_explicit_zero_is_also_clamped(monkeypatch):
    """F3: unlike MESH_MAX_CLAIMS, an explicit '0' is NOT a special case here —
    every configured value, including 0, is clamped to the floor."""
    assert _reload_mesh_with_ttl_env(monkeypatch, "0") == 65
