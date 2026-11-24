"""GET /api/mesh/claim/brief — the brief of a ticket, only for the node holding its claim.

The server reads Linear with its own key, so the node that runs the work stays
credential-free (mesh/prompt.py). The fleet-state comment that recorded the gap warned
that enriching claims server-side would hand ticket text to any node holding the mesh
secret. That is why the brief is released only against an OPEN claim row naming this
ticket, this host and this claim id, and why Linear is not even asked otherwise.
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
ISSUE = {"id": "uuid-7", "identifier": "UNI-7", "title": "Fix the header",
         "description": "Make it sticky.", "priority": 1, "team": {"id": "team-1"},
         "state": {"name": "In Progress", "type": "started"}, "labels": {"nodes": [{"name": "mesh:auto"}]}}
OPEN_CLAIM = {"id": "claim-1", "linear_id": "UNI-7", "machine": "nodeA", "state": "claimed"}
QUERY = "/api/mesh/claim/brief?linear_id=UNI-7&host=nodeA&claim_id=claim-1"


class Sb:
    """Answers the claim-row read; records every path it was asked for."""

    def __init__(self, rows, status=200):
        self.rows, self.status, self.paths = rows, status, []

    def __call__(self, method, path, payload=None, prefer=""):
        self.paths.append(path)
        assert method == "GET", "the brief endpoint must never write"
        return self.status, json.dumps(self.rows)


@pytest.fixture
def env(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    for name in ("app.server.routes.mesh_brief", "app.server.routes.mesh"):
        sys.modules.pop(name, None)
    from app.server.routes import mesh, mesh_brief
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(mesh_brief.mesh_lanes, "registry_repos", lambda: {})
    linear: list[str] = []

    def graphql(q):
        linear.append(q)
        return {"issue": dict(ISSUE)} if q.startswith("query{issue") else {}

    monkeypatch.setattr(mesh, "_linear_graphql", graphql)
    monkeypatch.setattr(mesh, "_sb", Sb([OPEN_CLAIM]))
    app = FastAPI()
    app.include_router(mesh_brief.router)
    return TestClient(app), mesh, mesh_brief, linear


def test_holder_of_the_open_claim_gets_the_brief(env):
    client, *_ = env
    r = client.get(QUERY, headers=HDR)
    assert r.status_code == 200, r.text
    assert r.json() == {"linear_id": "UNI-7", "title": "Fix the header",
                        "description": "Make it sticky.", "lane": "build", "repo": None}


def test_claim_read_is_narrowed_to_ticket_host_claim_and_open_states(env):
    client, mesh, *_ = env
    client.get(QUERY, headers=HDR)
    [path] = mesh._sb.paths
    for part in ("linear_id=eq.UNI-7", "machine=eq.nodeA", "id=eq.claim-1",
                 "state=in.(claimed,working)"):
        assert part in path, f"{part} missing from {path}"


def test_no_open_claim_is_refused_without_asking_linear(env, monkeypatch):
    client, mesh, _, linear = env
    monkeypatch.setattr(mesh, "_sb", Sb([]))
    r = client.get(QUERY, headers=HDR)
    assert r.status_code == 409
    assert linear == [], "ticket text must not be read for a node that holds no claim"


def test_unreadable_claim_table_is_unavailable_not_refused(env, monkeypatch):
    client, mesh, _, linear = env
    monkeypatch.setattr(mesh, "_sb", Sb({"message": "JWT expired"}, status=401))
    r = client.get(QUERY, headers=HDR)
    assert r.status_code == 503
    assert linear == []


def test_ticket_linear_cannot_return_is_unavailable(env, monkeypatch):
    client, mesh, *_ = env
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {})
    r = client.get(QUERY, headers=HDR)
    assert r.status_code == 503
    assert "Linear" in r.json()["detail"]


def test_wrong_secret_is_rejected(env):
    client, *_ = env
    assert client.get(QUERY, headers={"X-Pi-CEO-Secret": "nope"}).status_code == 401


def test_every_parameter_is_required(env):
    client, *_ = env
    for missing in ("linear_id=UNI-7&host=nodeA", "linear_id=UNI-7&claim_id=claim-1",
                    "host=nodeA&claim_id=claim-1"):
        assert client.get(f"/api/mesh/claim/brief?{missing}", headers=HDR).status_code == 422


def test_both_fields_are_capped(env, monkeypatch):
    client, mesh, mesh_brief, _ = env
    long = {**ISSUE, "title": "T" * 10_000, "description": "D" * 100_000}
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": long})
    body = client.get(QUERY, headers=HDR).json()
    assert len(body["title"]) == mesh._TITLE_MAX_CHARS
    assert len(body["description"]) == mesh._BRIEF_MAX_CHARS


def test_plan_ticket_reports_the_plan_lane(env, monkeypatch):
    client, mesh, *_ = env
    plan = {**ISSUE, "labels": {"nodes": [{"name": "idea:plan"}]}}
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": plan})
    assert client.get(QUERY, headers=HDR).json()["lane"] == "plan"


def test_project_ticket_carries_its_registered_repo(env, monkeypatch):
    client, mesh, mesh_brief, _ = env
    proj = {**ISSUE, "project": {"id": "proj-1"}}
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": proj})
    monkeypatch.setattr(mesh_brief.mesh_lanes, "registry_repos", lambda: {"proj-1": "CleanExpo/X"})
    assert client.get(QUERY, headers=HDR).json()["repo"] == "CleanExpo/X"


def test_project_ticket_without_a_registered_repo_is_refused(env, monkeypatch):
    """Never let it fall back to the runner's default repository."""
    client, mesh, *_ = env
    proj = {**ISSUE, "project": {"id": "proj-unregistered"}}
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": proj})
    assert client.get(QUERY, headers=HDR).status_code == 409


def test_refusal_codes_are_stored_on_the_claim_row():
    from app.server import mesh_run_record
    for code in ("brief_unreadable", "brief_refused", "brief_empty"):
        fields = mesh_run_record.RunRecordFields(error_code=code)
        assert mesh_run_record.record_patch(fields).get("error_code") == code


@pytest.mark.parametrize("change", [
    {"state": {"name": "Done", "type": "completed"}},
    {"state": {"name": "Canceled", "type": "canceled"}},
    {"labels": {"nodes": [{"name": "bug"}]}},
    {"labels": {"nodes": [{"name": "mesh:auto"}, {"name": "pi-dev:blocked-reason:human"}]}},
    {"inverseRelations": {"pageInfo": {"hasNextPage": False},
                          "nodes": [{"type": "blocks", "issue": {"identifier": "UNI-1", "state": {"type": "started"}}}]}},
])
def test_ticket_no_longer_runnable_is_refused(env, monkeypatch, change):
    """Closed, relabelled or newly blocked after dispatch: its brief must not start an agent."""
    client, mesh, *_ = env
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": {**ISSUE, **change}})
    assert client.get(QUERY, headers=HDR).status_code == 409


def test_unreadable_project_registry_is_unavailable(env, monkeypatch):
    client, mesh, mesh_brief, _ = env
    monkeypatch.setattr(mesh, "_linear_graphql", lambda q: {"issue": {**ISSUE, "project": {"id": "p"}}})

    def missing():
        raise FileNotFoundError("projects.json")

    monkeypatch.setattr(mesh_brief.mesh_lanes, "registry_repos", missing)
    assert client.get(QUERY, headers=HDR).status_code == 503
