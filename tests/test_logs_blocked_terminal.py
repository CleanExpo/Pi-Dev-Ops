"""RA-7546 — planner ``blocked`` must close both SSE log routes."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app():
    from app.server.auth import require_auth, require_rate_limit
    from app.server.routes.sessions import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_auth] = lambda: None
    app.dependency_overrides[require_rate_limit] = lambda: None
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app(), raise_server_exceptions=True)


def _session(status: str) -> MagicMock:
    s = MagicMock()
    s.id = "sess1"
    s.status = status
    s.output_lines = [{"type": "error", "text": "Plan blocked"}]
    return s


@pytest.mark.parametrize("status", ["blocked", "stalled"])
@pytest.mark.parametrize("path", [
    "/api/sessions/sess1/logs",
    "/api/sessions/sess1/logs/stream",
])
def test_blocked_or_stalled_closes_log_stream(client, status, path):
    with patch("app.server.routes.sessions.get_session", return_value=_session(status)):
        response = client.get(path)
    assert response.status_code == 200
    assert "done" in response.text
