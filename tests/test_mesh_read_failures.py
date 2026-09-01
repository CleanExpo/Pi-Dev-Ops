"""tests/test_mesh_read_safety.py — a failed read is never "nothing there" (RA-7405).

RA-7392 fixed ONE endpoint that rendered a failed Supabase read as empty lists.
The same defect was then found five more times in the same file, because the
shape that produced it was still available: `_sb` returns `(status, body)`, and
the parser took the BODY alone, so `_, body = _sb("GET", …)` was the natural
call and the status was dropped every time.

This file covers what each read site now DOES when the read fails. The
structural check that stops the shape coming back is its sibling,
`test_mesh_gate_read_safety.py`. Also related:

  * `tests/test_mesh_claim_reap.py` covers the reaper's ordinary behaviour;
    the destructive read case moved HERE, beside its siblings.
  * `tests/test_mesh_fleet_endpoint.py` covers `GET /api/mesh/fleet`.

Every case here pairs with a GREEN CONTROL. A fix in this direction can trade a
wrong answer for a stalled system — a reaper that never reaps, a dispatch that
always 503s — so proving the healthy path still works is half the evidence.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_reap_helpers import HDR, PGRST_401, FakeLinear, FakeSupabase, old  # noqa: E402

PGRST_500 = json.dumps({"message": "internal", "code": "XX000"})


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


def failing_reads(status=500, body=PGRST_500):
    """Every GET fails; writes succeed. Mirrors an expired service-role key."""
    def sb(method, path, req=None, *, prefer=""):
        if method == "GET":
            return status, body
        return 200, "[]"
    return sb


# --------------------------------------------------------------------------
# site 3 — _online_machines: "I cannot tell" is not "nobody is online"
# --------------------------------------------------------------------------

def test_dispatch_reports_a_failed_fleet_read_rather_than_assigning_nothing(mesh_client):
    """Pre-fix this returned `{"assigned": []}` with a 200.

    An operator watching dispatch saw a healthy call that placed no work, which
    is indistinguishable from an empty queue — so the fleet looked idle while
    the server could not read it at all.
    """
    client, mesh = mesh_client
    mesh._sb = failing_reads()
    r = client.post("/api/mesh/dispatch", json={"linear_ids": []}, headers=HDR)
    assert r.status_code == 503
    assert "fleet read failed" in r.json()["detail"]


def test_dispatch_still_works_when_the_fleet_reads_fine(mesh_client):
    """GREEN CONTROL — the 503 above is not simply dispatch being broken."""
    client, mesh = mesh_client

    def sb(method, path, body=None, *, prefer=""):
        if method == "GET" and path.startswith("mesh_fleet"):
            return 200, json.dumps([{"host": "nodeA", "is_stale": False, "load1": 0.1}])
        return 200, "[]"

    mesh._sb = sb
    mesh._linear_graphql = lambda q: {"issues": {"nodes": []}}
    assert client.post("/api/mesh/dispatch", json={"linear_ids": []},
                       headers=HDR).status_code == 200


# --------------------------------------------------------------------------
# site 4 — _open_claim_ids: a unique index is a backstop, not a design
# --------------------------------------------------------------------------

def test_open_claim_ids_refuses_to_answer_from_a_failed_read(mesh_client):
    """Pre-fix this returned an empty set: "nothing is claimed anywhere".

    `claim/self` would then hand out a ticket another machine already held, and
    only the `mesh_work_claims_one_open` partial unique index stopped the double
    claim — a database constraint catching an application-layer lie.
    """
    _, mesh = mesh_client
    mesh._sb = failing_reads()
    with pytest.raises(HTTPException) as e:
        mesh._open_claim_ids()
    assert e.value.status_code == 503
    assert "cannot tell what is claimed" in e.value.detail


def test_open_claim_ids_still_reads_a_healthy_response(mesh_client):
    """GREEN CONTROL."""
    _, mesh = mesh_client
    mesh._sb = lambda *a, **k: (200, json.dumps([{"linear_id": "UNI-1"}]))
    assert mesh._open_claim_ids() == {"UNI-1"}


def test_an_empty_claim_table_is_still_empty_not_an_error(mesh_client):
    """The distinction the ticket rests on: a genuinely empty table must keep
    reading as empty, or the fix would block claiming on a healthy system."""
    _, mesh = mesh_client
    mesh._sb = lambda *a, **k: (200, "[]")
    assert mesh._open_claim_ids() == set()


# --------------------------------------------------------------------------
# site 5 — GET /api/mesh/claims, the unfixed sibling of #717's endpoint
# --------------------------------------------------------------------------

def test_claims_endpoint_reports_degraded_instead_of_an_empty_list(mesh_client):
    """A runner asking "what's mine?" got `{"claims": []}` — 'you hold nothing'
    — from a read that never happened. Same contract as /api/mesh/fleet now."""
    client, mesh = mesh_client
    mesh._sb = failing_reads()
    body = client.get("/api/mesh/claims", headers=HDR).json()
    assert body["claims"] == []
    assert body["degraded"] is True
    assert body["errors"] == [{"source": "claims", "reason": "http-500"}]


def test_claims_endpoint_is_not_degraded_when_healthy(mesh_client):
    """GREEN CONTROL — an idle runner must read as idle, not as broken."""
    client, mesh = mesh_client
    mesh._sb = lambda *a, **k: (200, "[]")
    body = client.get("/api/mesh/claims", headers=HDR).json()
    assert body == {"claims": [], "degraded": False, "errors": []}


# ── RA-7405: a failed liveness read must not reap a live runner ──────────────
#
# The guard above (`test_live_runner_not_reaped_when_heartbeat_fresh`) protects
# a machine whose heartbeat is fresh. It was disarmed by the one failure it
# most needed to survive: an unreadable `mesh_fleet` gave an empty liveness
# map, `stale_by_host.get(machine)` returned None rather than False, and the
# `continue` never fired — so EVERY past-TTL claim was released and its Linear
# issue dragged back to Todo.
#
# The trigger is not an outage. `_sb` raises on a transport error, so that case
# already aborted. It is a non-2xx that RETURNS: an expired or rotated
# service-role key, or an RLS change, answering 401/403 with a valid JSON error
# body on every read.




def _live_claim_past_ttl():
    """One past-TTL claim on a machine that is demonstrably ALIVE."""
    return {"UNI-LIVE": {"id": "UNI-LIVE", "machine": "nodeA",
                         "state": "claimed", "claimed_at": old(200)}}


def test_live_runner_survives_an_unreadable_liveness_read(mesh_client):
    """THE DESTRUCTIVE CASE. 401 on the liveness read, machine alive."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims=_live_claim_past_ttl(), fleet_stale={"nodeA": False},
                        fleet_status=401, fleet_body=PGRST_401)
    fl = FakeLinear(team_of={"UNI-LIVE": "team-1"})
    mesh._sb, mesh._linear_graphql = fake.sb, fl.graphql
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert r["reaped"] == [], "reaped a live runner's claim on a blind guess"
    assert fake.patched == [], "PATCHed a claim it could not justify releasing"
    assert fl.moved_to_unstarted == set(), "dragged a live runner's ticket back to Todo"
    assert fake.claims["UNI-LIVE"]["state"] == "claimed"


def test_the_assertion_above_is_not_vacuous(mesh_client):
    """GREEN CONTROL 1 — the same claim IS reaped when liveness reads fine and
    says the machine is stale. Without this, the test above would pass equally
    well against a reaper that had simply been switched off."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims=_live_claim_past_ttl(), fleet_stale={"nodeA": True})
    fl = FakeLinear(team_of={"UNI-LIVE": "team-1"})
    mesh._sb, mesh._linear_graphql = fake.sb, fl.graphql
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    assert [x["linear_id"] for x in r["reaped"]] == ["UNI-LIVE"]
    assert fl.moved_to_unstarted == {"UNI-LIVE"}


def test_an_unreadable_candidate_read_is_logged_not_silently_empty(mesh_client, caplog):
    """The benign half of the same defect, made explicit.

    ASSERTED ON THE LOG DELIBERATELY. A failed candidate read produced an empty
    list, and an empty list also means "nothing is past TTL" — so the sweep
    no-opped either way and no assertion on `reaped` can tell the two apart. A
    first draft of this test asserted exactly that and passed against the
    unfixed code; the sabotage harness caught it.

    The observable difference is the warning, and it is the one that matters
    operationally: a dead service-role key otherwise looks identical to a quiet
    fleet, forever.
    """
    client, mesh = mesh_client
    mesh._sb = lambda method, path, body=None, *, prefer="": (401, PGRST_401)
    with caplog.at_level(logging.WARNING, logger="pi-ceo.mesh.reaper"):
        assert client.post("/api/mesh/claims/reap", headers=HDR).json()["reaped"] == []
    assert any("candidate read failed" in r.getMessage() for r in caplog.records), \
        "a failed candidate read passed silently"


def test_a_quiet_fleet_logs_no_warning(mesh_client, caplog):
    """GREEN CONTROL for the test above — an empty-but-healthy sweep must stay
    quiet, or the warning becomes noise and stops meaning anything."""
    client, mesh = mesh_client
    mesh._sb = FakeSupabase().sb
    with caplog.at_level(logging.WARNING, logger="pi-ceo.mesh.reaper"):
        assert client.post("/api/mesh/claims/reap", headers=HDR).json()["reaped"] == []
    assert not caplog.records


def test_a_liveness_body_that_is_not_a_list_is_treated_as_unreadable(mesh_client):
    """200 + a PostgREST error OBJECT. Valid JSON, so it never hit the old
    parser's JSONDecodeError fallback — it came back as a dict and iterating it
    yielded strings. Same class as the endpoint defect fixed in #717."""
    client, mesh = mesh_client
    fake = FakeSupabase(claims=_live_claim_past_ttl(), fleet_stale={"nodeA": False})
    original = fake.sb

    def sb(method, path, body=None, *, prefer=""):
        if method == "GET" and path == "mesh_fleet?select=host,is_stale":
            return 200, json.dumps({"message": "permission denied", "code": "42501"})
        return original(method, path, body, prefer=prefer)

    mesh._sb, mesh._linear_graphql = sb, FakeLinear(team_of={"UNI-LIVE": "team-1"}).graphql
    assert client.post("/api/mesh/claims/reap", headers=HDR).json()["reaped"] == []
    assert fake.patched == []
