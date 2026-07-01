"""API route tests for spec pipeline."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth
from app.server.routes import spec_pipeline


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(spec_pipeline.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app)


def test_spec_pipeline_list_empty(client: TestClient):
    r = client.get("/api/spec-pipeline")
    assert r.status_code == 200
    assert "pipelines" in r.json()


def test_spec_pipeline_run_queues(client: TestClient, monkeypatch):
    def fake_run_bg(pipeline_id: str, proposal: str, dry_run: bool) -> None:
        spec_pipeline._running[pipeline_id] = "mocked"

    monkeypatch.setattr(spec_pipeline, "_run_bg", fake_run_bg)
    r = client.post(
        "/api/spec-pipeline/run",
        json={"proposal": "Add dry-run spec pipeline panel to Mission Control", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pipeline_id"].startswith("spec-")
    assert body["status"] == "queued"
    assert body["dry_run"] is True


def test_spec_pipeline_run_rejects_short_proposal(client: TestClient):
    r = client.post(
        "/api/spec-pipeline/run",
        json={"proposal": "str", "dry_run": True},
    )
    assert r.status_code == 422


def test_spec_pipeline_get_invalid_id(client: TestClient):
    r = client.get("/api/spec-pipeline/not-valid")
    assert r.status_code == 400
