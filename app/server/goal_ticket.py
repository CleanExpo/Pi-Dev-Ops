"""Goal → Linear ticket — Backlog only, no autonomy markers."""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .goal_ticket_children import file_sub_tasks
from .goal_ticket_format import format_draft_notes

log = logging.getLogger("pi-ceo.goal_ticket")

_PROJECTS_JSON = Path(__file__).resolve().parents[2] / "config" / "harness" / "projects.json"

_LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
_SOURCE_LABEL = "pi-dev:source"
_AUTONOMY_LABEL = "pi-dev:autonomous"
_BACKLOG_STATE = "Backlog"
_READY_STATE = "Ready for Pi-Dev"
_PI_DEV_OPS_REGISTRY_ID = "pi-dev-ops"
_MIN_TEXT = 8
GqlFn = Callable[..., dict[str, Any]]


def normalize_repo(raw: str) -> str:
    """Return `owner/name` or empty if the input is not a GitHub repo."""
    s = (raw or "").strip().rstrip("/")
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
    )
    lower = s.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            s = s[len(prefix) :]
            break
    if s.endswith(".git"):
        s = s[:-4]
    parts = [p for p in s.split("/") if p]
    if len(parts) != 2:
        return ""
    return f"{parts[0]}/{parts[1]}"


def validate_goal(goal: str, repo: str, acceptance: str) -> list[str]:
    """Return names of missing/invalid fields. Empty list means valid."""
    fields: list[str] = []
    if not (goal or "").strip() or len(goal.strip()) < _MIN_TEXT:
        fields.append("goal")
    if not normalize_repo(repo):
        fields.append("repo")
    if not (acceptance or "").strip() or len(acceptance.strip()) < _MIN_TEXT:
        fields.append("acceptance")
    return fields


def title_from_goal(goal: str) -> str:
    line = (goal or "").strip().splitlines()[0].strip()
    return line[:200]


def build_description(
    goal: str,
    repo: str,
    acceptance: str,
    *,
    notes: str = "",
    parent_goal: str = "",
    project_title: str = "",
) -> str:
    parts = [
        f"## Goal\n{goal.strip()}",
        f"## Target repo\n`{repo}`",
        f"## Acceptance\n{acceptance.strip()}",
    ]
    if project_title.strip():
        parts.append(f"## Project\n{project_title.strip()}")
    if parent_goal.strip() and parent_goal.strip() != goal.strip():
        parts.append(f"## Parent goal\n{parent_goal.strip()}")
    if notes.strip():
        parts.append(f"## Why this ticket\n{notes.strip()}")
    parts.append(
        "---\n"
        "Filed via Goal → Linear (dashboard). Status: Backlog. "
        "Not authorised for autonomous pickup.\n"
    )
    return "\n\n".join(parts)


def resolve_project(repo: str) -> dict[str, str] | None:
    """Map owner/name to Linear project. Duplicate Pi-Dev-Ops rows prefer `pi-dev-ops`."""
    slug = normalize_repo(repo)
    if not slug:
        return None
    registry = json.loads(_PROJECTS_JSON.read_text(encoding="utf-8"))
    matches = [
        p for p in registry.get("projects", [])
        if str(p.get("repo") or "").lower() == slug.lower()
        and p.get("linear_project_id")
        and p.get("linear_team_id")
    ]
    if not matches:
        return None
    if len(matches) > 1:
        preferred = [p for p in matches if p.get("id") == _PI_DEV_OPS_REGISTRY_ID]
        if preferred:
            matches = preferred
    chosen = matches[0]
    return {
        "registry_id": str(chosen.get("id") or ""),
        "repo": str(chosen["repo"]),
        "project_id": str(chosen["linear_project_id"]),
        "team_id": str(chosen["linear_team_id"]),
        "project_name": str(chosen.get("linear_project_name") or chosen.get("id") or slug),
    }


def _linear_gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return {"error": "no_api_key"}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        _LINEAR_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("Linear GraphQL error: %s", exc)
        return {"error": "request_failed", "exception": type(exc).__name__}


def _backlog_state_id(gql: GqlFn, team_id: str) -> str | None:
    res = gql(
        "query($id: String!) { team(id: $id) { states { nodes { id name type } } } }",
        {"id": team_id},
    )
    if res.get("error") or res.get("errors"):
        return None
    nodes = (((res.get("data") or {}).get("team") or {}).get("states") or {}).get("nodes") or []
    for state in nodes:
        name = str(state.get("name") or "")
        if name.lower() == _READY_STATE.lower():
            continue
        if name.lower() == _BACKLOG_STATE.lower():
            return str(state["id"])
    return None


def _source_label_id(gql: GqlFn, team_id: str) -> str | None:
    res = gql(
        "query($teamId: String!) { team(id: $teamId) { labels(first: 100) { nodes { id name } } } }",
        {"teamId": team_id},
    )
    if "error" not in res and not res.get("errors"):
        nodes = (((res.get("data") or {}).get("team") or {}).get("labels") or {}).get("nodes") or []
        for label in nodes:
            if str(label.get("name") or "").lower() == _SOURCE_LABEL:
                return str(label["id"])
    created = gql(
        """
        mutation($input: IssueLabelCreateInput!) {
          issueLabelCreate(input: $input) { success issueLabel { id name } }
        }
        """,
        {"input": {"name": _SOURCE_LABEL, "teamId": team_id, "color": "#6B7280"}},
    )
    if created.get("error") or created.get("errors"):
        return None
    label = ((created.get("data") or {}).get("issueLabelCreate") or {}).get("issueLabel") or {}
    name = str(label.get("name") or "")
    if name.lower() == _AUTONOMY_LABEL:
        return None
    return str(label["id"]) if label.get("id") else None


def file_goal(
    goal: str,
    repo: str,
    acceptance: str,
    *,
    gql: GqlFn | None = None,
    title: str | None = None,
    notes: str = "",
    parent_goal: str = "",
    parent_id: str = "",
    project_title: str = "",
) -> dict[str, Any]:
    """Create a Backlog Linear ticket. Never authorises autonomous pickup."""
    missing = validate_goal(goal, repo, acceptance)
    if missing:
        return {"error": "validation", "fields": missing}

    slug = normalize_repo(repo)
    project = resolve_project(slug)
    if not project:
        return {"error": "unknown_repo", "repo": slug}

    client = gql or _linear_gql
    state_id = _backlog_state_id(client, project["team_id"])
    if not state_id:
        return {"error": "backlog_state_missing", "team_id": project["team_id"]}

    label_id = _source_label_id(client, project["team_id"])
    issue_title = (title or "").strip() or title_from_goal(goal)
    issue_input: dict[str, Any] = {
        "teamId": project["team_id"],
        "projectId": project["project_id"],
        "stateId": state_id,
        "title": issue_title[:200],
        "description": build_description(
            goal,
            slug,
            acceptance,
            notes=notes,
            parent_goal=parent_goal,
            project_title=project_title,
        ),
    }
    if parent_id.strip():
        issue_input["parentId"] = parent_id.strip()
    labels = [_SOURCE_LABEL]
    if label_id:
        issue_input["labelIds"] = [label_id]
    else:
        labels = []

    if _AUTONOMY_LABEL in labels:
        return {"error": "autonomy_guard"}
    return _submit_issue(client, issue_input, labels, project, slug)


def _submit_issue(
    client: GqlFn,
    issue_input: dict[str, Any],
    labels: list[str],
    project: dict[str, str],
    slug: str,
) -> dict[str, Any]:
    res = client(
        """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title url }
          }
        }
        """,
        {"input": issue_input},
    )
    if res.get("error"):
        return res
    if res.get("errors"):
        return {"error": "create_failed", "raw": res.get("errors")}
    data = ((res.get("data") or {}).get("issueCreate") or {})
    if not data.get("success"):
        return {"error": "create_failed", "raw": res}
    issue = data.get("issue") or {}
    return {
        "status": "created",
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": _BACKLOG_STATE,
        "labels": labels,
        "repo": slug,
        "project_id": project["project_id"],
        "registry_id": project["registry_id"],
    }


def file_drafts(
    repo: str,
    drafts: list[dict[str, Any]],
    *,
    approved: bool,
    parent_goal: str = "",
    gql: GqlFn | None = None,
    project_title: str = "",
) -> dict[str, Any]:
    """File approved drafts. Refuses unless `approved` is True."""
    if not approved:
        return {"error": "not_approved"}
    if not drafts:
        return {"error": "validation", "fields": ["tickets"]}
    created: list[dict[str, Any]] = []
    for draft in drafts:
        out = file_goal(
            str(draft.get("goal") or ""),
            repo,
            str(draft.get("acceptance") or ""),
            gql=gql,
            title=str(draft.get("title") or ""),
            notes=format_draft_notes(draft),
            parent_goal=parent_goal,
            project_title=project_title,
        )
        if out.get("error"):
            return {
                "error": out["error"],
                "fields": out.get("fields"),
                "filed": created,
                "failed_title": draft.get("title"),
            }
        created.append(out)
        children = file_sub_tasks(
            repo,
            draft,
            parent_id=str(out.get("id") or ""),
            parent_goal=parent_goal,
            project_title=project_title,
            file_goal=file_goal,
            gql=gql,
        )
        if children.get("error"):
            return {**children, "filed": created}
        created.extend(children.get("tickets") or [])
    return {"status": "created", "count": len(created), "tickets": created}
