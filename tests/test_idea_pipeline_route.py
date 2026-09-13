"""UNI-2633 — idea pipeline HTTP path: intake → packet → dispose → GO."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth
from app.server.routes import idea_pipeline


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(idea_pipeline, "_repo_root", lambda: tmp_path)
    app = FastAPI()
    app.include_router(idea_pipeline.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app)


def _drop_test_idea(client: TestClient) -> str:
    created = client.post(
        "/api/idea-pipeline/intake",
        json={
            "text": "Teach shop owners to grow with short self-paced video lessons.",
            "source": "phill",
        },
    )
    assert created.status_code == 200
    packet = created.json()["packet"]
    assert packet["executed"] is False
    return str(packet["idea_id"])


def test_intake_produces_a_board_packet(client: TestClient) -> None:
    empty = client.get("/api/idea-pipeline")
    assert empty.status_code == 200
    assert empty.json()["snapshot"]["awaiting"] == 0
    idea_id = _drop_test_idea(client)
    listed = client.get("/api/idea-pipeline")
    packet = listed.json()["snapshot"]["packet"]
    assert packet["idea_id"] == idea_id
    assert packet["judge"]["score"] >= 1
    assert packet["spm"]["desired_outcome"]


def test_execute_is_blocked_until_promote_and_go(client: TestClient) -> None:
    idea_id = _drop_test_idea(client)
    refused = client.post("/api/idea-pipeline/execute", json={"idea_id": idea_id})
    assert refused.status_code == 409
    assert "without GO" in refused.json()["detail"]
    disposed = client.post(
        "/api/idea-pipeline/dispose",
        json={"idea_id": idea_id, "verdict": "PROMOTE"},
    )
    assert disposed.json()["executed"] is False
    still = client.post("/api/idea-pipeline/execute", json={"idea_id": idea_id})
    assert still.status_code == 409
    go = client.post("/api/idea-pipeline/go", json={"idea_id": idea_id})
    assert go.json()["packet"]["go_at"]
    execute = client.post("/api/idea-pipeline/execute", json={"idea_id": idea_id})
    assert execute.status_code == 200
    assert execute.json()["executed"] is False
    assert execute.json()["authorized"] is True


def test_margot_intake_and_bad_verdict(client: TestClient) -> None:
    created = client.post(
        "/api/idea-pipeline/intake",
        json={"text": "A cafe owner practises one sales conversation each week.", "source": "margot"},
    )
    assert created.status_code == 200
    assert created.json()["packet"]["source"] == "margot"
    idea_id = created.json()["packet"]["idea_id"]
    bad = client.post(
        "/api/idea-pipeline/dispose",
        json={"idea_id": idea_id, "verdict": "SHIP"},
    )
    assert bad.status_code == 409


def test_short_intake_rejected(client: TestClient) -> None:
    r = client.post("/api/idea-pipeline/intake", json={"text": "short", "source": "phill"})
    assert r.status_code == 422
