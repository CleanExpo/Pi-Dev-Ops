"""tests/test_routing_route.py — RA-7434 read-only GET /api/routing.

Mission Control needs role → provider → model → source → cost today. Cost comes
from Supabase ``llm_costs``; when that read cannot happen the field is ``null``
with a ``reason`` — never a fake 0.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

HEADERS = {"X-Pi-CEO-Secret": "test-secret"}


@pytest.fixture
def client(monkeypatch):
    for k in list(os.environ):
        if k.startswith(("TAO_MODEL_", "TAO_CHEAP_", "TAO_TOP_", "TAO_MID_")) or k == "OLLAMA_BASE_URL":
            monkeypatch.delenv(k, raising=False)
    from app.server import config as _config  # noqa: PLC0415
    monkeypatch.setattr(_config, "WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    from app.server import provider_ollama, provider_router  # noqa: PLC0415
    monkeypatch.setattr(provider_ollama, "is_reachable", lambda **kw: False)
    monkeypatch.setattr(provider_router, "_record_tier_downgrade", lambda *a, **kw: None)
    from app.server import supabase_log  # noqa: PLC0415
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("", ""))
    from app.server.routes import routing  # noqa: PLC0415
    app = FastAPI()
    app.include_router(routing.router)
    return TestClient(app)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def test_routing_401_without_secret(client):
    assert client.get("/api/routing").status_code == 401


def test_routing_401_with_wrong_secret(client):
    assert client.get("/api/routing", headers={"X-Pi-CEO-Secret": "nope"}).status_code == 401


def test_routing_lists_every_role_with_provider_model_source(client):
    from app.server import provider_router as PR  # noqa: PLC0415
    resp = client.get("/api/routing", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["day_iso"] == _today()
    assert set(data["roles"]) == set(PR.ROLE_TIER)
    margot = data["roles"]["margot.casual"]
    assert margot["provider"] == "openrouter"
    assert margot["model"] == "google/gemma-4-26b-a4b-it:free"
    assert margot["source"] == "ladder-step-2"
    assert margot["error"] is None
    planner = data["roles"]["planner"]
    assert planner["provider"] == "anthropic"
    assert planner["source"] == "code-default"
    assert data["margot_casual"]["ladder"] == [
        "ollama:gemma4:latest",
        "openrouter:google/gemma-4-26b-a4b-it:free",
        "openrouter:z-ai/glm-4.7-flash",
    ]


def test_routing_source_names_the_env_var_that_decided(client, monkeypatch):
    monkeypatch.setenv("TAO_TOP_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("TAO_CHEAP_PROVIDER", "openrouter")
    monkeypatch.setenv("TAO_CHEAP_REMOTE_MODEL", "~moonshotai/kimi-latest")
    monkeypatch.setenv("TAO_MODEL_MONITOR", "ollama:qwen3.5:latest")
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", "openrouter:nvidia/nemotron-3-super-120b-a12b:free")
    roles = client.get("/api/routing", headers=HEADERS).json()["roles"]
    assert roles["planner"]["source"] == "env:TAO_TOP_MODEL"
    assert roles["intent_classify"]["model"] == "~moonshotai/kimi-latest"
    assert roles["intent_classify"]["source"] == "env:TAO_CHEAP_REMOTE_MODEL"
    assert roles["monitor"]["source"] == "env:TAO_MODEL_MONITOR"
    assert roles["margot.casual"]["source"] == "env:TAO_MODEL_MARGOT_CASUAL"
    assert roles["margot.casual"]["model"] == "nvidia/nemotron-3-super-120b-a12b:free"


def test_routing_shows_a_refused_margot_override_instead_of_500(client, monkeypatch):
    monkeypatch.setenv("TAO_MODEL_MARGOT_CASUAL", "openrouter:~anthropic/claude-sonnet-latest")
    resp = client.get("/api/routing", headers=HEADERS)
    assert resp.status_code == 200
    margot = resp.json()["roles"]["margot.casual"]
    assert margot["provider"] is None and margot["model"] is None
    assert margot["source"] == "env:TAO_MODEL_MARGOT_CASUAL"
    assert "RA-7434" in margot["error"]


def test_routing_cost_is_null_with_reason_when_supabase_not_configured(client):
    data = client.get("/api/routing", headers=HEADERS).json()
    assert data["cost_source"] is None
    assert "not configured" in data["cost_reason"]
    for row in data["roles"].values():
        assert row["cost_today_usd"] is None
        assert "not configured" in row["cost_reason"]


def test_routing_cost_is_null_with_reason_when_the_read_fails(client, monkeypatch):
    from app.server import supabase_log  # noqa: PLC0415
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(supabase_log, "_request", lambda *a, **kw: (503, None))
    data = client.get("/api/routing", headers=HEADERS).json()
    assert data["cost_source"] is None
    assert "HTTP 503" in data["cost_reason"]
    assert data["roles"]["margot.casual"]["cost_today_usd"] is None


def test_routing_cost_today_per_role_from_llm_costs(client, monkeypatch):
    from app.server import supabase_log  # noqa: PLC0415
    seen: list[tuple] = []

    def fake_request(method, path, body=None, prefer="return=minimal"):
        seen.append((method, path, prefer))
        return 200, [
            {"role": "margot.casual", "cost_usd": 0.0},
            {"role": "margot.casual", "cost_usd": "0.0125"},
            {"role": "planner", "cost_usd": 1.5},
            {"role": None, "cost_usd": 0.4},
        ]

    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(supabase_log, "_request", fake_request)
    data = client.get("/api/routing?tenant_id=pi-ceo", headers=HEADERS).json()
    assert data["cost_source"] == "supabase:llm_costs"
    assert data["cost_reason"] is None
    assert data["roles"]["margot.casual"]["cost_today_usd"] == 0.0125
    assert data["roles"]["planner"]["cost_today_usd"] == 1.5
    assert data["roles"]["monitor"]["cost_today_usd"] == 0.0
    method, path, prefer = seen[0]
    assert method == "GET" and path.startswith("llm_costs?")
    assert f"ts=gte.{_today()}T00:00:00Z" in path
    assert "tenant_id=eq.pi-ceo" in path


def test_routing_cost_is_null_when_the_page_cap_hides_rows(client, monkeypatch):
    from app.server import supabase_log  # noqa: PLC0415
    monkeypatch.setattr(supabase_log, "_cfg", lambda: ("https://x.supabase.co", "key"))
    monkeypatch.setattr(
        supabase_log, "_request",
        lambda *a, **kw: (200, [{"role": "planner", "cost_usd": 0.01}] * 1000),
    )
    data = client.get("/api/routing", headers=HEADERS).json()
    assert data["cost_source"] is None
    assert "cap" in data["cost_reason"]
    assert data["roles"]["planner"]["cost_today_usd"] is None


def test_routing_is_registered_on_the_production_app():
    from app.server.main import app  # noqa: PLC0415
    assert "/api/routing" in {getattr(r, "path", "") for r in app.routes}
