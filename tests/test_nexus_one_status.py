"""RA-7539 — read-only Nexus One synthetic status is fail-closed.

Unregistered must report registered=false and must never look healthy.
No live worker, no SHIPPED claim, no Anthropic/API spend.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.server.nexus_one import LINEAGE, select_worker
from app.server.nexus_one.status import (
    HEALTHY_KEYS,
    STATUS_PATH,
    collect_route_paths,
    healthy_bits_on,
    live_router_registered,
    status_payload_for_app,
    synthetic_status,
)
from app.server.routes import nexus_one_status as status_route
from app.server.routes import mission_control


def _assert_fail_closed(payload: dict) -> None:
    assert payload["lineage"] == LINEAGE
    assert payload["lineage"] == "SYNTHETIC"
    assert payload["excluded_from_real_acceptance"] is True
    assert payload["registered"] is False
    assert payload["windows_policy"] == "review_only"
    assert payload["max_subscription_only"] is True
    assert payload["worker_enrolled"] is False
    assert healthy_bits_on(payload) == ()
    for key in HEALTHY_KEYS:
        assert payload.get(key) is not True, f"{key} must not be true when unregistered"


def test_empty_app_is_unregistered():
    payload = synthetic_status(registered=live_router_registered(()))
    _assert_fail_closed(payload)


def test_status_path_alone_is_not_live_registration():
    assert live_router_registered((STATUS_PATH,)) is False
    payload = synthetic_status(registered=False)
    _assert_fail_closed(payload)


def test_live_path_sets_registered_but_never_ready():
    """Positive control: the inspector can return true; it still must not green."""
    assert live_router_registered(("/api/nexus-one/dispatch",)) is True
    payload = synthetic_status(registered=True)
    assert payload["registered"] is True
    assert payload["ready"] is False
    assert payload["shipped"] is False
    assert payload["worker_enrolled"] is False
    assert healthy_bits_on(payload) == ()


def test_isolated_status_router_reports_unregistered():
    app = FastAPI()
    app.include_router(status_route.router)
    assert STATUS_PATH in collect_route_paths(app)
    payload = status_payload_for_app(app)
    _assert_fail_closed(payload)
    paths_ok = live_router_registered(
        p for p in (
            "/api/nexus-one/status",
            "/api/nexus-one/status/",
        )
    )
    assert paths_ok is False


def test_dummy_live_router_is_detected():
    app = FastAPI()
    app.include_router(status_route.router)
    live = APIRouter(prefix="/api/nexus-one", tags=["nexus-one-live"])

    @live.post("/dispatch")
    def _dispatch() -> dict:
        return {"ok": False}

    app.include_router(live)
    payload = status_payload_for_app(app)
    assert payload["registered"] is True
    assert payload["ready"] is False
    assert payload["shipped"] is False
    assert healthy_bits_on(payload) == ()


def _authed_client(app: FastAPI) -> TestClient:
    from app.server.auth import create_session_token

    client = TestClient(app, raise_server_exceptions=False)
    token = create_session_token()
    client.cookies.set("tao_session", token)
    return client


def test_status_route_401_without_auth():
    app = FastAPI()
    app.include_router(status_route.router)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/nexus-one/status").status_code == 401


def test_status_route_returns_unregistered_contract():
    app = FastAPI()
    app.include_router(status_route.router)
    resp = _authed_client(app).get("/api/nexus-one/status")
    assert resp.status_code == 200
    _assert_fail_closed(resp.json())


def test_production_app_status_is_unregistered():
    """Ask the assembled app — FastAPI no longer flattens included routers."""
    from app.server.main import app

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/nexus-one/status").status_code == 401
    assert client.get("/api/__definitely_absent__").status_code == 404
    resp = _authed_client(app).get("/api/nexus-one/status")
    assert resp.status_code == 200
    _assert_fail_closed(resp.json())
    payload = status_payload_for_app(app)
    _assert_fail_closed(payload)


def test_mission_control_live_includes_fail_closed_nexus_one(monkeypatch):
    monkeypatch.setattr(mission_control, "_hourly_throughput_24h", lambda: [0] * 24)
    monkeypatch.setattr(mission_control, "_active_sessions", lambda: [])
    monkeypatch.setattr(mission_control, "_recent_completions", lambda: [])
    monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: {})
    monkeypatch.setattr(mission_control, "_pulse_status", lambda: {})
    monkeypatch.setattr(mission_control, "_claude_session_hud", lambda: {})

    async def _obs() -> dict:
        return {"source": "test", "ok": False}

    monkeypatch.setattr(mission_control, "_observability_snapshot", _obs)
    data = asyncio.run(mission_control.mission_control_live())
    _assert_fail_closed(data["nexus_one"])


def test_windows_review_only_policy_is_unchanged():
    decision = select_worker(platform="win32")
    assert decision.eligible is False
    assert decision.reason == "windows_review_only"
    assert decision.cost_usd == 0.0


def test_paid_api_lane_still_refused():
    decision = select_worker(platform="linux", requested_lane="anthropic_api")
    assert decision.eligible is False
    assert decision.reason == "api_billing_forbidden"
    assert decision.cost_usd == 0.0
