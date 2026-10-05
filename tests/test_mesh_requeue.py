"""A failed mesh claim goes back in the queue, says why, and skips the node that failed it (RA-7802).

On 28/09 RA-7794 and RA-7800 each failed and then sat In Progress, never
offered again, with nothing in Linear saying why, until a person went looking.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh_helpers import is_issue_read, issue_by_id  # noqa: E402

HDR = {"X-Pi-CEO-Secret": "test-secret"}


class _Sb:
    """PATCH answers with the `open_rows` its filter matches, as PostgREST would;
    GET of failed claims answers with `failed_rows`."""

    def __init__(self):
        self.open_rows = [{"id": "c-new", "linear_id": "RA-1", "state": "working",
                           "machine": "Phill_Desktop"}]
        self.failed_rows: list[dict] = []
        self.claimed: list[tuple[str, str]] = []
        self.patches: list[tuple[str, dict]] = []
        self.inserted: list[dict] = []

    def _matches(self, row: dict, query: str) -> bool:
        params = dict(urllib.parse.parse_qsl(query))
        if params.get("linear_id") != f"eq.{row['linear_id']}":
            return False
        # Every other eq-filter applies to the row as PostgREST would, so a filter the
        # route adds (a column this fake does not know, say) narrows the match here too.
        return all(v == f"eq.{row.get(k)}" for k, v in params.items() if k not in ("linear_id", "state"))

    def __call__(self, method, path, payload=None, prefer=""):
        if method == "POST" and path.startswith("mesh_work_claims"):
            self.claimed.append((payload["linear_id"], payload["machine"]))
            self.inserted.append(payload)
            return 201, ""  # return=minimal: the route must already know the row's id
        if method == "PATCH" and path.startswith("mesh_work_claims"):
            query = path.split("?", 1)[1]
            self.patches.append((query, payload))
            return 200, json.dumps([{**r, **payload} for r in self.open_rows if self._matches(r, query)])
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
        if is_issue_read(q):  # RA-7910: a queued ticket reads back whole; any other id still resolves for the reaper
            found = issue_by_id(q, mesh.queue)
            return found if found["issue"] else {"issue": {"id": "uuid-1"}}
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
    report = {"linear_id": "RA-1", "state": "failed", "host": "Phill_Desktop", "claim_id": "c-new", **body}
    return client.post("/api/mesh/claim/update", json=report, headers=HDR)


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
    sb.open_rows = []
    _update(client, error_code="runner_exception")
    assert mesh.reaped == [] and not any("commentCreate" in q for q in mesh.gql)


def test_a_stale_failed_report_cannot_close_another_nodes_claim(mesh_client):
    client, mesh, sb = mesh_client
    sb.open_rows = [{"id": "c-mini", "linear_id": "RA-1", "state": "working", "machine": "Mini"}]
    _update(client, claim_id="c-mini", error_code="runner_exception")  # even citing Mini's own row
    assert mesh.reaped == [] and not any("commentCreate" in q for q in mesh.gql)
    assert sb.open_rows[0]["state"] == "working"


def test_only_the_node_that_held_a_claim_may_requeue_it():
    """Behind the PATCH filter, in case a filter ever matches wider than it should."""
    from app.server import mesh_requeue
    assert mesh_requeue.owns({"machine": "Mini"}, "Mini")
    assert not mesh_requeue.owns({"machine": "Mini"}, "Phill_Desktop")
    assert not mesh_requeue.owns({"machine": "Mini"}, None)


def test_a_late_report_from_an_old_run_cannot_close_the_new_claim(mesh_client):
    """Codex round 2: the new claim on the same node had no branch yet, and a
    branch-null exception let the old run's report close it."""
    client, mesh, _ = mesh_client
    _update(client, claim_id="c-old", error_code="runner_exception")
    assert mesh.reaped == []


def test_a_failure_before_any_branch_was_stored_still_requeues(mesh_client):
    client, mesh, sb = mesh_client
    sb.open_rows[0]["state"] = "claimed"
    _update(client, error_code="repo_missing")
    assert mesh.reaped == ["RA-1"]


@pytest.mark.parametrize("missing", ["host", "claim_id"])
def test_ending_a_claim_without_naming_node_and_row_changes_nothing(mesh_client, missing):
    """Codex round 2: a report with no host (a runner from before RA-7802) PATCHed
    whatever claim the ticket had open, another node's included."""
    client, mesh, sb = mesh_client
    sb.open_rows = [{"id": "c-mini", "linear_id": "RA-1", "state": "working", "machine": "Mini"}]
    assert _update(client, **{missing: None}).status_code == 422
    assert mesh.reaped == [] and sb.open_rows[0]["state"] == "working"


def test_a_self_claim_hands_back_its_claim_row_id(mesh_client):
    """The runner can only name its claim row if claiming told it which one it got."""
    client, mesh, sb = mesh_client
    mesh.queue = [_issue("RA-2")]
    got = client.post("/api/mesh/claim/self", json={"host": "Phill_Desktop"}, headers=HDR).json()
    assert got["claimed"]["id"] == sb.inserted[-1]["id"]
    assert str(uuid.UUID(got["claimed"]["id"])) == got["claimed"]["id"]


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



def test_the_claim_id_is_chosen_before_the_insert_so_nothing_depends_on_its_reply(mesh_client):
    """Codex rounds 3-4: an id read back from the insert could be missing, and the
    release fallback could fail too, stranding the ticket. The id is now chosen first."""
    client, mesh, sb = mesh_client
    mesh.queue = [_issue("RA-2"), _issue("RA-3")]
    first = client.post("/api/mesh/claim/self", json={"host": "Phill_Desktop"}, headers=HDR).json()
    second = client.post("/api/mesh/claim/self", json={"host": "Mini"}, headers=HDR).json()
    assert first["claimed"]["id"] == sb.inserted[0]["id"] != second["claimed"]["id"] == sb.inserted[1]["id"]
    assert sb.patches == []  # nothing to release
