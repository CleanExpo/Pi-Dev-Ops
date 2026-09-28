"""A failed mesh claim goes back in the queue, says why, and skips the node that failed it (RA-7802).

Before this, a failed claim closed its `mesh_work_claims` row and left the
Linear issue In Progress indefinitely. The self-claim query only offers
backlog/unstarted issues, and the reaper only touches claims still
claimed/working, so a failed ticket was never offered again and nothing said
why. On 28/09 RA-7794 and RA-7800 each sat like that until a person found them.

Now a failed claim:
  * returns its issue to the unstarted pool, exactly as a reaped or
    HARD_STOP-released claim already does (`_mark_issue_reaped`);
  * gets one Linear comment naming the node and a fixed-vocabulary error code,
    never free text: every free-text field tried carried secrets (UNI-2796);
  * is not offered back to the node that failed it for FAILED_SKIP_HOURS, so
    one broken node cannot loop on it. Every other node can take it at once.

Collaborators are passed at call time, as `mesh_reaper` does, so a test that
monkeypatches `mesh._sb` / `mesh._linear_graphql` still reaches the fake.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import mesh_fleet, mesh_run_record

log = logging.getLogger(__name__)

FAILED_SKIP_HOURS = float(os.environ.get("MESH_FAILED_SKIP_HOURS", "24"))


def claim_filter(linear_id: str, state: str, host: str | None, branch: str | None) -> str:
    """The PATCH filter for a claim update: the ticket's open claim, and only the
    caller's own. A report naming its host matches that machine's row alone, and a
    terminal report naming its branch matches only that run's row (or one whose
    branch was never stored). Without these, a stale `failed` from one node closed
    another node's live claim and put its ticket back in the queue."""
    q = f"mesh_work_claims?linear_id=eq.{urllib.parse.quote(linear_id)}&state=in.(claimed,working)"
    if host:
        q += f"&machine=eq.{urllib.parse.quote(host)}"
    if branch and state in ("done", "released", "failed"):
        q += f"&or=(branch.is.null,branch.eq.{urllib.parse.quote(branch)})"
    return q


def owns(row: dict, host: str | None) -> bool:
    """A report naming a host requeues only that machine's claim. A runner from
    before RA-7802 names none: its PATCH has already closed the row, so requeue
    as main always did, or the ticket strands In Progress with no claim."""
    return host is None or row.get("machine") == host


def after_terminal(state: str, linear_id: str, row: dict, error_code: str | None,
                   mark_reaped: Callable[[str], bool], graphql: Callable[[str], dict]) -> None:
    """Return a released or failed claim's issue to the pool; comment on a failure.
    Best-effort: a Linear failure here must never fail the claim update."""
    try:
        mark_reaped(linear_id)
        if state == "failed":
            _comment(graphql, linear_id, row.get("machine") or "a node", error_code)
    except Exception:  # noqa: BLE001
        log.warning("requeue: Linear follow-up failed for %s", linear_id, exc_info=True)


def _comment(graphql: Callable[[str], dict], linear_id: str, machine: str, error_code: str | None) -> None:
    code = error_code if error_code in mesh_run_record._ERROR_CODES else "failed"
    issue = (graphql(f'query{{issue(id:{json.dumps(linear_id)}){{id}}}}').get("issue") or {}).get("id")
    if not issue:
        return
    body = (f"Mesh run failed on {machine} ({code}). The ticket is back in the queue; "
            f"{machine} will not take it again for {FAILED_SKIP_HOURS:g}h.")
    graphql(f'mutation{{commentCreate(input:{{issueId:{json.dumps(issue)},body:{json.dumps(body)}}}){{success}}}}')


def failed_here(get: Callable[[str], "tuple[int, str]"], host: str,
                now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> set:
    """Tickets `host` failed within FAILED_SKIP_HOURS. An unreadable table skips nothing:
    claiming then behaves exactly as before, and the node's own breaker still applies."""
    since = (now() - timedelta(hours=FAILED_SKIP_HOURS)).isoformat()
    path = (f"mesh_work_claims?select=linear_id&state=eq.failed"
            f"&machine=eq.{urllib.parse.quote(host)}&released_at=gte.{urllib.parse.quote(since)}")
    try:
        rows, problem = mesh_fleet.read(get, path)
    except Exception:  # noqa: BLE001 — e.g. Supabase not configured
        return set()
    return set() if problem else {r["linear_id"] for r in rows if r.get("linear_id")}
