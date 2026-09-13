"""tests/test_wiki_graph_route.py — GET /api/wiki-graph is registered and gated."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes import utils


def test_wiki_graph_401_without_session():
    app = FastAPI()
    app.include_router(utils.router)
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/wiki-graph").status_code == 401


def test_wiki_graph_empty_graph_with_session(monkeypatch):
    from app.server.auth import create_session_token  # noqa: PLC0415
    from app.server import unite_group_wiki as UG  # noqa: PLC0415

    monkeypatch.setattr(UG, "fetch_wiki_pages", lambda: (None, "not configured"))
    app = FastAPI()
    app.include_router(utils.router)
    client = TestClient(app, raise_server_exceptions=False)
    token = create_session_token()
    resp = client.get("/api/wiki-graph", cookies={"tao_session": token})
    assert resp.status_code == 200
    data = resp.json()
    assert data["pageCount"] == 0
    assert data["source"] == "unconfigured"


def test_wiki_graph_is_registered_on_the_production_app():
    """Ask the assembled app to route the path — FastAPI no longer flattens includes."""
    from app.server.main import app  # noqa: PLC0415

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/wiki-graph").status_code != 404
    assert client.get("/api/__definitely_absent__").status_code == 404
