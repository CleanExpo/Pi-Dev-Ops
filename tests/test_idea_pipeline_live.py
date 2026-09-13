"""UNI-2633 — Mission Control daily window carries the Board packet."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth
from app.server.routes import mission_control


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    snap = {
        "intake": "IDEAS.md",
        "awaiting": 1,
        "packet": {"idea_id": "idea-live", "text": "Teach owners a short lesson.", "executed": False},
        "go_required": True,
        "executed": False,
    }
    monkeypatch.setattr(mission_control, "_idea_pipeline_snapshot", lambda _root: snap)
    monkeypatch.setattr(mission_control, "_hourly_throughput_24h", lambda: [0] * 24)
    monkeypatch.setattr(mission_control, "_active_sessions", lambda: [])
    monkeypatch.setattr(mission_control, "_recent_completions", lambda: [])
    monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: {
        "urgent": 0, "high": 0, "next_issue_id": None, "next_issue_title": "",
    })
    monkeypatch.setattr(mission_control, "_pulse_status", lambda: {
        "last_at": None, "comments_today": 0, "pulse_issue_id": None,
    })
    monkeypatch.setattr(mission_control, "_claude_session_hud", lambda: {})
    monkeypatch.setattr(
        mission_control,
        "_observability_snapshot",
        AsyncMock(return_value={"ok": True, "actions": []}),
    )
    app = FastAPI()
    app.include_router(mission_control.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app)


def test_live_payload_includes_idea_pipeline(client: TestClient) -> None:
    r = client.get("/api/mission-control/live")
    assert r.status_code == 200
    body = r.json()
    assert "idea_pipeline" in body
    assert body["idea_pipeline"]["intake"] == "IDEAS.md"
    assert body["idea_pipeline"]["go_required"] is True
    assert body["idea_pipeline"]["executed"] is False
    assert body["idea_pipeline"]["packet"]["idea_id"] == "idea-live"
