"""RA-8100 read-only delivery collector: Linear missions, GitHub PR facts, Vercel, own revision.

Read-only by construction. GitHub only through ``ticket_sweeper_io.github_get``, Vercel
only through ``vercel_monitor._vercel_get``, Linear only through ``read_only_gql``, which
refuses any document that is not exactly one ``query`` operation before any request.
``CleanExpo/CCW-CRM`` is skipped on repo, any case, before any request (R2-9). Every
read is counted against the per-tick budgets (section 11). Failures raise ``Unknown``
or ``MissingCommit`` carrying a reason code only, never upstream text or a token.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import autonomy, autonomy_linear_rate, config_loader, vercel_monitor
from .delivery_collect_fields import (
    LINEAR_STATE_TYPES, VERCEL_STATES, flag, linear_identifier, maybe, member, node_id, positive_int, sha,
    text,
)

log = logging.getLogger("pi-ceo.delivery_reconcile")

SKIP_REPOS = frozenset({"cleanexpo/ccw-crm"})
BUDGETS = {"github": 200, "linear": 80, "vercel": 4}
READ_SECONDS = 90.0
_MAX_PAGES = 20
_REPO = re.compile(r"[\w.-]+/[\w.-]+")
_ID = re.compile(r"[\w-]+")
_LEX = re.compile(r'[ \t\n\r,﻿]+|#[^\n\r]*|"""(?:\\"""|(?!""")[\s\S])*"""|"(?:\\[^\n\r]|[^"\\\n\r])*"'
                  r"|\.\.\.|[{}()\[\]:=@!$|&]|[_A-Za-z][_0-9A-Za-z]*|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")
_PAIRS = {"}": "{", ")": "(", "]": "["}


class Unknown(Exception):
    """Evidence did not arrive whole; ``reason`` is a short code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class MissingCommit(Unknown):
    """The head or merge commit cannot be read (spec row 4)."""


class BudgetExhausted(Unknown):
    """A per-tick budget or the 90 s read clock is spent; no request was made."""


class RegistryError(Exception):
    """The registry could not be read whole; nothing falls back."""


class ReadOnlyViolation(ValueError):
    """The GraphQL document is not exactly one ``query`` operation."""


@dataclass
class Tick:
    """Per-tick read context: in-scope repos (lower case), budgets and the read clock."""

    allowed: frozenset[str] = frozenset()
    clock: Callable[[], float] = time.monotonic
    left: dict[str, int] = field(default_factory=lambda: dict(BUDGETS))
    started: float | None = None

    def __post_init__(self) -> None:
        self.started = self.clock() if self.started is None else self.started

    def spend(self, kind: str) -> None:
        """Count one request, or raise before it is made."""
        if self.clock() - self.started > READ_SECONDS:
            raise BudgetExhausted("clock")
        if self.left[kind] <= 0:
            raise BudgetExhausted(f"budget_{kind}")
        self.left[kind] -= 1


@dataclass
class MissionRead:
    issues: list[dict]
    complete: bool
    reason: str | None = None


@dataclass(frozen=True)
class Registry:
    entries: tuple[dict, ...]
    queryable: tuple[dict, ...]
    unqueryable_projects: tuple[str, ...]
    allowed: frozenset[str]
    swept: tuple[str, ...]
    skipped_repos: tuple[str, ...]


def _skipped(repo: object) -> bool:
    return isinstance(repo, str) and repo.lower() in SKIP_REPOS


def _check_read_only(query: object) -> None:
    """Allow exactly: ``query`` [name] [variables] [directives] ``{...}`` and nothing after."""
    if not isinstance(query, str):
        raise ReadOnlyViolation("not_text")
    tokens, pos = [], 0
    while pos < len(query):
        match = _LEX.match(query, pos)
        if match is None:
            raise ReadOnlyViolation("unlexable")
        pos = match.end()
        if match.group()[0] not in " \t\n\r,﻿#":
            tokens.append(match.group())
    if not tokens or tokens[0] != "query":
        raise ReadOnlyViolation("not_a_query")
    stack: list[str] = []
    done = False
    for tok in tokens[1:]:
        if done:
            raise ReadOnlyViolation("more_than_one_definition")
        if tok in ("{", "(", "["):
            stack.append(tok)
        elif tok in _PAIRS:
            if not stack or stack.pop() != _PAIRS[tok]:
                raise ReadOnlyViolation("unbalanced")
            done = tok == "}" and not stack
    if not done:
        raise ReadOnlyViolation("unbalanced")


def read_only_gql(api_key: str, query: str, variables: dict | None, *, tick: Tick) -> dict:
    """One Linear read. Refuses any non-query document before any network call."""
    try:
        _check_read_only(query)
    except ReadOnlyViolation as exc:
        log.warning("delivery_collect: refused a GraphQL document (%s)", exc)
        raise
    tick.spend("linear")
    return autonomy._gql(api_key, query, variables or {})


def load_registry(path: str | None = None) -> Registry:
    """Strict read of projects.json; any unreadable or malformed entry raises."""
    try:
        data = json.loads(Path(path or config_loader.PROJECTS_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"registry_unreadable_{type(exc).__name__}") from None
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, list) or not projects:
        raise RegistryError("registry_malformed")
    for entry in projects:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) \
                or not isinstance(entry.get("repo"), str) or not _REPO.fullmatch(entry["repo"]):
            raise RegistryError("registry_malformed")
    entries = tuple(e for e in projects if not _skipped(e["repo"]))
    queryable = tuple(e for e in entries if e.get("linear_project_id") and e.get("linear_team_id"))
    swept: list[str] = []
    for entry in queryable:
        if entry["repo"].lower() not in {s.lower() for s in swept}:
            swept.append(entry["repo"])
    return Registry(
        entries=entries, queryable=queryable,
        unqueryable_projects=tuple(e["id"] for e in entries if e not in queryable),
        allowed=frozenset(e["repo"].lower() for e in entries), swept=tuple(swept),
        skipped_repos=tuple(sorted({e["repo"] for e in projects if _skipped(e["repo"])})))


_MISSIONS_QUERY = """
query DeliveryMissions($projectId: String!, $since: DateTimeOrDuration!, $cursor: String) {
    project(id: $projectId) {
        issues(filter: { or: [
            { state: { type: { eq: "started" } } }
            { completedAt: { gt: $since } }
        ] }, first: 50, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes {
                id identifier startedAt completedAt createdAt description
                state { type } assignee { name }
                attachments(first: 100) { pageInfo { hasNextPage } nodes { url } }
            }
        }
    }
}
"""


def _node_ok(node: object) -> bool:
    """The issue fields a consumer reads are in their domain; a null assignee means unowned. ``startedAt`` and
    ``completedAt`` are judged per mission by the classifier (spec row 1: bad timestamp is that mission's UNKNOWN)."""
    if not isinstance(node, dict) or not node_id(node.get("id")) or not linear_identifier(node.get("identifier")):
        return False
    state, assignee = node.get("state"), node.get("assignee")
    return isinstance(state, dict) and member(state.get("type"), LINEAR_STATE_TYPES) \
        and (assignee is None or (isinstance(assignee, dict) and maybe(assignee.get("name"), text)))


def _issue_page(data: object) -> tuple[list[dict], str | None] | None:
    """(nodes, next cursor or None), or None when the page or any node in it is malformed."""
    project = data.get("project") if isinstance(data, dict) else None
    conn = project.get("issues") if isinstance(project, dict) else None
    page = conn.get("pageInfo") if isinstance(conn, dict) else None
    nodes = conn.get("nodes") if isinstance(page, dict) else None
    if not isinstance(nodes, list) or not flag(page.get("hasNextPage")) or not all(_node_ok(n) for n in nodes):
        return None
    cursor = page.get("endCursor") if page["hasNextPage"] else None
    if page["hasNextPage"] and not text(cursor):
        return None
    return nodes, cursor


def fetch_missions(api_key: str, entry: dict, *, tick: Tick, since: str) -> MissionRead:
    """Every mission page for one entry; stops at the first error, cooldown or budget, no retry."""
    if _skipped(entry.get("repo")) or not entry.get("linear_project_id"):
        raise Unknown("not_queryable")
    issues: list[dict] = []
    seen: set[str] = set()
    cursor = None
    for _ in range(_MAX_PAGES):
        if autonomy_linear_rate.linear_rate_limited():
            return MissionRead(issues, False, "linear_rate_limited")
        variables = {"projectId": entry["linear_project_id"], "since": since, "cursor": cursor}
        try:
            page = _issue_page(read_only_gql(api_key, _MISSIONS_QUERY, variables, tick=tick))
        except BudgetExhausted as exc:
            return MissionRead(issues, False, exc.reason)
        except Exception as exc:  # noqa: BLE001 — recorded by type name only
            return MissionRead(issues, False, f"error_{type(exc).__name__}")
        if page is None:
            return MissionRead(issues, False, "malformed_page")
        idents = [n["identifier"] for n in page[0]]
        if len(set(idents)) < len(idents) or seen.intersection(idents):
            return MissionRead(issues, False, "duplicate_issue")  # a shifted page may have skipped one
        seen.update(idents)
        issues.extend(page[0])
        cursor = page[1]
        if cursor is None:
            return MissionRead(issues, True)
    return MissionRead(issues, False, "too_many_pages")


def in_scope(refs: list[tuple[str, int]], allowed: frozenset[str] | set[str]) -> tuple[list[tuple[str, int]], int]:
    """Keep refs to in-scope repos; count the rest without recording them (R2-3).
    One malformed ref fails the whole list (``malformed_ref``); nothing is filtered silently."""
    if not isinstance(refs, list) or not all(
            isinstance(r, tuple) and len(r) == 2 and isinstance(r[0], str) and _REPO.fullmatch(r[0])
            and positive_int(r[1]) for r in refs):
        raise Unknown("malformed_ref")
    wanted = {a.lower() for a in allowed} - SKIP_REPOS
    kept = [(repo, n) for repo, n in refs if repo.lower() in wanted]
    return kept, len(refs) - len(kept)


def vercel_latest_ready(entry: dict, *, tick: Tick) -> str | None:
    """The newest READY production deployment's 40-hex commit SHA, else None.
    Recorded as ``live_unconfirmed`` only; it never proves what is serving (R2-8)."""
    project, team = entry.get("vercel_project_id"), entry.get("vercel_team_id")
    if _skipped(entry.get("repo")) or not isinstance(project, str) or not _ID.fullmatch(project):
        return None
    query = f"projectId={project}&target=production&state=READY&limit=5"
    if isinstance(team, str) and _ID.fullmatch(team):
        query += f"&teamId={team}"
    tick.spend("vercel")
    try:
        data = vercel_monitor._vercel_get(f"/v6/deployments?{query}")
    except Exception as exc:  # noqa: BLE001 — recorded by type name only
        raise Unknown(f"vercel_error_{type(exc).__name__}") from None
    deployments = data.get("deployments") if isinstance(data, dict) else None
    if not isinstance(deployments, list):
        raise Unknown("malformed_deployments")
    if not all(isinstance(d, dict) and member(d.get("state"), VERCEL_STATES) for d in deployments):
        raise Unknown("malformed_deployments")
    ready = [d for d in deployments if d["state"] == "READY"]  # another known state: a business skip
    if not all(positive_int(d.get("created")) for d in ready):
        raise Unknown("malformed_deployments")
    if not ready:
        return None
    meta = max(ready, key=lambda d: d["created"]).get("meta")
    value = meta.get("githubCommitSha") if isinstance(meta, dict) else None
    if not isinstance(meta, (dict, type(None))) or not maybe(value, sha):
        raise Unknown("malformed_deployments")
    return sha(value)  # None: no commit SHA, not built from a commit


def own_revision() -> str | None:
    """This service's running revision, 40 hex only (same rule as health_evidence.py:9-10)."""
    revision = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("BUILD_REVISION", "")
    return sha(revision)
