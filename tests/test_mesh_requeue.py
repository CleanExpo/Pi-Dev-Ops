"""A failed mesh claim goes back in the queue, says why, and skips the node that failed it (RA-7802).

On 28/09 RA-7794 and RA-7800 each failed and then sat In Progress, never
offered again, with nothing in Linear saying why, until a person went looking.
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
    """PATCH answers with `patch_rows`; GET of failed claims answers with `failed_rows`."""

    def __init__(self):
        self.patch_rows = [{"linear_id": "RA-1", "state": "failed", "machine": "Phill_Desktop"}]
        self.failed_rows: list[dict] = []
        self.claimed: list[tuple[str, str]] = []

    def __call__(self, method, path, payload=None, prefer=""):
        if method == "POST" and path.startswith("mesh_work_claims"):
            self.claimed.append((payload["linear_id"], payload["machine"]))
            return 201, ""
        if method == "PATCH" and path.startswith("mesh_work_claims"):
            return 200, json.dumps(self.patch_rows)
        if method == "GET" and "state=eq.failed" in path:
            return 200, json.dumps(self.failed_rows)
        return 200, "[]"


@pytest.fixture
def mesh_client(monkeypatch):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sb = _Sb()
    monkeypatch.setattr(mesh, "_sb", sb)
    monkeypatch.setattr(mesh, "_open_claim_ids", lambda: set())
    monkeypatch.setattr(mesh, "_reap_sweep_best_effort", lambda: None)
    mesh.reaped, mesh.gql = [], []
    monkeypatch.setattr(mesh, "_mark_issue_reaped", lambda lid: mesh.reaped.append(lid) or True)

    def gql(q):
        mesh.gql.append(q)
        if q.startswith("query{issue("):
            return {"issue": {"id": "uuid-1"}}
        if q.startswith("query{team"):
            return {"team": {"states": {"nodes": [{"id": "st", "type": "started"}]}}}
        if q.startswith("mutation"):
            return {"issueUpdate": {"success": True}, "commentCreate": {"success": True}}
        return {"issues": {"nodes": mesh.queue}}

    mesh.queue = []
    monkeypatch.setattr(mesh, "_linear_graphql", gql)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh, sb


def _update(client, **body):
    return client.post("/api/mesh/claim/update", json={"linear_id": "RA-1", "state": "failed", **body}, headers=HDR)


def test_a_failed_claim_returns_to_the_queue_with_the_reason(mesh_client):
    client, mesh, _ = mesh_client
    assert _update(client, error_code="runner_exception").status_code == 200
    assert mesh.reaped == ["RA-1"]
    comment = next(q for q in mesh.gql if "commentCreate" in q)
    assert "Phill_Desktop (runner_exception)" in comment


def test_free_text_never_reaches_the_comment(mesh_client):
    client, mesh, _ = mesh_client
    _update(client, error_code="sk-ant-looks-like-a-key")
    comment = next(q for q in mesh.gql if "commentCreate" in q)
    assert "sk-ant" not in comment and "(failed)" in comment


def test_a_stale_failed_report_matching_no_open_claim_changes_nothing(mesh_client):
    client, mesh, sb = mesh_client
    sb.patch_rows = []
    _update(client, error_code="runner_exception")
    assert mesh.reaped == [] and not any("commentCreate" in q for q in mesh.gql)


def _issue(ident: str) -> dict:
    return {"id": ident, "identifier": ident, "title": ident, "description": "d", "priority": 1,
            "team": {"id": "team-1"}, "labels": {"nodes": [{"name": "mesh:auto"}]}}


def test_the_node_that_failed_a_ticket_is_offered_the_next_one_instead(mesh_client):
    client, mesh, sb = mesh_client
    mesh.queue = [_issue("RA-1"), _issue("RA-2")]
    sb.failed_rows = [{"linear_id": "RA-1"}]
    got = client.post("/api/mesh/claim/self", json={"host": "Phill_Desktop"}, headers=HDR).json()
    assert got["claimed"]["linear_id"] == "RA-2"


def test_an_unreadable_failure_table_skips_nothing():
    from app.server import mesh_requeue
    assert mesh_requeue.failed_here(lambda path: (401, '{"message":"JWT expired"}'), "Mini") == set()
