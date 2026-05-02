"""
swarm/linear_tools.py — RA-1839: Linear flow tools.

Wraps the Linear GraphQL API as flow_engine-callable tools. Same pattern
as swarm/bots/scribe.py — direct GraphQL via urllib.request, fire-and-
forget on transient errors, structured outputs.

Tools registered with flow_engine:
  * mcp.linear.list_issues(team, state?, limit?)
  * mcp.linear.save_issue(team, project?, title, description?, priority?)
  * mcp.linear.save_comment(issue_id, body)

Auth: LINEAR_API_KEY env var. Fail-soft if missing (returns
{"error": "no_api_key"} so a flow can decide what to do).

Team / project lookup: when called with a team key (e.g. "RA"), the
tool resolves it to a UUID via a cached Linear API query. Same for
project names. Cache lives for the lifetime of the process.

Safety:
  * Kill-switch aware via TAO_SWARM_ENABLED — when off, save_issue
    returns {"status": "skipped_kill_switch"} without hitting the API.
  * Dry-run: pass dry_run=True to any write tool — returns a synthetic
    response shape without API call.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from typing import Any

log = logging.getLogger("swarm.linear_tools")

LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
_TEAM_CACHE: dict[str, dict[str, Any]] = {}  # key (lower) -> team dict
_PROJECT_CACHE: dict[tuple[str, str], dict[str, Any]] = {}  # (team_id, name_lower) -> project


def _api_key() -> str:
    return os.environ.get("LINEAR_API_KEY", "").strip()


def _kill_switch_active() -> bool:
    return os.environ.get("TAO_SWARM_ENABLED", "0") != "1"


def _gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue a GraphQL query with auth. Returns parsed JSON or {'error': ...}."""
    key = _api_key()
    if not key:
        return {"error": "no_api_key"}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.warning("Linear GraphQL error: %s", exc)
        return {"error": "request_failed", "exception": repr(exc)}


def _resolve_team(team: str) -> dict[str, Any] | None:
    """Resolve a team identifier (key like 'RA' or name like 'RestoreAssist' or UUID).

    Returns {id, key, name} or None if not found.
    """
    if not team:
        return None
    cached = _TEAM_CACHE.get(team.lower())
    if cached:
        return cached
    # If looks like a UUID, trust it
    if len(team) == 36 and team.count("-") == 4:
        return {"id": team, "key": "", "name": ""}

    res = _gql(
        "query { teams(first: 100) { nodes { id key name } } }"
    )
    if "error" in res:
        return None
    for t in res.get("data", {}).get("teams", {}).get("nodes", []):
        _TEAM_CACHE[t["key"].lower()] = t
        _TEAM_CACHE[t["name"].lower()] = t
        _TEAM_CACHE[t["id"].lower()] = t
    return _TEAM_CACHE.get(team.lower())


def _resolve_project(team_id: str, project: str | None) -> dict[str, Any] | None:
    """Resolve a project name within a team to {id, name}. Returns None if unset."""
    if not project:
        return None
    key = (team_id, project.lower())
    if key in _PROJECT_CACHE:
        return _PROJECT_CACHE[key]
    if len(project) == 36 and project.count("-") == 4:
        return {"id": project, "name": ""}

    res = _gql(
        """
        query($teamId: String!) {
          team(id: $teamId) { projects(first: 100) { nodes { id name } } }
        }
        """,
        {"teamId": team_id},
    )
    if "error" in res:
        return None
    for p in res.get("data", {}).get("team", {}).get("projects", {}).get("nodes", []):
        _PROJECT_CACHE[(team_id, p["name"].lower())] = p
    return _PROJECT_CACHE.get(key)


# ── Public flow tools ────────────────────────────────────────────────────────


def list_issues(
    team: str,
    state: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """List issues in a team. `state` filter is a state-name substring."""
    t = _resolve_team(team)
    if not t:
        return {"error": "team_not_found", "team": team}

    res = _gql(
        """
        query($teamId: String!, $first: Int!) {
          team(id: $teamId) {
            issues(first: $first, orderBy: updatedAt) {
              nodes {
                id identifier title state { name } priority
                updatedAt assignee { name }
              }
            }
          }
        }
        """,
        {"teamId": t["id"], "first": min(limit, 100)},
    )
    if "error" in res:
        return res

    nodes = res.get("data", {}).get("team", {}).get("issues", {}).get("nodes", [])
    if state:
        nodes = [n for n in nodes if state.lower() in n.get("state", {}).get("name", "").lower()]
    return {
        "team": t["key"] or t["id"],
        "issues": [
            {
                "id": n["identifier"], "title": n["title"],
                "state": (n.get("state") or {}).get("name", "?"),
                "priority": n.get("priority"),
                "updated": n.get("updatedAt"),
                "assignee": (n.get("assignee") or {}).get("name", "unassigned"),
            }
            for n in nodes
        ],
    }


def save_issue(
    team: str,
    title: str,
    *,
    project: str | None = None,
    description: str | None = None,
    priority: int = 3,
    labels: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a new Linear issue. Returns {id, identifier, url} on success.

    `priority`: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low. Default 3.
    """
    if _kill_switch_active() and not dry_run:
        return {"status": "skipped_kill_switch"}

    if dry_run:
        return {
            "status": "dry_run",
            "team": team,
            "title": title,
            "project": project,
            "priority": priority,
        }

    t = _resolve_team(team)
    if not t:
        return {"error": "team_not_found", "team": team}

    project_id = None
    if project:
        p = _resolve_project(t["id"], project)
        if not p:
            return {"error": "project_not_found", "team": team, "project": project}
        project_id = p["id"]

    input_obj: dict[str, Any] = {
        "teamId": t["id"],
        "title": title,
        "priority": priority,
    }
    if description:
        input_obj["description"] = description
    if project_id:
        input_obj["projectId"] = project_id

    res = _gql(
        """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title url priority }
          }
        }
        """,
        {"input": input_obj},
    )
    if "error" in res:
        return res
    data = res.get("data", {}).get("issueCreate", {})
    if not data.get("success"):
        return {"error": "create_failed", "raw": res}
    iss = data["issue"]
    return {
        "status": "created",
        "id": iss["id"],
        "identifier": iss["identifier"],
        "title": iss["title"],
        "url": iss["url"],
        "priority": iss["priority"],
    }


def save_comment(
    issue_id: str,
    body: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Append a comment to an existing issue. `issue_id` accepts UUID or 'RA-1839'."""
    if _kill_switch_active() and not dry_run:
        return {"status": "skipped_kill_switch"}
    if dry_run:
        return {"status": "dry_run", "issue_id": issue_id, "body_preview": body[:80]}

    # If looks like RA-1839, resolve to UUID first
    if "-" in issue_id and len(issue_id) < 20:
        res = _gql(
            """
            query($identifier: String!) { issue(id: $identifier) { id } }
            """,
            {"identifier": issue_id},
        )
        if "error" in res:
            return res
        uuid_ = (res.get("data", {}).get("issue") or {}).get("id")
        if not uuid_:
            return {"error": "issue_not_found", "issue_id": issue_id}
        issue_id = uuid_

    res = _gql(
        """
        mutation($input: CommentCreateInput!) {
          commentCreate(input: $input) { success comment { id url } }
        }
        """,
        {"input": {"issueId": issue_id, "body": body}},
    )
    if "error" in res:
        return res
    data = res.get("data", {}).get("commentCreate", {})
    if not data.get("success"):
        return {"error": "comment_failed", "raw": res}
    return {"status": "commented",
            "comment_id": data["comment"]["id"],
            "url": data["comment"]["url"]}


def register_with_flow_engine() -> int:
    """Register all three tools with flow_engine. Returns count registered."""
    from . import flow_engine

    flow_engine.register_tool("mcp.linear.list_issues",
                              lambda **kw: list_issues(**kw))
    flow_engine.register_tool("mcp.linear.save_issue",
                              lambda **kw: save_issue(**kw))
    flow_engine.register_tool("mcp.linear.save_comment",
                              lambda **kw: save_comment(**kw))
    return 3


# Auto-register on import (idempotent)
try:
    register_with_flow_engine()
except Exception as exc:
    log.debug("linear_tools auto-register skipped: %s", exc)


__all__ = [
    "list_issues", "save_issue", "save_comment", "register_with_flow_engine",
]
