"""UNI-2762: a slow upstream on a mesh route must not stall unrelated requests.

Every mesh handler talks to Supabase / Linear through blocking `urllib` calls
(10-15 s timeouts). Declared `async def`, each one ran on the event loop and
froze the whole server while it waited: a 404 measured 10.58 s in production
and heartbeat clients timed out at 10 s. As plain `def` handlers FastAPI runs
them in its threadpool, so the loop stays free.

The control: park a mesh request inside a slow fake upstream, then time a
cheap async request on the SAME event loop. `with TestClient(app)` matters —
without it each request gets its own portal and loop, and the test would pass
against the broken code.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HDR = {"X-Pi-CEO-Secret": "test-secret"}
UPSTREAM_SLEEP_S = 1.5
CHEAP_BUDGET_S = 0.5


def _slow(entered: threading.Event, result):
    def call(*_a, **_k):
        entered.set()
        time.sleep(UPSTREAM_SLEEP_S)
        return result
    return call


@pytest.fixture
def mesh_modules(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    from app.server.routes import mesh, mesh_ship
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    return mesh, mesh_ship


def _arm_heartbeat(mesh, _ship, entered, monkeypatch):
    monkeypatch.setattr(mesh, "_sb", _slow(entered, (201, "")))
    return "/api/mesh/heartbeat", {"host": "nodeA"}


def _arm_claim_self(mesh, _ship, entered, monkeypatch):
    monkeypatch.setattr(mesh, "_reap_sweep_best_effort", lambda: None)
    monkeypatch.setattr(mesh, "_open_claim_ids", lambda: set())
    monkeypatch.setattr(mesh, "_linear_graphql", _slow(entered, {"issues": {"nodes": []}}))
    return "/api/mesh/claim/self", {"host": "nodeA"}


def _arm_ship(_mesh, ship, entered, monkeypatch):
    # mesh_ship holds its own reference to the mesh module; patch that one.
    monkeypatch.setattr(ship.mesh_routes, "_sb", _slow(entered, (201, "")))
    return "/api/mesh/ship", {"machine": "nodeA", "repo": "CleanExpo/Pi-Dev-Ops", "sha": "abc1234"}


@pytest.mark.parametrize("arm", [_arm_heartbeat, _arm_claim_self, _arm_ship],
                         ids=["heartbeat", "claim_self", "ship"])
def test_slow_upstream_does_not_block_the_event_loop(mesh_modules, monkeypatch, arm):
    mesh, mesh_ship = mesh_modules
    entered = threading.Event()
    path, payload = arm(mesh, mesh_ship, entered, monkeypatch)

    app = FastAPI()
    app.include_router(mesh.router)
    app.include_router(mesh_ship.router)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    slow: dict = {}
    with TestClient(app) as client:  # one portal, one event loop for both requests
        t = threading.Thread(target=lambda: slow.update(r=client.post(path, json=payload, headers=HDR)))
        t.start()
        assert entered.wait(5), "the mesh request never reached the fake upstream"
        t0 = time.monotonic()
        cheap = client.get("/ping")
        elapsed = time.monotonic() - t0
        t.join(10)

    assert cheap.status_code == 200
    assert slow["r"].status_code == 200, slow["r"].text
    assert elapsed < CHEAP_BUDGET_S, (
        f"/ping took {elapsed:.2f}s while {path} waited on its upstream — "
        "the handler is blocking the event loop")
