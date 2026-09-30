"""Claimable-queue eligibility — one function for poller and dashboard.

UNI-2648: Mission Control used to list every unstarted Urgent/High ticket in
the workspace. The autonomy poller claims only Ready-for-Pi-Dev tickets that
carry an autonomy label, sit in the harness project registry, and (when
configured) match the priority-label filter. Those four axes live here so the
displayed queue and the claimable queue cannot drift.

W1b (estate audit 30/09 ranks #1 and #5): every executor — the Railway poller,
the mesh self-claim and dispatcher, and swarm intake — admits work through
`issue_is_claimable`, which also applies `claim_refusal`: a ticket with an open
blocker, a Blocked transition in the last 24h, or two session starts in the
last 24h is not claimable. One ticket was claimed 14 times in a day without it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Set
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

READY_STATUS_NAME = "Ready for Pi-Dev"
TODO_STATUS_NAME = "Todo"
BLOCKED_STATUS_NAME = "Pi-Dev: Blocked"
AUTONOMY_LABEL = "pi-dev:autonomous"
MACHINE_SHIP_LABEL = "pi-dev:machine-ship"
CLAIMABLE_LABELS = frozenset({AUTONOMY_LABEL, MACHINE_SHIP_LABEL})
POLLER_STATES = frozenset({READY_STATUS_NAME})
# The mesh build lane also takes approved Todo work (16 pi-dev:autonomous Todo
# tickets sat unreachable on 30/09 because only Ready was ever read).
MESH_STATES = frozenset({READY_STATUS_NAME, TODO_STATUS_NAME})
BLOCKED_REASON_PREFIX = "pi-dev:blocked-reason:"
REPEAT_CLAIM_LABEL = BLOCKED_REASON_PREFIX + "repeat-claim"
# The poller's own start comment ("Pi-CEO autonomous session started").
SESSION_STARTED_MARKER = "autonomous session started"
MAX_STARTS_PER_WINDOW = 2  # the third start inside the window is refused
GUARD_WINDOW = timedelta(hours=24)
_CLOSED_STATE_TYPES = frozenset({"completed", "canceled"})

# Every executor's issue query selects these so claim_refusal can see them.
# `inverseRelations` of type "blocks" are the issues blocking this one.
GUARD_FIELDS = (
    "project { id } "
    "inverseRelations(first: 20) { nodes { type issue { identifier state { type } } } } "
    "history(first: 20) { nodes { createdAt toState { name } } } "
    "comments(first: 50) { nodes { body createdAt } }"
)


def _nodes(issue: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    conn = issue.get(key)
    nodes = (conn or {}).get("nodes") if isinstance(conn, Mapping) else None
    return [n for n in nodes or [] if isinstance(n, Mapping)]


def _at(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _recent(value: Any, now: datetime) -> bool:
    ts = _at(value)
    return ts is not None and now - ts < GUARD_WINDOW


def open_blockers(issue: Mapping[str, Any]) -> list[str]:
    """Identifiers of issues that block this one and are not yet closed."""
    return [
        str((rel.get("issue") or {}).get("identifier") or "?")
        for rel in _nodes(issue, "inverseRelations")
        if rel.get("type") == "blocks"
        and ((rel.get("issue") or {}).get("state") or {}).get("type") not in _CLOSED_STATE_TYPES
    ]


def recent_session_starts(issue: Mapping[str, Any], now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    return sum(
        1 for c in _nodes(issue, "comments")
        if SESSION_STARTED_MARKER in str(c.get("body") or "").lower()
        and _recent(c.get("createdAt"), now)
    )


def claim_refusal(issue: Mapping[str, Any], now: datetime | None = None) -> str | None:
    """Why no executor may claim this issue now, or None when nothing forbids it.

    Reasons: ``blocked-reason`` (a pi-dev:blocked-reason:* label — a human must
    clear it, because teams without a Blocked state park failures in Todo, which
    the mesh lane reads), ``blocked-by`` (an open blockedBy relation),
    ``recently-blocked`` (moved to Pi-Dev: Blocked within 24h), ``repeat-claim``
    (already started twice within 24h). Fields a query did not select count as absent.
    """
    now = now or datetime.now(timezone.utc)
    if any(name.startswith(BLOCKED_REASON_PREFIX) for name in issue_label_names(issue)):
        return "blocked-reason"
    if open_blockers(issue):
        return "blocked-by"
    if any(
        ((h.get("toState") or {}).get("name") or "") == BLOCKED_STATUS_NAME
        and _recent(h.get("createdAt"), now)
        for h in _nodes(issue, "history")
    ):
        return "recently-blocked"
    if recent_session_starts(issue, now) >= MAX_STARTS_PER_WINDOW:
        return "repeat-claim"
    return None


def registry_repos(path: Path | None = None) -> dict[str, str]:
    """Linear project id -> GitHub repo from config/harness/projects.json.

    First row wins, so a project sharing a repo resolves as the registry orders it.
    """
    if path is None:
        from app.server import config_loader  # noqa: PLC0415 — keep this module import-light
        path = config_loader.PROJECTS_JSON
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in registry.get("projects", []):
        pid, repo = row.get("linear_project_id"), row.get("repo")
        if pid and repo and pid not in out:
            out[str(pid)] = str(repo)
    return out


def issue_label_names(issue: Mapping[str, Any]) -> frozenset[str]:
    nodes = (issue.get("labels") or {}).get("nodes") or []
    return frozenset(
        str(node.get("name") or "")
        for node in nodes
        if isinstance(node, Mapping)
    )


def issue_project_id(issue: Mapping[str, Any]) -> str | None:
    project = issue.get("project")
    if isinstance(project, Mapping) and project.get("id"):
        return str(project["id"])
    annotated = issue.get("_project_id")
    if annotated:
        return str(annotated)
    return None


def issue_is_claimable(
    issue: Mapping[str, Any],
    *,
    registered_project_ids: Set[str],
    priority_labels: Set[str] | None = None,
    states: Set[str] = POLLER_STATES,
    now: datetime | None = None,
) -> bool:
    """True when the issue is on the autonomy claimable queue.

    Axes (all required):
    1. State *name* is in ``states`` (Ready for Pi-Dev) — not state.type == unstarted
    2. Label pi-dev:autonomous or pi-dev:machine-ship
    3. Project id is in config/harness/projects.json
    4. When priority_labels is non-empty, one of those labels is present
    5. ``claim_refusal`` finds nothing (no open blocker, recent Blocked, repeat claim)
    """
    state = issue.get("state") if isinstance(issue.get("state"), Mapping) else {}
    if (state.get("name") or "") not in states:
        return False
    labels = issue_label_names(issue)
    if labels.isdisjoint(CLAIMABLE_LABELS):
        return False
    project_id = issue_project_id(issue)
    if not project_id or project_id not in registered_project_ids:
        return False
    wanted = priority_labels or frozenset()
    if wanted and labels.isdisjoint(wanted):
        return False
    return claim_refusal(issue, now) is None


def filter_claimable_issues(
    issues: Iterable[Mapping[str, Any]],
    *,
    registered_project_ids: Set[str],
    priority_labels: Set[str] | None = None,
) -> list[dict[str, Any]]:
    return [
        issue if isinstance(issue, dict) else dict(issue)
        for issue in issues
        if issue_is_claimable(
            issue,
            registered_project_ids=registered_project_ids,
            priority_labels=priority_labels,
        )
    ]


def queue_snapshot_from_issues(issues: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(issues)
    nxt = rows[0] if rows else {}
    return {
        "urgent": sum(1 for issue in rows if issue.get("priority") == 1),
        "high": sum(1 for issue in rows if issue.get("priority") == 2),
        "next_issue_id": nxt.get("identifier") or None,
        "next_issue_title": (nxt.get("title") or "")[:80],
    }
