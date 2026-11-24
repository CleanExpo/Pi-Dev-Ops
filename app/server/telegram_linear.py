"""Pi-Dev Linear contract for POST /api/telegram/linear/create (RA-8632).

The route passes its own Linear transport (`gql`): it returns the GraphQL `data`
object and raises HTTPException(502) on any transport, HTTP or GraphQL error.
Every step below fails closed: nothing is filed unless routing, the duplicate
lookup and the source label all succeeded and every Linear answer was well
formed. A malformed answer is 502, never read as "nothing there".

Concurrency: look-up-then-create is serialised per (team id, title) with an
in-process lock, so identical requests inside ONE worker process file once.
Requests landing on different workers or replicas can still both miss the
lookup and file twice; closing that needs a shared lock or an idempotency key
that Linear itself enforces, and neither exists here.

Known limits, deliberately not implemented:
- The contract's `Pi-Dev Run ID` custom field is not set. Nothing in this
  repository sets it today; the run id lives only in the description footer.
- The footer carries no `Source commit` or `Dashboard session` line. A Telegram
  command has neither a commit nor a dashboard session to link to.
"""
from __future__ import annotations

import re
import secrets
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from .goal_ticket import _SOURCE_LABEL, normalize_repo

GqlFn = Callable[..., dict[str, Any]]

_SOURCE = "Telegram /linear/create"
_REPO_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

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
# Filtered by name, so a team with more than one page of labels still finds it.
_SOURCE_LABEL_BY_NAME = (
    "query SourceLabel($teamId: String!, $name: String!) { team(id: $teamId) { "
    "labels(filter: { name: { eq: $name } }, first: 5) { nodes { id name } } } }"
)
_LABEL_CREATE = """
mutation($input: IssueLabelCreateInput!) {
  issueLabelCreate(input: $input) { success issueLabel { id name } }
}
"""
_ISSUE_CREATE = """
mutation Create($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url title }
  }
}
"""

_locks: dict[tuple[str, str], list] = {}  # key -> [lock, holders]
_locks_guard = threading.Lock()


def _nodes(data: Any, *path: str) -> list:
    """`data[path...]["nodes"]` as a list, or 502: a missing list is not 'none'."""
    cur = data
    for key in (*path, "nodes"):
        cur = cur.get(key) if isinstance(cur, dict) else None
    if not isinstance(cur, list):
        raise HTTPException(502, f"Linear answer had no {'.'.join(path)} list; nothing created")
    return cur


def repo_name(repo: str) -> str:
    """`owner/name`, a GitHub URL or a bare `name` -> `name` ('' if unusable)."""
    slug = normalize_repo(repo)
    name = slug.split("/", 1)[1] if slug else (repo or "").strip()
    return name if _REPO_NAME_RE.match(name) else ""


def route_by_repo(gql: GqlFn, repo: str) -> dict[str, str]:
    """Pattern B: the one Linear project named exactly like the repo, in one team."""
    name = repo_name(repo)
    if not name:
        raise HTTPException(422, "repo must be a GitHub owner/name or a bare repository name; nothing created")
    nodes = _nodes(gql(_PROJECT_BY_NAME, {"name": name}), "projects")
    if any(not isinstance(p, dict) for p in nodes):
        raise HTTPException(502, "Linear returned a malformed project; nothing created")
    matches = [p for p in nodes if p.get("name") == name]
    if len(matches) != 1:
        raise HTTPException(
            422, f"need exactly one Linear project named {name!r}, found {len(matches)}; nothing created"
        )
    project = matches[0]
    if not project.get("id"):
        raise HTTPException(502, f"Linear project {name!r} came back without an id; nothing created")
    teams = _nodes(project, "teams")
    team_ids = [t.get("id") for t in teams if isinstance(t, dict) and t.get("id")]
    if len(teams) != 1 or len(team_ids) != 1:
        raise HTTPException(
            422, f"Linear project {name!r} must belong to exactly one team, found {len(teams)}; nothing created"
        )
    return {"teamId": team_ids[0], "projectId": project["id"]}


def find_open_issue(gql: GqlFn, team_id: str, title: str) -> dict[str, Any] | None:
    """Open issue with exactly this title in the team, or None. Fails closed."""
    nodes = _nodes(gql(_FIND_OPEN_BY_TITLE, {"teamId": team_id, "title": title}), "issues")
    if not nodes:
        return None
    node = nodes[0]
    if not isinstance(node, dict) or not node.get("id") or not node.get("identifier"):
        raise HTTPException(502, "Linear duplicate lookup returned a malformed issue; nothing created")
    return node


def source_label_id(gql: GqlFn, team_id: str) -> str:
    """Id of the team's `pi-dev:source` label; create it only after a clean miss."""
    nodes = _nodes(gql(_SOURCE_LABEL_BY_NAME, {"teamId": team_id, "name": _SOURCE_LABEL}), "team", "labels")
    for label in nodes:
        if isinstance(label, dict) and label.get("name") == _SOURCE_LABEL and label.get("id"):
            return str(label["id"])
    created = gql(_LABEL_CREATE, {"input": {"name": _SOURCE_LABEL, "teamId": team_id, "color": "#6B7280"}})
    label = ((created.get("issueLabelCreate") or {}).get("issueLabel")) or {}
    if not isinstance(label, dict) or label.get("name") != _SOURCE_LABEL or not label.get("id"):
        raise HTTPException(502, f"Linear did not create a {_SOURCE_LABEL!r} label; nothing created")
    return str(label["id"])


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


@contextmanager
def _serialised(team_id: str, title: str) -> Iterator[None]:
    """One look-up-and-create at a time per (team, title) in this process."""
    key = (team_id, title)
    with _locks_guard:
        entry = _locks.setdefault(key, [threading.Lock(), 0])
        entry[1] += 1
    try:
        with entry[0]:
            yield
    finally:
        with _locks_guard:
            entry[1] -= 1
            if entry[1] == 0:
                _locks.pop(key, None)


def _file_issue(gql: GqlFn, inp: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Send issueCreate; anything short of a real id + identifier is 502."""
    unsure = f"the issue may exist in Linear; search for run id {run_id} before retrying"
    try:
        result = gql(_ISSUE_CREATE, {"input": inp}).get("issueCreate") or {}
    except HTTPException as exc:
        raise HTTPException(502, f"Linear issueCreate failed ({exc.detail}); {unsure}") from exc
    if not result.get("success"):
        raise HTTPException(502, f"Linear issueCreate returned success=false (run id {run_id})")
    issue = result.get("issue")
    if not isinstance(issue, dict) or not issue.get("id") or not issue.get("identifier"):
        raise HTTPException(502, f"Linear reported success but returned no issue id/identifier; {unsure}")
    return _shape(issue, existing=False, run_id=run_id)


def create_or_reuse(
    gql: GqlFn,
    *,
    routing: dict,
    title: str,
    description: str | None,
    priority: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the open same-title issue, or file a labelled, footed new one."""
    team_id = routing["teamId"]
    with _serialised(team_id, title):
        found = find_open_issue(gql, team_id, title)
        if found:
            return _shape(found, existing=True, run_id=None)
        label_id = source_label_id(gql, team_id)
        when = now or datetime.now(timezone.utc)
        run_id = new_run_id(when)
        inp: dict[str, Any] = {
            "teamId": team_id,
            "title": title,
            "priority": priority,
            "labelIds": [label_id],
            "description": with_footer(description, run_id, when.date().isoformat()),
        }
        if routing.get("projectId"):
            inp["projectId"] = routing["projectId"]
        return _file_issue(gql, inp, run_id)
