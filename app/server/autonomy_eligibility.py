"""Claimable-queue eligibility — one function for poller and dashboard.

UNI-2648: Mission Control used to list every unstarted Urgent/High ticket in
the workspace. The autonomy poller claims only Ready-for-Pi-Dev tickets that
carry an autonomy label, sit in the harness project registry, and (when
configured) match the priority-label filter. Those four axes live here so the
displayed queue and the claimable queue cannot drift.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set
from typing import Any

READY_STATUS_NAME = "Ready for Pi-Dev"
AUTONOMY_LABEL = "pi-dev:autonomous"
MACHINE_SHIP_LABEL = "pi-dev:machine-ship"
CLAIMABLE_LABELS = frozenset({AUTONOMY_LABEL, MACHINE_SHIP_LABEL})


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
) -> bool:
    """True when the issue is on the autonomy claimable queue.

    Axes (all required):
    1. State *name* is Ready for Pi-Dev — not state.type == unstarted
    2. Label pi-dev:autonomous or pi-dev:machine-ship
    3. Project id is in config/harness/projects.json
    4. When priority_labels is non-empty, one of those labels is present
    """
    state = issue.get("state") if isinstance(issue.get("state"), Mapping) else {}
    if (state.get("name") or "") != READY_STATUS_NAME:
        return False
    labels = issue_label_names(issue)
    if labels.isdisjoint(CLAIMABLE_LABELS):
        return False
    project_id = issue_project_id(issue)
    if not project_id or project_id not in registered_project_ids:
        return False
    wanted = priority_labels or frozenset()
    return not wanted or not labels.isdisjoint(wanted)


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
