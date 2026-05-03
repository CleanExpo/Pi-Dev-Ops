"""tests/test_cost_report_route.py — RA-1909 phase-1 route auth + shape."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Build a minimal FastAPI app mounting only the cost_report router."""
    monkeypatch.setenv("TAO_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("BUDGET_TRACKER_LOG_PATH", str(tmp_path / "llm-cost.jsonl"))
    # Force module reload so config picks up the env var
    for m in [
        "app.server.config",
        "app.server.routes.cost_report",
        "swarm.budget_tracker",
    ]:
        sys.modules.pop(m, None)
    from app.server.routes import cost_report  # noqa: PLC0415
    app = FastAPI()
    app.include_router(cost_report.router)
    return TestClient(app)


def test_cost_report_401_without_secret(client):
    resp = client.get("/api/cost-report?since=24h")
    assert resp.status_code == 401


def test_cost_report_401_with_wrong_secret(client):
    resp = client.get(
        "/api/cost-report?since=24h",
        headers={"X-Pi-CEO-Secret": "wrong"},
    )
    assert resp.status_code == 401


def test_cost_report_200_returns_expected_shape(client):
    resp = client.get(
        "/api/cost-report?since=24h",
        headers={"X-Pi-CEO-Secret": "test-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "by_provider" in data
    assert "by_role" in data
    assert "total_usd" in data
    assert "day_iso" in data
    assert isinstance(data["by_provider"], dict)
    assert isinstance(data["by_role"], dict)
    assert isinstance(data["total_usd"], (int, float))
    # Empty log → totals are zero
    assert data["total_usd"] == 0.0
