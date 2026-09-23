"""`/claim/self` also takes `idea:plan` tickets, and says which lane each one runs in.

`mesh:auto` is the build lane: the node makes a worktree and changes code. `idea:plan`
is the plan lane: the node runs a read-only gs-autoplan review and returns a Board
packet. A ticket carrying BOTH is plan, because an idea is never built before it is
reviewed — a node that read `build` there would write code for an unreviewed idea.

The packet half: a plan-lane node hands its packet back on `/claim/update`, and the
server attaches it to the idea-pipeline item the Board panel reads.
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
    """Claim INSERT and claim PATCH both succeed; records what was sent. The PATCH
    answers with `patch_rows`, the rows PostgREST says it updated."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []
        self.patch_rows = [{"linear_id": "UNI-9", "state": "done", "machine": "nodeA"}]

    def __call__(self, method, path, payload=None, prefer=""):
        self.calls.append((method, path))
        if method == "POST" and path.startswith("mesh_work_claims"):
            return 201, ""
        if method == "PATCH" and path.startswith("mesh_work_claims"):
            return 200, json.dumps(self.patch_rows)
        return 200, "[]"


@pytest.fixture
def mesh_client(monkeypatch, tmp_path):
    from app.server import config as _config
    monkeypatch.setattr(_config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    sys.modules.pop("app.server.routes.mesh", None)
    from app.server import mesh_lanes
    from app.server.routes import mesh
    monkeypatch.setattr(mesh.config, "INTERNAL_WEBHOOK_SECRET", "test-secret", raising=False)
    monkeypatch.setattr(mesh_lanes, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mesh, "_sb", _Sb())
    monkeypatch.setattr(mesh, "_open_claim_ids", lambda: set())
    monkeypatch.setattr(mesh, "_reap_sweep_best_effort", lambda: None)
    app = FastAPI()
    app.include_router(mesh.router)
    return TestClient(app), mesh


def _issue(ident: str, labels: list[str], priority: int = 1) -> dict:
    return {"id": ident, "identifier": ident, "title": f"title {ident}",
            "description": "desc", "priority": priority, "team": {"id": "team-1"},
            "labels": {"nodes": [{"name": n} for n in labels]}}


def _serve(mesh, issues: list[dict]) -> list[str]:
    queries: list[str] = []

    def _gql(q):
        queries.append(q)
        if q.startswith("query{team"):
            return {"team": {"states": {"nodes": [{"id": "st", "type": "started"}]}}}
        if q.startswith("mutation"):
            return {"issueUpdate": {"success": True}}
        return {"issues": {"nodes": issues}}

    mesh._linear_graphql = _gql
    return queries


def _claim(client) -> dict:
    return client.post("/api/mesh/claim/self", json={"host": "nodeA"}, headers=HDR).json()


@pytest.mark.parametrize("labels, lane", [
    (["mesh:auto"], "build"),
    (["idea:plan"], "plan"),
    (["mesh:auto", "idea:plan"], "plan"),
    (["idea:plan", "mesh:auto"], "plan"),
])
def test_claim_self_reports_the_lane_for_each_label_set(mesh_client, labels, lane):
    client, mesh = mesh_client
    _serve(mesh, [_issue("UNI-9", labels)])
    claimed = _claim(client)["claimed"]
    assert claimed["linear_id"] == "UNI-9"
    assert claimed["lane"] == lane


def test_claim_self_asks_linear_for_both_labels_and_their_names(mesh_client):
    """The lane is decided from the labels Linear returns, so the query must both
    admit `idea:plan` tickets and select label names. A query that filtered on
    mesh:auto alone would never surface an idea at all."""
    client, mesh = mesh_client
    queries = _serve(mesh, [_issue("UNI-9", ["idea:plan"])])
    _claim(client)
    issue_query = next(q for q in queries if q.startswith("query{issues"))
    assert '"idea:plan"' in issue_query and '"mesh:auto"' in issue_query
    assert "labels{nodes{name}}" in issue_query


def test_plan_lane_claim_uses_the_same_atomic_insert(mesh_client):
    """Same claim row, same unique index: a plan claim is not a side door."""
    client, mesh = mesh_client
    _serve(mesh, [_issue("UNI-9", ["idea:plan"])])
    _claim(client)
    assert ("POST", "mesh_work_claims") in mesh._sb.calls


def _update(client, **body) -> dict:
    payload = {"linear_id": "UNI-9", "state": "done", "host": "nodeA", **body}
    return client.post("/api/mesh/claim/update", json=payload, headers=HDR).json()


def _pipeline(tmp_path):
    from app.server.idea_pipeline import examine_intake
    return examine_intake(tmp_path)


def test_packet_md_creates_an_idea_pipeline_item_the_panel_lists(mesh_client, tmp_path):
    client, _ = mesh_client
    r = _update(client, packet_md="# Board packet\nVerdict: PROMOTE", title="Coach cafe owners")
    assert r["ok"] is True and r["idea_id"]
    rows = [p for p in _pipeline(tmp_path) if p.get("linear_id") == "UNI-9"]
    assert len(rows) == 1
    assert rows[0]["plan_packet_md"].startswith("# Board packet")
    assert rows[0]["text"] == "Coach cafe owners"
    assert rows[0]["status"] == "awaiting_dispose"


def test_packet_md_attaches_to_the_existing_item_instead_of_duplicating(mesh_client, tmp_path):
    client, _ = mesh_client
    _update(client, packet_md="first", title="Coach cafe owners")
    _update(client, packet_md="second", title="Coach cafe owners")
    rows = [p for p in _pipeline(tmp_path) if p.get("linear_id") == "UNI-9"]
    assert [r["plan_packet_md"] for r in rows] == ["second"]


def test_packet_md_attaches_to_a_matching_ideas_md_item(mesh_client, tmp_path):
    """An idea dropped in IDEAS.md and then filed to Linear under the same words is
    one idea, not two cards on the Board — and attaching the review must not wipe what
    the Board already decided about it."""
    from app.server.idea_pipeline import append_and_examine, dispose_idea
    client, _ = mesh_client
    dropped = append_and_examine(tmp_path, "Coach cafe owners on pricing")
    dispose_idea(tmp_path, dropped["idea_id"], "PARK")
    r = _update(client, packet_md="packet", title="Coach cafe owners on pricing")
    assert r["idea_id"] == dropped["idea_id"]
    rows = _pipeline(tmp_path)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "PARK" and rows[0]["plan_packet_md"] == "packet"


def test_re_review_follows_the_ticket_when_its_title_changes(mesh_client, tmp_path):
    """The Linear id, not the title, is what identifies a reviewed idea: a ticket
    retitled between reviews is still one card."""
    client, _ = mesh_client
    first = _update(client, packet_md="first", title="Coach cafe owners")
    second = _update(client, packet_md="second", title="Coach cafe owners on pricing")
    assert second["idea_id"] == first["idea_id"]
    rows = [p for p in _pipeline(tmp_path) if p.get("linear_id") == "UNI-9"]
    assert [r["plan_packet_md"] for r in rows] == ["second"]


def test_packet_md_is_capped_at_20000_chars_not_rejected(mesh_client, tmp_path):
    """Rejecting an oversized packet would fail the claim update and leave the
    ticket locked; truncating keeps the claim moving."""
    client, _ = mesh_client
    r = _update(client, packet_md="x" * 25_000, title="t")
    assert r["ok"] is True
    row = next(p for p in _pipeline(tmp_path) if p.get("linear_id") == "UNI-9")
    assert len(row["plan_packet_md"]) == 20_000


def test_update_without_packet_md_attaches_nothing(mesh_client, tmp_path):
    client, _ = mesh_client
    r = _update(client)
    assert r["ok"] is True and r.get("idea_id") is None
    assert _pipeline(tmp_path) == []


def test_failed_update_does_not_attach_a_packet(mesh_client, tmp_path):
    client, _ = mesh_client
    _update(client, state="failed", packet_md="partial output")
    assert _pipeline(tmp_path) == []


# ── review round 1: who may attach, and to what ─────────────────────────────


@pytest.mark.parametrize("rows, host", [
    ([{"linear_id": "UNI-9", "state": "done", "machine": "nodeA"}], "nodeB"),
    ([{"linear_id": "UNI-9", "state": "done", "machine": "nodeA"}], None),
    ([], "nodeA"),
])
def test_packet_for_a_claim_the_caller_does_not_hold_is_not_attached(
        mesh_client, tmp_path, rows, host):
    """Every node shares the mesh secret, so a 2xx PATCH proves nothing about who
    holds the claim. Attach only when a row matched AND it is the caller's."""
    client, mesh = mesh_client
    mesh._sb.patch_rows = rows
    r = _update(client, packet_md="forged packet", title="t", host=host)
    assert r.get("idea_id") is None
    assert _pipeline(tmp_path) == []


def test_title_match_never_takes_over_another_tickets_card(mesh_client, tmp_path):
    """Two tickets with the same title are two ideas once each has its own Linear
    id: UNI-2's review must not overwrite the card that belongs to UNI-1."""
    client, mesh = mesh_client
    first = _update(client, linear_id="UNI-1", packet_md="review of 1", title="Same title")
    mesh._sb.patch_rows = [{"linear_id": "UNI-2", "state": "done", "machine": "nodeA"}]
    second = _update(client, linear_id="UNI-2", packet_md="review of 2", title="Same title")
    assert first["idea_id"] != second["idea_id"]
    rows = {p["linear_id"]: p for p in _pipeline(tmp_path) if p.get("linear_id")}
    assert set(rows) == {"UNI-1", "UNI-2"}
    assert rows["UNI-1"]["plan_packet_md"] == "review of 1"
    assert rows["UNI-2"]["plan_packet_md"] == "review of 2"


def test_dispatcher_never_assigns_an_idea_plan_ticket():
    """The dispatcher's claims carry no lane, so the runner treats them as build.
    A ticket carrying idea:plan (alone or with mesh:auto) must therefore never be
    dispatched: it reaches a node only through /claim/self, which says `plan`."""
    from app.server import mesh_dispatch_service as svc
    from app.server.routes import mesh as real_mesh

    class Routes:
        claims: list = []

        def _open_claim_ids(self):
            return set()

        def _sb(self, method, path, body=None, *, prefer=""):
            self.claims.append(body["linear_id"])
            return 201, ""

        def _mark_issue_in_progress(self, ticket):
            return True

    routes = Routes()
    tickets = [_issue("UNI-1", ["mesh:auto"]), _issue("UNI-2", ["idea:plan"]),
               _issue("UNI-3", ["mesh:auto", "idea:plan"])]
    svc._assign(routes, tickets, [{"host": "nodeA"}])
    assert routes.claims == ["UNI-1"]
    assert "labels{nodes{name}}" in real_mesh._MESH_AUTO_QUERY
