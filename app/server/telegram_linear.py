"""Pi-Dev Linear contract for POST /api/telegram/linear/create (RA-8632).

The route passes its own Linear transport (`gql`): it returns the GraphQL `data`
object and raises HTTPException(502) on any transport, HTTP or GraphQL error.
Every step below therefore fails closed: nothing is filed unless the duplicate
lookup, the routing and the source label all succeeded first.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import HTTPException

from .goal_ticket import _source_label_id, normalize_repo

GqlFn = Callable[..., dict[str, Any]]

_SOURCE = "Telegram /linear/create"

# Same filter as swarm/margot_tools._lookup_open_issue (behind
# find_open_issue_by_title): exact title, open state types only, and `ID!` for
# the team comparator (String! fails Linear's IDComparator). That helper cannot
# be called here: it resolves teams by name and collapses "lookup failed" into
# "no match", which would file blind when Linear is down.
_FIND_OPEN_BY_TITLE = (
    "query FindOpenByTitle($teamId: ID!, $title: String!) { issues(filter: { "
    "team: { id: { eq: $teamId } }, "
    'state: { type: { in: ["triage","backlog","unstarted","started"] } }, '
    "title: { eq: $title } }, first: 1) { nodes { id identifier url title } } }"
)
_PROJECT_BY_NAME = (
    "query ProjectByName($name: String!) { projects(filter: { name: { eq: $name } }, "
    "first: 5) { nodes { id name teams(first: 5) { nodes { id } } } } }"
)
_ISSUE_CREATE = """
mutation Create($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url title }
  }
}
"""


def repo_name(repo: str) -> str:
    """`owner/name`, a GitHub URL or a bare `name` -> `name` ('' if unusable)."""
    slug = normalize_repo(repo)
    if slug:
        return slug.split("/", 1)[1]
    bare = (repo or "").strip()
    return "" if "/" in bare else bare


def route_by_repo(gql: GqlFn, repo: str) -> dict[str, str]:
    """Pattern B: the Linear project whose name equals the repo name, verbatim."""
    name = repo_name(repo)
    if not name:
        raise HTTPException(422, "repo must be a GitHub owner/name or a bare repository name")
    data = gql(_PROJECT_BY_NAME, {"name": name})
    nodes = ((data.get("projects") or {}).get("nodes")) or []
    matches = [p for p in nodes if p.get("name") == name]
    if len(matches) != 1:
        raise HTTPException(
            422, f"need exactly one Linear project named {name!r}, found {len(matches)}; nothing created"
        )
    project = matches[0]
    teams = [t.get("id") for t in ((project.get("teams") or {}).get("nodes") or []) if t.get("id")]
    if not teams:
        raise HTTPException(422, f"Linear project {name!r} has no team; nothing created")
    return {"teamId": teams[0], "projectId": project["id"]}


def find_open_issue(gql: GqlFn, team_id: str, title: str) -> dict[str, Any] | None:
    """Open issue with exactly this title in the team, or None. Fails closed."""
    data = gql(_FIND_OPEN_BY_TITLE, {"teamId": team_id, "title": title})
    issues = data.get("issues")
    nodes = issues.get("nodes") if isinstance(issues, dict) else None
    if not isinstance(nodes, list):
        raise HTTPException(502, "Linear duplicate lookup returned no issue list; nothing created")
    return nodes[0] if nodes else None


def source_label_id(gql: GqlFn, team_id: str) -> str:
    """Resolve `pi-dev:source` the way goal_ticket does; refuse to file without it."""

    def envelope(query: str, variables: dict | None = None) -> dict[str, Any]:
        try:
            return {"data": gql(query, variables)}
        except HTTPException as exc:
            return {"error": str(exc.detail)}

    label_id = _source_label_id(envelope, team_id)
    if not label_id:
        raise HTTPException(502, "could not resolve the pi-dev:source label; nothing created")
    return label_id


def new_run_id(now: datetime) -> str:
    return f"telegram-{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


def with_footer(description: str | None, run_id: str, filed: str) -> str:
    footer = (
        "---\n**Pi-Dev-Ops run**\n"
        f"- Run ID: `{run_id}`\n"
        f"- Source: {_SOURCE}\n"
        f"- Filed: {filed}"
    )
    body = (description or "").rstrip()
    return f"{body}\n\n{footer}" if body else footer


def _shape(issue: dict[str, Any], *, existing: bool, run_id: str | None) -> dict[str, Any]:
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "url": issue.get("url"),
        "title": issue.get("title"),
        "existing": existing,
        "run_id": run_id,
    }


def create_or_reuse(
    gql: GqlFn, *, routing: dict, title: str, description: str | None, priority: int
) -> dict[str, Any]:
    """Return the open same-title issue, or file a labelled, footed new one."""
    team_id = routing["teamId"]
    found = find_open_issue(gql, team_id, title)
    if found:
        return _shape(found, existing=True, run_id=None)
    label_id = source_label_id(gql, team_id)
    now = datetime.now(timezone.utc)
    run_id = new_run_id(now)
    inp: dict[str, Any] = {
        "teamId": team_id,
        "title": title,
        "priority": priority,
        "labelIds": [label_id],
        "description": with_footer(description, run_id, now.date().isoformat()),
    }
    if routing.get("projectId"):
        inp["projectId"] = routing["projectId"]
    result = gql(_ISSUE_CREATE, {"input": inp}).get("issueCreate") or {}
    if not result.get("success"):
        raise HTTPException(502, "Linear issueCreate returned success=false")
    return _shape(result.get("issue") or {}, existing=False, run_id=run_id)
