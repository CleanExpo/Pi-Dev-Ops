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
from tests.test_telegram_linear_create_contract import _ROUTED, FakeLinear


@pytest.fixture
def client_and_calls(monkeypatch):
    # RA-8632: the route now looks up, labels and then creates, so the fake must be a
    # small Linear that answers every query; `fake.calls` records them all.
    fake = FakeLinear()
    fake.labels["team-default"] = [{"id": "label-src", "name": "pi-dev:source"}]
    monkeypatch.setattr(telegram_proxy, "_linear_graphql", fake)
    monkeypatch.setattr(telegram_proxy, "_project_routing", lambda project_id: dict(_ROUTED))
    app = FastAPI()
    app.include_router(telegram_proxy.router)
    app.dependency_overrides[require_auth] = lambda: None
    return TestClient(app), fake


@pytest.mark.parametrize("title", ["", "   ", "\n\t"])
def test_blank_title_is_rejected_before_linear(client_and_calls, title: str) -> None:
    client, fake = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": title})
    assert resp.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("priority", [-1, 5, 99])
def test_out_of_range_priority_is_rejected_before_linear(client_and_calls, priority: int) -> None:
    client, fake = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": "Real title", "priority": priority})
    assert resp.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("priority", [0, 1, 2, 3, 4])
def test_valid_priority_reaches_linear(client_and_calls, priority: int) -> None:
    client, fake = client_and_calls
    resp = client.post("/api/telegram/linear/create", json={"title": "  Real title  ", "priority": priority})
    assert resp.status_code == 200
    creates = fake.ops("issueCreate(")
    assert len(creates) == 1
    assert creates[0]["input"]["priority"] == priority
    assert creates[0]["input"]["title"] == "Real title"


def test_linear_calls_run_off_the_event_loop(client_and_calls, monkeypatch) -> None:
    """Every Linear call is a blocking urlopen. They must run in a worker thread,
    never on the event loop, or one slow Linear reply stalls every other request."""
    import asyncio

    client, fake = client_and_calls
    on_loop: list[bool] = []

    def recording(query, variables=None):
        try:
            asyncio.get_running_loop()
            on_loop.append(True)
        except RuntimeError:
            on_loop.append(False)
        return fake(query, variables)

    monkeypatch.setattr(telegram_proxy, "_linear_graphql", recording)
    resp = client.post("/api/telegram/linear/create", json={"title": "Off loop"})
    assert resp.status_code == 200
    assert on_loop and not any(on_loop)
