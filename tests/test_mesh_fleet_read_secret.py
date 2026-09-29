"""RA-7846 — the dashboard reads the fleet with a read-only key, not the shared secret.

The Vercel dashboard drew "NO LIVE SOURCE YET" because it held no secret for
`GET /api/mesh/fleet`. Giving it the shared secret would also hand it the
power to write heartbeats and claim work, so a second credential is accepted by
the fleet snapshot ONLY. These tests pin both halves: it opens the read, and it
opens nothing else.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SHARED = "shared-secret"
READ_ONLY = "read-only-secret"
ROWS = {"mesh_fleet": json.dumps([{"host": "m1", "status": "online", "is_stale": False}])}


@pytest.fixture
def mesh_client(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", SHARED, raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh

    def sb(method, path, body=None, *, prefer=""):
        for table, payload in ROWS.items():
            if path.startswith(table):
                return 200, payload
        return 200, "[]"

    monkeypatch.setattr(mesh, "_sb", sb)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh, monkeypatch


def _get(client: TestClient, secret: str | None):
    return client.get("/api/mesh/fleet", headers={"X-Pi-CEO-Secret": secret} if secret else {})


def test_read_only_key_opens_the_fleet_snapshot(mesh_client):
    client, _mesh, mp = mesh_client
    mp.setenv("TAO_FLEET_READ_SECRET", READ_ONLY)
    assert _get(client, READ_ONLY).status_code == 200


def test_the_shared_secret_still_opens_it(mesh_client):
    client, _mesh, mp = mesh_client
    mp.setenv("TAO_FLEET_READ_SECRET", READ_ONLY)
    assert _get(client, SHARED).status_code == 200


def test_a_wrong_or_missing_key_is_refused(mesh_client):
    client, _mesh, mp = mesh_client
    mp.setenv("TAO_FLEET_READ_SECRET", READ_ONLY)
    assert _get(client, "nope").status_code == 401
    assert _get(client, None).status_code == 401


def test_read_only_key_is_refused_when_it_is_not_configured(mesh_client):
    client, _mesh, mp = mesh_client
    mp.delenv("TAO_FLEET_READ_SECRET", raising=False)
    assert _get(client, READ_ONLY).status_code == 401


def test_an_empty_read_only_setting_does_not_accept_an_empty_header(mesh_client):
    client, _mesh, mp = mesh_client
    mp.setenv("TAO_FLEET_READ_SECRET", "  ")
    assert _get(client, "").status_code == 401


def test_read_only_key_cannot_pass_the_write_gate(mesh_client):
    """Heartbeats, claims and ship writes use `_check_secret`; the new key must fail it."""
    _client, mesh, mp = mesh_client
    mp.setenv("TAO_FLEET_READ_SECRET", READ_ONLY)
    with pytest.raises(HTTPException) as err:
        mesh._check_secret(READ_ONLY)
    assert err.value.status_code == 401
    mesh._check_secret(SHARED)


def test_no_secret_configured_anywhere_is_a_503(mesh_client):
    client, _mesh, mp = mesh_client
    from app.server import config as _config
    mp.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "", raising=False)
    mp.delenv("TAO_FLEET_READ_SECRET", raising=False)
    assert _get(client, SHARED).status_code == 503
