"""tests/test_mesh_reap_done_guard.py — UNI-2753.

The stale-claim reaper must never reopen a ticket a human already closed.

A claim row can outlive its ticket: the work finishes, someone moves the Linear
issue to Done (or Canceled), but the runner died before releasing its
mesh_work_claims row. ~90 minutes later the reaper released the row AND moved
the issue back to the team's first unstarted state (Todo), so closed tickets
kept reappearing in the mesh:auto pool.

* completed / canceled issue -> claim row still released, issue NOT moved.
* started issue (genuinely stuck work) -> still moved back to unstarted.

Fully offline: the HTTP/Supabase/Linear layers are mocked.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
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


def _reap_one(mesh_client, state_type):
    client, mesh = mesh_client
    fake = FakeSupabase(
        claims={"UNI-A": {"machine": "nodeA", "state": "working",
                          "claimed_at": datetime.now(timezone.utc) - timedelta(minutes=100)}},
        fleet_stale={"nodeA": True},
    )
    fl = FakeLinear(team_of={"UNI-A": "team-1"}, state_type_of={"UNI-A": state_type})
    mesh._sb = fake.sb
    mesh._linear_graphql = fl.graphql
    r = client.post("/api/mesh/claims/reap", headers=HDR).json()
    return r, fake, fl


@pytest.mark.parametrize("state_type", ["completed", "canceled"])
def test_reap_leaves_closed_issue_closed(mesh_client, state_type):
    """Done/Canceled issue: the dead claim row is still freed, but the issue
    is not dragged back to Todo."""
    r, fake, fl = _reap_one(mesh_client, state_type)
    assert r["reaped"] == [{"linear_id": "UNI-A", "machine": "nodeA"}]
    assert fake.claims["UNI-A"]["state"] == "released"
    assert fl.moved_to_unstarted == set()


def test_reap_still_reopens_open_issue(mesh_client):
    """Control: an issue still in progress when its runner died IS moved back
    to unstarted, so the guard has not disabled the reaper's Linear half."""
    r, fake, fl = _reap_one(mesh_client, "started")
    assert r["reaped"] == [{"linear_id": "UNI-A", "machine": "nodeA"}]
    assert fake.claims["UNI-A"]["state"] == "released"
    assert fl.moved_to_unstarted == {"UNI-A"}
