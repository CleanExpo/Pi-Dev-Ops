"""app/server/discovery_archive.py — RA-2027 Linear archive cron handler.

Operator decision 2026-05-06: auto-close Discovery-loop tickets at
sev 4-5 (Linear priority 3-4 — Medium / Low) that have been unactioned
for >7 days. Tickets at sev≥6 (priority 1-2 — Urgent / High) NEVER
auto-close — those need a human read.

Definition of "unactioned":
  No comments, no state changes (still in Backlog/Todo), no label
  changes since the ticket was created. Linear surfaces all of these
  via `updatedAt` — if `updatedAt` equals `createdAt` (within tolerance)
  AND the ticket is unchanged from its initial state, it's unactioned.

Why this is a prerequisite for live Discovery:
  At ~196 findings/day × 7 boards × 30 days = ~6000 tickets/month
  before pruning. Without this archive, Linear quotas exhaust and the
  triage signal-to-noise collapses.

Public API:
    archive_stale_discovery_tickets() -> ArchiveReport

Cron entry: `discovery-archive-stale-daily` at 02:00 UTC.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

log = logging.getLogger("pi-ceo.discovery_archive")

STALE_THRESHOLD_DAYS: int = 7
DISCOVERY_LOOP_LABEL: str = "discovery-loop"
LINEAR_GRAPHQL_URL: str = "https://api.linear.app/graphql"


@dataclass
class ArchiveReport:
    started_at: str = ""
    finished_at: str = ""
    inspected: int = 0
    archived: list[str] = field(default_factory=list)  # Linear identifiers
    skipped_recent_activity: int = 0
    skipped_high_severity: int = 0
    errors: list[str] = field(default_factory=list)


def _api_key() -> str:
    return os.environ.get("LINEAR_API_KEY", "").strip()


def _gql(query: str, variables: dict | None = None) -> dict:
    """POST GraphQL. Returns parsed JSON or `{"error": ...}`. Never raises."""
    key = _api_key()
    if not key:
        return {"error": "no_api_key"}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        LINEAR_GRAPHQL_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("discovery_archive: gql error: %s", exc)
        return {"error": "request_failed", "exception": repr(exc)}


def _resolve_label_id(label_name: str = DISCOVERY_LOOP_LABEL) -> str | None:
    """Resolve `discovery-loop` workspace label UUID."""
    res = _gql(
        "query { issueLabels(first: 250) { nodes { id name } } }"
    )
    if "error" in res:
        return None
    for lbl in (res.get("data", {}).get("issueLabels", {}).get("nodes") or []):
        if lbl.get("name", "").lower() == label_name.lower():
            return lbl["id"]
    return None


def _resolve_canceled_state_id(team_id: str) -> str | None:
    """Find the team's `Canceled` workflow state UUID."""
    res = _gql(
        "query($teamId: String!) { team(id: $teamId) { "
        "states { nodes { id name type } } } }",
        {"teamId": team_id},
    )
    if "error" in res:
        return None
    nodes = (
        res.get("data", {}).get("team", {}).get("states", {}).get("nodes") or []
    )
    for st in nodes:
        if (st.get("type") or "").lower() == "canceled":
            return st["id"]
    return None


def _list_stale_candidates(
    label_id: str, *, since_iso: str,
) -> list[dict]:
    """Find Discovery-loop tickets at sev 4-5 (priority 3-4) not updated
    since `since_iso`. Returns minimal dicts: id, identifier, title,
    priority, teamId, stateName.

    Linear pagination is best-effort — first 100 stale candidates is
    enough; the cron runs daily so backlog drains in days, not seconds.
    """
    query = """
    query($labelId: ID!, $since: DateTimeOrDuration!) {
      issues(
        first: 100,
        orderBy: updatedAt,
        filter: {
          labels: { id: { eq: $labelId } },
          updatedAt: { lt: $since },
          priority: { in: [3, 4] },
          state: { type: { in: ["backlog", "unstarted"] } }
        }
      ) {
        nodes {
          id identifier title priority
          team { id }
          state { id name type }
        }
      }
    }
    """
    res = _gql(query, {"labelId": label_id, "since": since_iso})
    if "error" in res:
        return []
    nodes = (res.get("data", {}).get("issues") or {}).get("nodes") or []
    return nodes


def _close_to_canceled(issue_id: str, state_id: str, comment_body: str) -> bool:
    """Add an explanatory comment + transition issue to Canceled.
    Returns True on success."""
    # Comment first so the close note survives even if the state
    # transition fails for any reason.
    comment_res = _gql(
        """
        mutation($input: CommentCreateInput!) {
          commentCreate(input: $input) { success }
        }
        """,
        {"input": {"issueId": issue_id, "body": comment_body}},
    )
    if "error" in comment_res:
        log.warning("discovery_archive: comment create failed: %s", comment_res.get("error"))

    update_res = _gql(
        """
        mutation($id: String!, $stateId: String!) {
          issueUpdate(id: $id, input: { stateId: $stateId }) {
            success
          }
        }
        """,
        {"id": issue_id, "stateId": state_id},
    )
    if "error" in update_res:
        return False
    data = (update_res.get("data") or {}).get("issueUpdate", {})
    return bool(data.get("success"))


def archive_stale_discovery_tickets() -> ArchiveReport:
    """Run one archive sweep. Returns ArchiveReport.

    Behaviour:
      * Lists discovery-loop-labelled tickets in priority 3-4 (sev 4-5)
        that are still in backlog/todo state with `updatedAt` older
        than 7 days.
      * For each: post an explanatory comment + transition state to the
        team's Canceled workflow state.
      * sev≥6 tickets (priority 1-2) are excluded by the GraphQL filter.
      * No-op safe when LINEAR_API_KEY is unset (returns early with
        a structured error in `report.errors`).
    """
    started = datetime.now(timezone.utc)
    report = ArchiveReport(started_at=started.isoformat())

    if not _api_key():
        report.errors.append("no_linear_api_key")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    label_id = _resolve_label_id()
    if not label_id:
        report.errors.append("discovery_loop_label_not_found")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    cutoff = started - timedelta(days=STALE_THRESHOLD_DAYS)
    cutoff_iso = cutoff.isoformat()

    candidates = _list_stale_candidates(label_id, since_iso=cutoff_iso)
    report.inspected = len(candidates)

    # Cache canceled-state lookup per team so we don't re-query.
    canceled_state_cache: dict[str, str | None] = {}

    for c in candidates:
        team_id = (c.get("team") or {}).get("id")
        if not team_id:
            report.errors.append(f"missing_team:{c.get('identifier')}")
            continue
        if team_id not in canceled_state_cache:
            canceled_state_cache[team_id] = _resolve_canceled_state_id(team_id)
        state_id = canceled_state_cache[team_id]
        if not state_id:
            report.errors.append(f"canceled_state_not_found:{c.get('identifier')}")
            continue

        # Extra safety: don't archive priority 0/1/2 (Urgent/High)
        # even if filter let one through (e.g. priority changed since
        # the GraphQL fetch).
        priority = int(c.get("priority") or 3)
        if priority < 3:
            report.skipped_high_severity += 1
            continue

        comment = (
            "**Auto-archived by Discovery loop sweep (RA-2027)**\n\n"
            f"This Discovery proposal was filed >{STALE_THRESHOLD_DAYS} "
            "days ago at priority Medium/Low and has had no comment, "
            "state change, or label update since.\n\n"
            "Per operator policy 2026-05-06, sev 4-5 unactioned proposals "
            "auto-close to Cancelled to keep the persona's board legible. "
            "Re-open if this finding becomes relevant again — the original "
            "Discovery cycle metadata is preserved in the ticket history."
        )
        ok = _close_to_canceled(c["id"], state_id, comment)
        if ok:
            report.archived.append(c.get("identifier") or c["id"])
        else:
            report.errors.append(f"close_failed:{c.get('identifier')}")

    report.finished_at = datetime.now(timezone.utc).isoformat()
    log.info(
        "discovery_archive: inspected=%d archived=%d skipped_high_sev=%d errors=%d",
        report.inspected, len(report.archived),
        report.skipped_high_severity, len(report.errors),
    )
    return report


# ── Cron-callable shim ───────────────────────────────────────────────────────


async def _fire_discovery_archive_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'discovery_archive', ...}."""
    import asyncio as _aio  # noqa: PLC0415

    log_arg.info("Firing discovery_archive trigger id=%s", trigger.get("id"))
    report = await _aio.to_thread(archive_stale_discovery_tickets)
    log_arg.info(
        "discovery_archive id=%s done: inspected=%d archived=%d skipped_high=%d errors=%d",
        trigger.get("id"), report.inspected, len(report.archived),
        report.skipped_high_severity, len(report.errors),
    )


__all__ = [
    "STALE_THRESHOLD_DAYS",
    "DISCOVERY_LOOP_LABEL",
    "ArchiveReport",
    "archive_stale_discovery_tickets",
]
