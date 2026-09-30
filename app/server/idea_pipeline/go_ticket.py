"""GO → one Linear build ticket (W1b, estate audit 30/09 rank #1).

``try_execute`` used to record the request and stop ("Never starts a build"),
so an idea Phill said GO on reached no executor. Now execute files exactly one
ticket in Ready for Pi-Dev with ``pi-dev:autonomous`` — the one signal every
executor admits through ``issue_is_claimable``. It starts nothing itself: a
runner or the poller picks the ticket up like any other approved work.

The target is the registry row ``IDEA_GO_PROJECT`` (a projects.json ``id``,
default ``pi-dev-ops``). The autonomy label must already exist on that team;
it is looked up, never created, so a missing label is a loud refusal.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

from ..autonomy_eligibility import AUTONOMY_LABEL, READY_STATUS_NAME
from ..goal_ticket import _PROJECTS_JSON, _linear_gql, _submit_issue

GqlFn = Callable[..., dict[str, Any]]
_DEFAULT_PROJECT = "pi-dev-ops"
_TITLE_MAX = 200


def _target() -> dict[str, str] | None:
    key = os.environ.get("IDEA_GO_PROJECT", "").strip() or _DEFAULT_PROJECT
    registry = json.loads(_PROJECTS_JSON.read_text(encoding="utf-8"))
    for row in registry.get("projects", []):
        if row.get("id") == key and row.get("linear_project_id") and row.get("linear_team_id"):
            return {"registry_id": key, "repo": str(row["repo"]),
                    "project_id": str(row["linear_project_id"]),
                    "team_id": str(row["linear_team_id"])}
    return None


def _team_ids(gql: GqlFn, team_id: str) -> tuple[str | None, str | None]:
    """(Ready for Pi-Dev state id, pi-dev:autonomous label id) on the team."""
    res = gql(
        "query($id: String!) { team(id: $id) {"
        " states { nodes { id name } } labels(first: 250) { nodes { id name } } } }",
        {"id": team_id},
    )
    team = ((res.get("data") or {}).get("team") or {}) if not res.get("error") else {}
    state = next((n["id"] for n in (team.get("states") or {}).get("nodes") or []
                  if n.get("name") == READY_STATUS_NAME), None)
    label = next((n["id"] for n in (team.get("labels") or {}).get("nodes") or []
                  if n.get("name") == AUTONOMY_LABEL), None)
    return state, label


def file_go_ticket(packet: dict[str, Any], *, gql: GqlFn | None = None) -> dict[str, Any]:
    """Create the build ticket for a GO'd idea. Returns the ticket or ``{"error": ...}``."""
    target = _target()
    if not target:
        return {"error": "go_project_unregistered"}
    client = gql or _linear_gql
    state_id, label_id = _team_ids(client, target["team_id"])
    if not state_id:
        return {"error": "ready_state_missing", "team_id": target["team_id"]}
    if not label_id:
        return {"error": "autonomy_label_missing", "team_id": target["team_id"]}
    text = str(packet.get("text") or "").strip()
    issue_input = {
        "teamId": target["team_id"], "projectId": target["project_id"],
        "stateId": state_id, "labelIds": [label_id],
        "title": (text.splitlines()[0] if text else f"Idea {packet.get('idea_id')}")[:_TITLE_MAX],
        "description": (
            f"## Idea\n{text}\n\n## Approval\nPROMOTE, then GO at {packet.get('go_at')}.\n\n"
            f"---\nFiled by the idea pipeline on execute (idea `{packet.get('idea_id')}`)."
        ),
    }
    out = _submit_issue(client, issue_input, [AUTONOMY_LABEL], target, target["repo"])
    if not out.get("error"):
        out["state"] = READY_STATUS_NAME
    return out
