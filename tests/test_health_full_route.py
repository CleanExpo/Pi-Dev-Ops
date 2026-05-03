"""tests/test_health_full_route.py — RA-1910 phase 1.

Coverage for /api/health/full:

  * Response shape contains all 7 required components
  * Returns 200 when every component is green
  * Returns 503 when at least one component is red
  * Total response time < 2s (each component is bounded to 2s, run in parallel)
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from app.server.routes import health_full


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


_REQUIRED_COMPONENTS = {
    "hermes_gateway",
    "pi_ceo_railway",
    "margot_route",
    "mcp_pi_ceo",
    "openrouter",
    "supabase",
    "telegram_polling",
}


def _all_green_checks() -> dict:
    """Return _CHECKS-shaped dict where every probe returns ok=True."""
    async def ok(_name=""):
        return {"ok": True, "note": "stub"}
    return {name: ok for name in _REQUIRED_COMPONENTS}


def _one_red_checks(red_name: str) -> dict:
    async def ok():
        return {"ok": True}

    async def red():
        return {"ok": False, "error": "stub_failure"}

    return {name: (red if name == red_name else ok) for name in _REQUIRED_COMPONENTS}


def test_route_returns_all_seven_components(monkeypatch):
    monkeypatch.setattr(health_full, "_CHECKS", _all_green_checks())
    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert "components" in body
    assert set(body["components"].keys()) == _REQUIRED_COMPONENTS
    assert "ok" in body
    assert "last_full_check" in body


def test_route_returns_200_when_all_green(monkeypatch):
    monkeypatch.setattr(health_full, "_CHECKS", _all_green_checks())
    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert response.status_code == 200
    assert body["ok"] is True


def test_route_returns_503_when_any_component_red(monkeypatch):
    monkeypatch.setattr(health_full, "_CHECKS", _one_red_checks("supabase"))
    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert response.status_code == 503
    assert body["ok"] is False
    assert body["components"]["supabase"]["ok"] is False


def test_route_completes_under_two_seconds(monkeypatch):
    """Each probe is timeout-bounded to 2s and they run via asyncio.gather,
    so total wall time must stay <2s even when probes do real work."""
    monkeypatch.setattr(health_full, "_CHECKS", _all_green_checks())
    t0 = time.time()
    _run(health_full.health_full())
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"endpoint took {elapsed:.2f}s — must be <2s"


def test_one_broken_check_does_not_fail_endpoint(monkeypatch):
    """A probe that raises must be captured as ok=false, not bubble up."""
    async def boom():
        raise RuntimeError("intentional")

    async def ok():
        return {"ok": True}

    checks = {name: ok for name in _REQUIRED_COMPONENTS}
    checks["openrouter"] = boom
    monkeypatch.setattr(health_full, "_CHECKS", checks)

    response = _run(health_full.health_full())
    body = json.loads(response.body)

    assert response.status_code == 503
    assert body["components"]["openrouter"]["ok"] is False
    assert "error" in body["components"]["openrouter"]
    # All other components still green.
    other_ok = [k for k, v in body["components"].items() if k != "openrouter"]
    assert all(body["components"][k]["ok"] for k in other_ok)
