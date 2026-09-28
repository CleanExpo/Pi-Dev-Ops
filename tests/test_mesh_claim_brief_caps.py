"""Both brief fields leaving /api/mesh/claim/self are length-capped.

Raised as a P1 by the independent reviewer on the first pass of the brief-with-claim
change: the cap was applied to `description` only, and the comment justifying it said
"Linear descriptions are unbounded". A Linear *title* is unbounded in exactly the same
way, so the cap's own rationale was bypassed by putting the payload in the title.

The text is untrusted — anyone who can file an issue writes it — and it is forwarded to
an unattended agent, so an uncapped field is an uncapped prompt.

Its own file rather than an addition to test_mesh_runner_idle_autoclaim.py, which is
grandfathered over the 300-line ceiling; CLAUDE.md's ratchet says not to grow those.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HDR = {"X-Pi-CEO-Secret": "test-secret"}


class _Sb:
    """Minimum Supabase surface claim_self touches: the claim INSERT succeeds."""

    def __call__(self, method, path, payload=None, prefer=""):
        if method == "GET" and path.startswith("mesh_fleet"):
            return 200, json.dumps([{"host": "nodeA", "is_stale": False,
                                     "active_agents": 0, "load1": 0.1}])
        if method == "POST" and path.startswith("mesh_work_claims"):
            return 201, ""
        return 200, "[]"


@pytest.fixture
def mesh_client(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh


def _claim(client, mesh, *, title: str, description: str) -> dict:
    mesh._linear_graphql = lambda q: (
        {"team": {"states": {"nodes": [{"id": "st", "type": "started", "position": 1}]}}}
        if q.startswith("query{team") else
        {"issueUpdate": {"success": True}} if q.startswith("mutation") else
        {"issues": {"nodes": [{"id": "UNI-9", "identifier": "UNI-9", "title": title,
                               "description": description, "priority": 1,
                               "team": {"id": "team-1"}}]}}
    )
    mesh._sb = _Sb()
    mesh._open_claim_ids = lambda: set()
    r = client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR).json()
    assert r["claimed"] is not None, "fixture failed to produce a claim"
    return r["claimed"]


@pytest.mark.parametrize("field, cap_name", [("title", "_TITLE_MAX_CHARS"),
                                             ("description", "_BRIEF_MAX_CHARS")])
def test_each_brief_field_is_capped(mesh_client, field, cap_name):
    client, mesh = mesh_client
    cap = getattr(mesh, cap_name)
    oversize = "A" * (cap + 500)
    claimed = _claim(client, mesh, **{field: oversize,
                                      "title" if field == "description" else "description": "ok"})
    assert len(claimed[field]) == cap, f"{field} was not capped at {cap_name}"


def test_under_cap_text_is_passed_through_untouched(mesh_client):
    """The cap must not be truncation-by-default: a normal brief arrives whole, or
    the length assertion above would pass on a field that always returns nothing."""
    client, mesh = mesh_client
    claimed = _claim(client, mesh, title="Short title", description="Short body")
    assert claimed["title"] == "Short title"
    assert claimed["description"] == "Short body"


@pytest.mark.parametrize("cap_name", ["_TITLE_MAX_CHARS", "_BRIEF_MAX_CHARS"])
def test_the_route_and_the_prompt_agree_on_the_cap(mesh_client, cap_name):
    """`mesh/` is not an importable package, so the two caps are separate literals.

    That duplication is only safe while it cannot drift unnoticed. If someone raises
    the route's cap and not the prompt's, the prompt silently keeps the old bound;
    raise the prompt's and not the route's and the route's becomes the real limit.
    Either way the number a reader sees stops being the number that applies.
    """
    _, mesh = mesh_client
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mesh"))
    import prompt

    assert getattr(prompt, cap_name) == getattr(mesh, cap_name), (
        f"{cap_name} disagrees between mesh/prompt.py and app/server/routes/mesh.py"
    )
