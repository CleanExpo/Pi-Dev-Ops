"""W1b — the mesh build lane, runner repo routing, swarm intake and idea GO.

Companion to test_w1b_claimable.py (split to stay under the 300-line gate).
The mesh took only `mesh:auto`, so approved `pi-dev:autonomous` work never
reached a logged-in runner; swarm intake read the label `agent-ready`, which
does not exist; GO on an idea filed nothing. No live Linear call: faked.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from w1b_helpers import REPO_ROOT, _issue  # noqa: E402


# ── Mesh: autonomy lane, shared rule, repo routing ───────────────────────────

def _mesh_nodes():
    ato = "20bb0ca6-0176-46c4-be4c-cd34ac89767d"
    return [
        _issue("UNI-2801", state="Ready for Pi-Dev", project=ato),
        _issue("UNI-TODO", state="Todo", project=ato),
        _issue("UNI-UNREG", state="Todo", project="unregistered"),
        _issue("UNI-BLK", state="Todo", project=ato, blockers=[("UNI-1", "started")]),
        _issue("UNI-MESH", labels=("mesh:auto",), project=None),
    ]


def test_mesh_candidates_take_autonomous_todo_and_ready_under_shared_rule():
    from app.server import mesh_lanes
    queries: list = []

    def gql(q):
        queries.append(q)
        if "after:" not in q:
            return {"issues": {"nodes": _mesh_nodes()[:3], "pageInfo": {"hasNextPage": True, "endCursor": "c1"}}}
        return {"issues": {"nodes": _mesh_nodes()[3:], "pageInfo": {"hasNextPage": False}}}

    nodes, repos = mesh_lanes.candidates(gql)
    assert [n["identifier"] for n in nodes] == ["UNI-2801", "UNI-TODO", "UNI-MESH"]
    assert '"pi-dev:autonomous"' in queries[0] and 'after:"c1"' in queries[1]
    assert mesh_lanes.repo_of(nodes[0], repos) == "CleanExpo/ATO"
    assert mesh_lanes.repo_of(nodes[2], repos) is None


def test_dual_labelled_autonomy_ticket_answers_to_the_full_rule_and_its_repo():
    from app.server import mesh_lanes
    ato = "20bb0ca6-0176-46c4-be4c-cd34ac89767d"
    repos = {ato: "CleanExpo/ATO"}
    backlog = _issue("UNI-DUAL", state="Backlog", labels=("pi-dev:autonomous", "mesh:auto"), project=ato)
    ready = _issue("UNI-DUAL2", state="Todo", labels=("pi-dev:autonomous", "mesh:auto"), project=ato)
    assert not mesh_lanes.eligible(backlog, repos)
    assert mesh_lanes.eligible(ready, repos) and mesh_lanes.needs_repo(ready)
    assert mesh_lanes.repo_of(ready, repos) == "CleanExpo/ATO"


def test_explicit_dispatch_ids_pass_the_shared_rule():
    from app.server import mesh_lanes
    ato = "20bb0ca6-0176-46c4-be4c-cd34ac89767d"
    issues = {"UNI-OK": _issue("UNI-OK", labels=("mesh:auto",), project=ato),
              "UNI-BLK": _issue("UNI-BLK", labels=("mesh:auto",), blockers=[("UNI-1", "started")])}

    def gql(q):
        ident = q.split('issue(id:"', 1)[1].split('"', 1)[0]
        return {"issue": issues.get(ident)}

    got = mesh_lanes.explicit(gql, ["UNI-OK", "UNI-BLK", "UNI-GONE"])
    assert [i["identifier"] for i in got] == ["UNI-OK"]


def test_runner_never_builds_a_named_repo_in_its_default_checkout(tmp_path):
    import sys
    sys.path.insert(0, str(REPO_ROOT / "mesh"))
    import repo_guard
    with patch.object(repo_guard, "git_origin", return_value="https://github.com/CleanExpo/Pi-Dev-Ops.git"):
        own = repo_guard.repo_dir_for("CleanExpo/Pi-Dev-Ops", tmp_path, tmp_path / "root")
        other = repo_guard.repo_dir_for("CleanExpo/ATO", tmp_path, tmp_path / "root")
    assert own == tmp_path.resolve()
    assert other != tmp_path.resolve() and not (other / ".git").exists()


# ── Swarm intake reads the real label through the shared rule ───────────────

def test_swarm_intake_uses_shared_rule_not_agent_ready(monkeypatch):
    from swarm import intake_producers as IP
    from swarm import linear_tools
    ato = "20bb0ca6-0176-46c4-be4c-cd34ac89767d"
    sent: list = []

    def gql(query, variables=None):
        sent.append(variables)
        return {"data": {"team": {"issues": {"nodes": [
            _issue("UNI-2801", project=ato), _issue("UNI-X", project=ato, blockers=[("UNI-1", "started")])],
            "pageInfo": {"hasNextPage": False}}}}}

    monkeypatch.setattr(linear_tools, "_resolve_team", lambda _t: {"id": "team"})
    monkeypatch.setattr(linear_tools, "_gql", gql)
    assert IP._agent_ready_tickets() == [("UNI-2801", "t UNI-2801")]
    assert sent[0]["label"] == "pi-dev:autonomous"


# ── GO files one Ready + pi-dev:autonomous ticket ────────────────────────────

def test_go_execute_files_exactly_one_autonomous_ticket(tmp_path):
    from app.server.idea_pipeline import (
        append_and_examine, authorize_go_for, dispose_idea, try_execute_idea,
    )
    created: list = []

    def gql(query, variables=None):
        if "team(id" in query:
            return {"data": {"team": {"states": {"nodes": [{"id": "st-ready", "name": "Ready for Pi-Dev"}]},
                                      "labels": {"nodes": [{"id": "lb-auto", "name": "pi-dev:autonomous"}]}}}}
        if "issues(" in query:
            return {"data": {"issues": {"nodes": []}}}
        created.append(variables["input"])
        return {"data": {"issueCreate": {"success": True, "issue": {
            "id": "i1", "identifier": "RA-9001", "title": "x", "url": "u"}}}}

    packet = append_and_examine(tmp_path, "Teach shop owners to grow with a short video lesson.")
    dispose_idea(tmp_path, packet["idea_id"], "PROMOTE")
    authorize_go_for(tmp_path, packet["idea_id"])
    first = try_execute_idea(tmp_path, packet["idea_id"], gql=gql)
    try_execute_idea(tmp_path, packet["idea_id"], gql=gql)
    assert len(created) == 1
    assert created[0]["stateId"] == "st-ready" and created[0]["labelIds"] == ["lb-auto"]
    assert first["linear_ticket"]["identifier"] == "RA-9001"
    assert first["executed"] is False


def test_go_retry_after_a_lost_create_response_links_instead_of_duplicating(tmp_path):
    from app.server.idea_pipeline import (
        PipelineGateError, append_and_examine, authorize_go_for, dispose_idea, try_execute_idea,
    )
    creates: list = []

    def gql(query, variables=None):
        if "team(id" in query:
            return {"data": {"team": {"states": {"nodes": [{"id": "st", "name": "Ready for Pi-Dev"}]},
                                      "labels": {"nodes": [{"id": "lb", "name": "pi-dev:autonomous"}]}}}}
        if "issues(" in query:  # reconcile: finds the ticket once one was created
            nodes = [{"id": "i1", "identifier": "RA-9001", "url": "u"}] if creates else []
            return {"data": {"issues": {"nodes": nodes}}}
        creates.append(variables["input"])
        return {"errors": [{"message": "timeout after commit"}]}  # committed, response lost

    packet = append_and_examine(tmp_path, "Teach shop owners to grow with a short video lesson.")
    dispose_idea(tmp_path, packet["idea_id"], "PROMOTE")
    authorize_go_for(tmp_path, packet["idea_id"])
    with pytest.raises(PipelineGateError):
        try_execute_idea(tmp_path, packet["idea_id"], gql=gql)
    again = try_execute_idea(tmp_path, packet["idea_id"], gql=gql)
    assert len(creates) == 1 and again["linear_ticket"]["identifier"] == "RA-9001"
