"""tests/test_mesh_ship_endpoint.py — POST /api/mesh/ship (RA-7377).

mesh_ships had a schema and a reader (GET /api/mesh/fleet) but no writer, so
the fleet ship feed could never show a new ship. This endpoint is the writer:
same X-Pi-CEO-Secret gate and service-role insert path as /api/mesh/heartbeat.

Fully offline: the Supabase layer is stubbed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HDR = {"X-Pi-CEO-Secret": "test-secret"}
VALID = {
    "machine": "unite-mac-mini",
    "repo": "CleanExpo/Pi-Dev-Ops",
    "branch": "mesh/unite-mac-mini/ra-7377-abc",
    "sha": "a526459",
    "subject": "feat(mesh): record the ship",
    "files_changed": 2,
}


@pytest.fixture
def ship_client(monkeypatch):
    """TestClient over the ship router, secret set, mesh._sb stubbed later."""
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    sys.modules.pop("app.server.routes.mesh_ship", None)
    from app.server.routes import mesh, mesh_ship
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh_ship.router)
    return TestClient(app), mesh, monkeypatch


def test_ship_requires_the_secret(ship_client):
    client, mesh, mp = ship_client
    mp.setattr(mesh, "_sb", lambda *a, **k: (200, ""))
    assert client.post("/api/mesh/ship", json=VALID).status_code == 401
    assert client.post(
        "/api/mesh/ship", json=VALID, headers={"X-Pi-CEO-Secret": "wrong"},
    ).status_code == 401


def test_ship_inserts_the_schema_columns(ship_client):
    client, mesh, mp = ship_client
    calls = []

    def _sb(method, path, body=None, *, prefer=""):
        calls.append((method, path, body, prefer))
        return 201, ""

    mp.setattr(mesh, "_sb", _sb)
    r = client.post("/api/mesh/ship", json=VALID, headers=HDR)
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "machine": "unite-mac-mini",
        "repo": "CleanExpo/Pi-Dev-Ops",
        "sha": "a526459",
    }
    assert len(calls) == 1
    method, path, body, prefer = calls[0]
    assert method == "POST" and path == "mesh_ships"
    assert prefer == "return=minimal"
    assert body["machine"] == "unite-mac-mini"
    assert body["repo"] == "CleanExpo/Pi-Dev-Ops"
    assert body["branch"] == VALID["branch"]
    assert body["sha"] == "a526459"
    assert body["subject"] == VALID["subject"]
    assert body["files_changed"] == 2
    assert "shipped_at" in body


def test_ship_rejects_missing_required_fields(ship_client):
    client, mesh, mp = ship_client
    mp.setattr(mesh, "_sb", lambda *a, **k: (200, ""))
    r = client.post("/api/mesh/ship", json={"machine": "host"}, headers=HDR)
    assert r.status_code == 422
    r = client.post("/api/mesh/ship", json={"repo": "owner/repo"}, headers=HDR)
    assert r.status_code == 422


def test_ship_rejects_a_non_hex_sha(ship_client):
    client, mesh, mp = ship_client
    mp.setattr(mesh, "_sb", lambda *a, **k: (201, ""))
    bad = dict(VALID, sha="not-a-sha")
    r = client.post("/api/mesh/ship", json=bad, headers=HDR)
    assert r.status_code == 422
    assert r.json()["detail"] == "sha must be a 7-40 character hex git object"


def test_ship_reports_a_failed_insert(ship_client):
    client, mesh, mp = ship_client
    mp.setattr(mesh, "_sb", lambda *a, **k: (401, '{"message":"permission denied"}'))
    r = client.post("/api/mesh/ship", json=VALID, headers=HDR)
    assert r.status_code == 502
    assert "ship insert failed" in r.json()["detail"]


def test_ship_defaults_files_changed_to_zero(ship_client):
    client, mesh, mp = ship_client
    calls = []
    mp.setattr(mesh, "_sb", lambda method, path, body=None, **k: calls.append(body) or (201, ""))
    payload = {"machine": "host", "repo": "owner/repo", "sha": "abc1234"}
    assert client.post("/api/mesh/ship", json=payload, headers=HDR).status_code == 200
    assert calls[0]["files_changed"] == 0
