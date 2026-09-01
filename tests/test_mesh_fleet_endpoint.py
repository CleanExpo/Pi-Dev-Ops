"""tests/test_mesh_fleet_endpoint.py — the fleet snapshot the operator confirms with.

`GET /api/mesh/fleet` is the ONLY confirmation `docs/runbooks/fleet-operations.md`
offers for action item 1, the highest-priority switch in the whole fleet
bring-up: "3 rows, all fresh within ~20 s". `mesh/bootstrap.sh` now ends by
pointing at it too ("Confirm from the fleet, not from this output").

It had no test. Four sibling mesh endpoints do — `claim/self`, `claim/update`,
`claims/reap` and `dispatch` are all exercised against a TestClient — so this
was a gap in the read path rather than a convention against testing routes:
the four endpoints that CHANGE fleet state were covered, and the one an
operator READS to decide whether the fleet exists was not.

`is_stale` is the field that gives the confirmation its meaning, and three
things key on it: this endpoint, `_reap_stale_claims()`, and `_online_nodes()`,
which hands work only to nodes where it is falsy. It is computed in SQL by the
`mesh_fleet` view (`mesh/schema/0001_nexus_mesh.sql:65`), not here, so what
these tests pin is that the API passes it through untouched.

Fully offline: the Supabase layer is stubbed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}

# One live node and one that stopped heartbeating. The view derives is_stale as
# (now() - last_seen) > 60s; last_seen is `not null default now()`, so is_stale
# is never NULL — which is what keeps `_online_nodes()` from handing work to a
# machine whose staleness is unknown.
FLEET_ROWS = [
    {"host": "unite-mac-mini", "status": "online", "is_stale": False, "active_agents": 2},
    {"host": "phill-desktop", "status": "online", "is_stale": True, "active_agents": 0},
]
AGENT_ROWS = [{"machine": "unite-mac-mini", "runtime": "claude", "state": "working"}]
CLAIM_ROWS = [{"machine": "unite-mac-mini", "linear_id": "RA-1", "state": "working"}]
SHIP_ROWS = [{"machine": "unite-mac-mini", "repo": "CleanExpo/Pi-Dev-Ops"}]


def _fake_sb(table_bodies: dict):
    """Stub of `mesh._sb`, keyed on the table each query starts with."""
    def sb(method, path, body=None, *, prefer=""):
        """Return the stubbed body for the first table this path matches."""
        for table, payload in table_bodies.items():
            if path.startswith(table):
                return 200, payload
        return 200, "[]"
    return sb


def _ok_bodies() -> dict:
    """The four well-formed table responses a healthy snapshot reads."""
    return {
        "mesh_fleet": json.dumps(FLEET_ROWS),
        "mesh_agents": json.dumps(AGENT_ROWS),
        "mesh_ships": json.dumps(SHIP_ROWS),
        "mesh_work_claims": json.dumps(CLAIM_ROWS),
    }


@pytest.fixture
def mesh_client(monkeypatch):
    """A TestClient over the mesh router alone, with the secret set.

    The module is popped from sys.modules first so it re-reads config at
    import time rather than inheriting a secret from an earlier test file.
    """
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh, monkeypatch


# ── the endpoint exists and is gated ─────────────────────────────────────────


def test_fleet_requires_the_secret(mesh_client):
    """The snapshot names every machine, its load and what it is working on.

    Auth is checked before the 200 tests below so that a passing 200 cannot be
    mistaken for "the endpoint is open".
    """
    client, mesh, mp = mesh_client
    mp.setattr(mesh, "_sb", _fake_sb(_ok_bodies()))
    assert client.get("/api/mesh/fleet").status_code == 401
    assert client.get("/api/mesh/fleet", headers={"X-Pi-CEO-Secret": "wrong"}).status_code == 401


def test_fleet_returns_the_four_lists_the_runbook_reads(mesh_client):
    """THE CONFIRMATION FOR SWITCH 1.

    The runbook tells the operator to read `machines[].is_stale`, then `agents[]`
    for what is running and `claims[]` for open work. If any key were renamed or
    dropped, that instruction would silently stop being followable.
    """
    client, mesh, mp = mesh_client
    mp.setattr(mesh, "_sb", _fake_sb(_ok_bodies()))
    r = client.get("/api/mesh/fleet", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"machines", "agents", "ships", "claims", "degraded", "errors"}
    assert [m["host"] for m in body["machines"]] == ["unite-mac-mini", "phill-desktop"]
    # RA-7392 added the last two. Still an EXACT set: the point of this
    # assertion is that a renamed or dropped key breaks the runbook silently,
    # and that argument does not weaken because the contract grew.
    assert body["degraded"] is False and body["errors"] == []


def test_is_stale_reaches_the_operator_unchanged(mesh_client):
    """`is_stale` is what separates "3 rows" from "3 rows, all fresh".

    A snapshot that returned three machines without distinguishing the dead one
    would pass the operator's row count while describing a fleet that cannot
    take work — `_online_nodes()` skips exactly these rows.
    """
    client, mesh, mp = mesh_client
    mp.setattr(mesh, "_sb", _fake_sb(_ok_bodies()))
    machines = client.get("/api/mesh/fleet", headers=HDR).json()["machines"]
    by_host = {m["host"]: m["is_stale"] for m in machines}
    assert by_host == {"unite-mac-mini": False, "phill-desktop": True}


# ── the empty-vs-broken trade, pinned deliberately ───────────────────────────


def test_a_malformed_supabase_body_is_reported_not_silently_empty(mesh_client):
    """RA-7392: the trade-off this file used to pin is now fixed.

    It previously asserted that a Supabase failure rendered as
    `{"machines": []}` — indistinguishable from a fleet nobody has joined — and
    said so deliberately, because the Mission Control Panel was believed to
    consume this endpoint and a 5xx would blank it.

    That premise was wrong: the dashboard has no reference to `/api/mesh/fleet`
    and the path is absent from ALLOWED_UPSTREAM, so the proxy 403s it. The real
    consumer is `mesh/runner.py`. The list stays empty (nothing here should
    500), but `degraded` and `errors` now make the two states distinguishable.
    """
    client, mesh, mp = mesh_client
    mp.setattr(mesh, "_sb", _fake_sb({"mesh_fleet": "<html>502 Bad Gateway</html>"}))
    r = client.get("/api/mesh/fleet", headers=HDR)
    assert r.status_code == 200
    assert r.json()["machines"] == []
    assert r.json()["degraded"] is True
    assert r.json()["errors"] == [
        {"source": "machines", "status": 200, "reason": "not-json"}
    ]


def test_a_postgrest_error_object_cannot_reach_the_caller_as_a_dict(mesh_client):
    """The failure shape RA-7392 did not describe, and the worse of the two.

    A PostgREST error is VALID JSON — `{"message": ..., "code": ...}` — so it
    never hit the old `except JSONDecodeError` fallback and was returned in the
    field verbatim. `mesh/runner.py` does
    `[c for c in fleet["claims"] if c.get("machine") == HOST]`; iterating a dict
    yields strings and `.get` on a string raises AttributeError, so this
    crashed the caller rather than merely misleading it.
    """
    client, mesh, mp = mesh_client
    body = '{"message":"permission denied for table mesh_fleet","code":"42501"}'
    mp.setattr(mesh, "_sb", _fake_sb({"mesh_fleet": body}))
    machines = client.get("/api/mesh/fleet", headers=HDR).json()["machines"]
    assert isinstance(machines, list) and machines == []
    # and iterating it is safe, which is the property the runner depends on
    assert [m.get("host") for m in machines] == []


def test_an_http_error_status_is_not_read_as_success(mesh_client):
    """`fleet()` discarded the status with `_, body = _sb(...)`.

    A 500 whose body happened to parse as a list therefore looked healthy. The
    rows still come through — they may be all the operator has — but the
    snapshot says so.
    """
    client, mesh, mp = mesh_client
    def _sb_500(method, path, body=None, *, prefer=""):
        return (500, json.dumps(FLEET_ROWS)) if path.startswith("mesh_fleet") else (200, "[]")
    mp.setattr(mesh, "_sb", _sb_500)
    r = client.get("/api/mesh/fleet", headers=HDR).json()
    assert len(r["machines"]) == 2
    assert r["degraded"] is True
    assert r["errors"][0]["reason"] == "http-error" and r["errors"][0]["status"] == 500


def test_the_empty_assertion_above_is_not_vacuous(mesh_client):
    """GREEN CONTROL for the degraded-path tests above.

    Same stub shape, valid JSON: the machines list must come back populated. A
    stub that returned `[]` for everything — a typo'd table prefix, say — would
    satisfy the malformed-body assertion while proving nothing about it.
    """
    client, mesh, mp = mesh_client
    mp.setattr(mesh, "_sb", _fake_sb(_ok_bodies()))
    assert len(client.get("/api/mesh/fleet", headers=HDR).json()["machines"]) == 2
