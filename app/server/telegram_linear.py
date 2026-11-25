"""Pi-Dev Linear contract for POST /api/telegram/linear/create (RA-8632).

Two choke points make the failure classes structural, not per call site:
- `_call` is the only way this module talks to Linear: ANY transport exception,
  of any type or status, becomes a 502.
- `_parse` (in `telegram_linear_models`) is the only way it reads a Linear
  answer. Each of the five answers (project lookup, open-issue lookup, label
  lookup, label create, issue create) has a strict pydantic model (StrictStr
  ids, `success: Literal[True]`, required id/identifier/url/title on issues);
  any validation error is a 502 and nothing is filed, and for issueCreate the
  502 names the run id. Nothing else reads the raw GraphQL dicts.
Routing is a typed `Routing`, built only from parsed models (Pattern B) or the
validated legacy config. Malformed Linear answers are always 502; only "no or
several matching projects, or not exactly one team" is 422. In-process locks
serialise look-up-then-create per (team id, title) and look-up-or-create of
the `pi-dev:source` label per team, so ONE worker files once and labels once.

Known limits, deliberately not implemented:
- Cross-worker races: requests on different workers or replicas can still both
  miss a lookup and file twice (issue or label); closing that needs a shared
  lock or an idempotency key Linear enforces.
- The Telegram bot does not send `repo` yet (bot out of scope), so Pattern B
  is reachable only from direct API calls.
- No `Pi-Dev Run ID` custom field: nothing in this repository sets it today.
- No `Source commit` or `Dashboard session` footer line: a Telegram command
  has neither.
"""
from __future__ import annotations

import re
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi import HTTPException

from .goal_ticket import _SOURCE_LABEL
from .telegram_linear_models import (
    NOTHING as _NOTHING,
    IssueCreateAnswer,
    LabelAnswer,
    LabelCreateAnswer,
    OpenIssueAnswer,
    ProjectAnswer,
    _ConfigRouting,
    _Issue,
    _parse,
)

GqlFn = Callable[..., Any]

_SOURCE = "Telegram /linear/create"

# Same filter as swarm/margot_tools._lookup_open_issue (that helper reads "lookup
# failed" as "no match"). Titles are re-checked exactly in code after the query.
_OPEN_STATES = 'state: { type: { in: ["triage","backlog","unstarted","started"] } }, '
_ISSUE_NODES = "title: { eq: $title } }, first: 50) { nodes { id identifier url title } } }"
_FIND_OPEN_BY_TITLE = (
    "query FindOpenByTitle($teamId: ID!, $title: String!) { issues(filter: { "
    "team: { id: { eq: $teamId } }, " + _OPEN_STATES + _ISSUE_NODES
)
# Routed to a project: a same-title issue in a sibling project is not a duplicate.
_FIND_OPEN_BY_TITLE_IN_PROJECT = (
    "query FindOpenByTitle($teamId: ID!, $projectId: ID!, $title: String!) { issues(filter: { "
    "team: { id: { eq: $teamId } }, project: { id: { eq: $projectId } }, " + _OPEN_STATES + _ISSUE_NODES
)
_PROJECT_BY_NAME = (
    "query ProjectByName($name: String!) { projects(filter: { name: { eq: $name } }, "
    "first: 50) { nodes { id name teams(first: 5) { nodes { id } } } } }"
)
# Filtered by name, so a team with more than one page of labels still finds it.
_SOURCE_LABEL_BY_NAME = (
    "query SourceLabel($teamId: String!, $name: String!) { team(id: $teamId) { "
    "labels(filter: { name: { eq: $name } }, first: 50) { nodes { id name } } } }"
)
_LABEL_CREATE = (
    "mutation($input: IssueLabelCreateInput!) { "
    "issueLabelCreate(input: $input) { success issueLabel { id name } } }"
)
_ISSUE_CREATE = (
    "mutation Create($input: IssueCreateInput!) { "
    "issueCreate(input: $input) { success issue { id identifier url title } } }"
)

# ── repository names ────────────────────────────────────────────────────────
_OWNER = r"[A-Za-z0-9][A-Za-z0-9-]{0,38}"
_NAME = r"[A-Za-z0-9._-]{1,100}"
_REPO_FORMS = (
    re.compile(rf"^https?://github\.com/{_OWNER}/(?P<name>{_NAME}?)(?:\.git)?/?$", re.IGNORECASE),
    re.compile(rf"^{_OWNER}/(?P<name>{_NAME})$"),
    re.compile(rf"^(?P<name>{_NAME})$"),
)


def repo_name(repo: str) -> str:
    """owner/name, https://github.com/owner/name or a bare name -> name; else ''."""
    text = repo.strip()
    for form in _REPO_FORMS:
        match = form.match(text)
        if match and match["name"] not in (".", ".."):
            return match["name"]
    return ""


def _call(gql: GqlFn, query: str, variables: dict[str, Any], consequence: str = _NOTHING) -> Any:
    """The one transport call site: every failure, of any type, is 502."""
    try:
        return gql(query, variables)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything the transport does
        detail = exc.detail if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
        raise HTTPException(502, f"Linear call failed ({detail}); {consequence}") from exc


# ── routing ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Routing:
    team_id: str
    project_id: str | None

    @classmethod
    def from_config(cls, routing: Any) -> Routing:
        """Wrap the legacy `_project_routing` dict; a bad one is 502."""
        parsed = _parse(_ConfigRouting, routing, "Linear routing config")
        return cls(team_id=parsed.teamId, project_id=parsed.projectId or None)


def route_by_repo(gql: GqlFn, repo: str) -> Routing:
    """Pattern B: the one Linear project named exactly like the repo, in one team."""
    name = repo_name(repo)
    if not name:
        raise HTTPException(422, f"repo must be a GitHub owner/name, github.com URL or bare name; {_NOTHING}")
    answer = _parse(ProjectAnswer, _call(gql, _PROJECT_BY_NAME, {"name": name}), "Linear project lookup")
    matches = [p for p in answer.projects.nodes if p.name == name]
    if len(matches) != 1:
        raise HTTPException(422, f"need exactly one Linear project named {name!r}, found {len(matches)}; {_NOTHING}")
    teams = matches[0].teams.nodes
    if len(teams) != 1:
        raise HTTPException(422, f"Linear project {name!r} needs exactly one team, found {len(teams)}; {_NOTHING}")
    return Routing(team_id=teams[0].id, project_id=matches[0].id)


# ── lookups ─────────────────────────────────────────────────────────────────
def find_open_issue(gql: GqlFn, team_id: str, title: str, project_id: str | None = None) -> _Issue | None:
    """Open issue with exactly this title in the project (else the team), or None. Fails closed."""
    if project_id:
        data = _call(gql, _FIND_OPEN_BY_TITLE_IN_PROJECT, {"teamId": team_id, "projectId": project_id, "title": title})
    else:
        data = _call(gql, _FIND_OPEN_BY_TITLE, {"teamId": team_id, "title": title})
    answer = _parse(OpenIssueAnswer, data, "Linear duplicate lookup")
    return next((i for i in answer.issues.nodes if i.title == title), None)


def source_label_id(gql: GqlFn, team_id: str) -> str:
    """Id of the team's `pi-dev:source` label; create it only after a clean miss."""
    with _serialised(("label", team_id)):
        data = _call(gql, _SOURCE_LABEL_BY_NAME, {"teamId": team_id, "name": _SOURCE_LABEL})
        answer = _parse(LabelAnswer, data, "Linear label lookup")
        found = next((lb for lb in answer.team.labels.nodes if lb.name == _SOURCE_LABEL), None)
        if found:
            return found.id
        new = {"input": {"name": _SOURCE_LABEL, "teamId": team_id, "color": "#6B7280"}}
        created = _parse(LabelCreateAnswer, _call(gql, _LABEL_CREATE, new), "Linear label create")
        if created.issueLabelCreate.issueLabel.name != _SOURCE_LABEL:
            raise HTTPException(502, f"Linear created a label not named {_SOURCE_LABEL!r}; {_NOTHING}")
        return created.issueLabelCreate.issueLabel.id


# ── locks ───────────────────────────────────────────────────────────────────
_locks: dict[tuple[str, ...], list] = {}  # key -> [lock, holders]
_locks_guard = threading.Lock()


@contextmanager
def _serialised(key: tuple[str, ...]) -> Iterator[None]:
    """One holder at a time per key in this process; entries are dropped when idle."""
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


# ── filing ──────────────────────────────────────────────────────────────────
def new_run_id(now: datetime) -> str:
    return f"telegram-{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"


def with_footer(description: str | None, run_id: str, filed: str) -> str:
    footer = f"---\n**Pi-Dev-Ops run**\n- Run ID: `{run_id}`\n- Source: {_SOURCE}\n- Filed: {filed}"
    body = (description or "").rstrip()
    return f"{body}\n\n{footer}" if body else footer


def _shape(issue: _Issue, *, existing: bool, run_id: str | None) -> dict[str, Any]:
    return {**issue.model_dump(), "existing": existing, "run_id": run_id}


def _file_issue(gql: GqlFn, inp: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Send issueCreate; anything short of a complete issue is 502 naming the run id."""
    unsure = f"the issue may exist in Linear; search for run id {run_id} before retrying"
    data = _call(gql, _ISSUE_CREATE, {"input": inp}, unsure)
    created = _parse(IssueCreateAnswer, data, "Linear issueCreate answer", unsure)
    return _shape(created.issueCreate.issue, existing=False, run_id=run_id)


def create_or_reuse(gql: GqlFn, *, routing: Routing, title: str, description: str | None,
                    priority: int, now: datetime | None = None) -> dict[str, Any]:
    """Return the open same-title issue, or file a labelled, footed new one."""
    with _serialised(("issue", routing.team_id, title)):
        found = find_open_issue(gql, routing.team_id, title, routing.project_id)
        if found:
            return _shape(found, existing=True, run_id=None)
        label_id = source_label_id(gql, routing.team_id)
        when = now or datetime.now(timezone.utc)
        run_id = new_run_id(when)
        inp: dict[str, Any] = {"teamId": routing.team_id, "title": title, "priority": priority, "labelIds": [label_id],
                               "description": with_footer(description, run_id, when.date().isoformat())}
        if routing.project_id:
            inp["projectId"] = routing.project_id
        return _file_issue(gql, inp, run_id)
