"""swarm/portfolio_pulse_linear.py — RA-1890 (child of RA-1409).

Linear-movement section provider for the daily Portfolio Pulse. Plugs
into the foundation (RA-1888) via ``portfolio_pulse.set_section_provider``.

For each project, queries Linear for movement in the last 24h:
  * Tickets opened (count + top 3 by priority)
  * Tickets closed (count + Done/Cancelled/Duplicate split)
  * Currently blocked (`Pi-Dev: Blocked` state OR labels matching
    `pi-dev:blocked-reason:*`)
  * Stale tickets (open ≥ 14 days no update)

Project → Linear project_id mapping comes from `.harness/projects.json`.

The provider is registered at module import time, so any caller that
imports this module (or `swarm.portfolio_pulse_sections`) gets the
upgraded section. Foundation's placeholder is replaced.

Failure modes (graceful):
  * No LINEAR_API_KEY → returns "_(linear: no API key)_" body
  * project_id not in projects.json → returns
    "_(linear: project_id 'xxx' not in .harness/projects.json)_"
  * Network error / GraphQL error → returns the error string in body
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import portfolio_pulse

# linear_tools is imported lazily inside _fetch_movement / linear_section_provider
# because it triggers flow_engine.register_with_flow_engine() at module load,
# which transitively imports swarm.draft_review. Eager import would pollute
# sys.modules before tests can monkeypatch draft_review.

log = logging.getLogger("swarm.portfolio_pulse.linear")

REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_JSON_REL = ".harness/projects.json"

# 24h window matches the daily-pulse cadence.
DEFAULT_LOOKBACK_HOURS = 24
# Stale threshold for "open ≥N days no update".
STALE_DAYS = 14
# How many top-priority opens / first-stale to surface in markdown.
TOP_OPENED_COUNT = 3
TOP_STALE_COUNT = 3


# ── Project lookup ──────────────────────────────────────────────────────────


def _load_projects(repo_root: Path) -> dict[str, dict[str, Any]]:
    """Load .harness/projects.json keyed by project id."""
    p = repo_root / PROJECTS_JSON_REL
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("portfolio_pulse_linear: projects.json parse failed: %s", exc)
        return {}
    out: dict[str, dict[str, Any]] = {}
    for proj in data.get("projects", []):
        pid = proj.get("id")
        if pid:
            out[pid] = proj
    return out


# ── GraphQL ─────────────────────────────────────────────────────────────────


_MOVEMENT_QUERY = """
query($projectId: String!, $since: DateTimeOrDuration!, $first: Int!) {
  opened: issues(
    first: $first,
    filter: {
      project: { id: { eq: $projectId } },
      createdAt: { gt: $since }
    },
    orderBy: createdAt
  ) {
    nodes {
      id identifier title priority state { name }
    }
  }
  closed: issues(
    first: $first,
    filter: {
      project: { id: { eq: $projectId } },
      completedAt: { gt: $since }
    },
    orderBy: updatedAt
  ) {
    nodes {
      id identifier title state { name type }
    }
  }
  blocked: issues(
    first: $first,
    filter: {
      project: { id: { eq: $projectId } },
      state: { type: { in: [started, unstarted, backlog] } },
      labels: { name: { startsWith: "pi-dev:blocked-reason:" } }
    },
    orderBy: updatedAt
  ) {
    nodes {
      id identifier title state { name } labels { nodes { name } }
    }
  }
  stale: issues(
    first: $first,
    filter: {
      project: { id: { eq: $projectId } },
      state: { type: { in: [started, unstarted, backlog] } },
      updatedAt: { lt: $stale_before }
    },
    orderBy: updatedAt
  ) {
    nodes {
      id identifier title updatedAt priority
    }
  }
}
"""

# Linear's `DateTimeOrDuration` accepts ISO-8601 OR a duration string
# like "-P1D". We use absolute ISO strings to be unambiguous.


# ── Movement query ──────────────────────────────────────────────────────────


def _fetch_movement(linear_project_id: str,
                      *, lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
                      first: int = 50,
                      ) -> dict[str, Any]:
    """Fetch one project's 24h Linear movement. Returns dict shape:

        {opened: [...], closed: [...], blocked: [...], stale: [...]}

    On error returns {"error": "..."}.
    """
    from . import linear_tools  # noqa: PLC0415 — lazy import (see header)

    now = datetime.now(timezone.utc)
    since_iso = (now - timedelta(hours=lookback_hours)).isoformat()
    stale_before_iso = (now - timedelta(days=STALE_DAYS)).isoformat()

    # The query accepts $since and $stale_before separately. Since Linear's
    # GraphQL spec requires one variable per use, we declare both upfront.
    query = _MOVEMENT_QUERY.replace(
        "($projectId: String!, $since: DateTimeOrDuration!, $first: Int!)",
        "($projectId: String!, $since: DateTimeOrDuration!, "
        "$first: Int!, $stale_before: DateTimeOrDuration!)",
    )

    res = linear_tools._gql(query, {
        "projectId": linear_project_id,
        "since": since_iso,
        "first": first,
        "stale_before": stale_before_iso,
    })
    if "error" in res:
        return {"error": res.get("error", "unknown"),
                 "details": res.get("exception")}
    data = res.get("data") or {}
    return {
        "opened": (data.get("opened") or {}).get("nodes") or [],
        "closed": (data.get("closed") or {}).get("nodes") or [],
        "blocked": (data.get("blocked") or {}).get("nodes") or [],
        "stale": (data.get("stale") or {}).get("nodes") or [],
    }


# ── Markdown rendering ──────────────────────────────────────────────────────


_PRIORITY_LABEL = {
    1: "Urgent", 2: "High", 3: "Medium", 4: "Low", 0: "—",
}


def _format_priority(p: int | None) -> str:
    if p is None:
        return "—"
    return _PRIORITY_LABEL.get(int(p), str(p))


def _state_type(node: dict[str, Any]) -> str:
    s = node.get("state") or {}
    return (s.get("type") or "").lower()


def _classify_closed(closed: list[dict[str, Any]]
                      ) -> dict[str, list[dict[str, Any]]]:
    """Split closed nodes by state.type → completed / canceled."""
    out: dict[str, list[dict[str, Any]]] = {"done": [], "canceled": []}
    for n in closed:
        if _state_type(n) == "completed":
            out["done"].append(n)
        else:
            # "canceled" type covers both Canceled and Duplicate states
            out["canceled"].append(n)
    return out


def _render_section(movement: dict[str, Any]) -> str:
    """Build the markdown body for one project's Linear movement."""
    if "error" in movement:
        return f"_(linear: {movement['error']})_"

    opened = movement.get("opened", [])
    closed = movement.get("closed", [])
    blocked = movement.get("blocked", [])
    stale = movement.get("stale", [])

    closed_split = _classify_closed(closed)

    lines: list[str] = []
    lines.append(f"- **Opened (last 24h):** {len(opened)}")
    if opened:
        # Show top by priority: lower priority value = higher (Urgent=1)
        ranked = sorted(
            opened,
            key=lambda n: (n.get("priority") or 99),
        )[:TOP_OPENED_COUNT]
        for n in ranked:
            pri = _format_priority(n.get("priority"))
            lines.append(f"    - `{n['identifier']}` [{pri}] {n.get('title', '')[:80]}")

    lines.append(
        f"- **Closed (last 24h):** {len(closed)} "
        f"(Done {len(closed_split['done'])} · "
        f"Canceled/Duplicate {len(closed_split['canceled'])})"
    )

    lines.append(f"- **Currently blocked:** {len(blocked)}")
    if blocked:
        for n in blocked[:3]:
            label_names = [
                lab.get("name", "") for lab in
                ((n.get("labels") or {}).get("nodes") or [])
            ]
            blocked_reason = next(
                (lab for lab in label_names
                  if lab.startswith("pi-dev:blocked-reason:")),
                "(unknown reason)",
            )
            lines.append(
                f"    - `{n['identifier']}` {blocked_reason} — "
                f"{n.get('title', '')[:80]}",
            )

    lines.append(f"- **Stale (open ≥{STALE_DAYS}d no update):** {len(stale)}")
    if stale:
        for n in stale[:TOP_STALE_COUNT]:
            pri = _format_priority(n.get("priority"))
            updated = (n.get("updatedAt") or "")[:10]
            lines.append(
                f"    - `{n['identifier']}` [{pri}] "
                f"last updated {updated} — {n.get('title', '')[:70]}",
            )

    return "\n".join(lines)


# ── Provider ────────────────────────────────────────────────────────────────


def linear_section_provider(project_id: str,
                              repo_root: Path) -> tuple[str, str | None]:
    """Section provider — registered at module import."""
    # Read env directly rather than via linear_tools._api_key(), so the
    # graceful-fallback paths (no key / missing project) don't trigger
    # the linear_tools import chain that pulls in flow_engine + draft_review.
    # That eager registration breaks test isolation for swarm.draft_review
    # monkeypatching elsewhere in the test suite.
    import os as _os  # noqa: PLC0415
    if not (_os.environ.get("LINEAR_API_KEY") or "").strip():
        return "_(linear: no API key)_", "no_api_key"

    projects = _load_projects(repo_root)
    proj = projects.get(project_id)
    if proj is None:
        return (
            f"_(linear: project_id {project_id!r} not in "
            ".harness/projects.json — add a `linear_project_id` mapping)_",
            "missing_projects_json_entry",
        )

    linear_project_id = proj.get("linear_project_id")
    if not linear_project_id:
        return (
            f"_(linear: project {project_id!r} has no linear_project_id "
            "in .harness/projects.json)_",
            "no_linear_project_id",
        )

    movement = _fetch_movement(linear_project_id)
    return _render_section(movement), movement.get("error")


def register() -> None:
    """Idempotent registration. Called at module import."""
    portfolio_pulse.set_section_provider("linear_movement",
                                           linear_section_provider)


# Self-register on import — sibling-child plug-point convention.
register()


__all__ = [
    "linear_section_provider", "register",
    "DEFAULT_LOOKBACK_HOURS", "STALE_DAYS",
    "TOP_OPENED_COUNT", "TOP_STALE_COUNT",
]
