"""RA-8639: /api/telegram/linear/create rejects bad input before Linear is called.

The release review found an empty title and an out-of-range priority both
reaching issueCreate. The root cause is that the request model accepted any
string and any integer, so every check had to be remembered later in the
handler. The bounds now live on the model, and these tests prove a bad body
never reaches the Linear call.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.auth import require_auth
from app.server.routes import telegram_proxy


@pytest.fixture
def client_and_calls(monkeypatch):
    calls: list[dict] = []

    def fake_graphql(query: str, variables: dict | None = None) -> dict:
        calls.append(variables or {})
        return {"issueCreate": {"success": True, "issue": {"id": "x", "identifier": "RA-1", "url": "u", "title": "t"}}}

    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake_graphql)
    app = FastAPI()
    app.include_router(telegram_proxy.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app), calls


@pytest.mark.parametrize("title", ["", "   ", "\n\t"])
def test_blank_title_is_rejected_before_linear(client_and_calls, title: str) -> None:
    client, calls = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": title})
    assert resp.status_code == 422
    assert calls == []


@pytest.mark.parametrize("priority", [-1, 5, 99])
def test_out_of_range_priority_is_rejected_before_linear(client_and_calls, priority: int) -> None:
    client, calls = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": "Real title", "priority": priority})
    assert resp.status_code == 422
    assert calls == []


@pytest.mark.parametrize("priority", [0, 1, 2, 3, 4])
def test_valid_priority_reaches_linear(client_and_calls, priority: int) -> None:
    client, calls = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": "  Real title  ", "priority": priority})
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["input"]["priority"] == priority
    assert calls[0]["input"]["title"] == "Real title"
