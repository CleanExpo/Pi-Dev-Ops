"""app/server/burndown.py — RA-6670 bounded daily P3 backlog-burndown.

Problem (founder-reported 2026-06-15): cron jobs surface findings but "there
never seems to be progress on the evidence found." Root cause: the push side
files findings as Linear tickets, but triage defaults scan findings to P3
(``triage.py`` ``_SEVERITY_TO_LINEAR_PRIORITY`` medium→3), while the only
worker (``autonomy.py``) claims tickets that are status "Ready for Pi-Dev" AND
labelled "pi-dev:autonomous". P3 findings carry neither signal, so they sit in
Todo forever — a live snapshot showed 219 of 250 open tickets (88%) ignored.

This trigger pulls the top-K open **P3** Todo findings across the portfolio each
run and drives each to a TERMINAL state, bounded so it can never flood:

  (a) workable (engineering ticket) → autonomy build session → PR
      (reuses ``autonomy._process_autonomy_issue`` — transition + create_session)
  (b) unworkable (no-code / manual / legal) → close-to-Canceled with a one-line
      reason (reuses ``discovery_archive._close_to_canceled``)

Bounds: ``TAO_BURNDOWN_DAILY_CAP`` (default 5) caps tickets claimed per run; the
RA-1966 ``TAO_HARD_STOP_FILE`` aborts mid-run. Lowering the autonomy threshold
to P3 was explicitly REJECTED — it would spawn ~219 sessions at once.

The Telegram summary is EDGE-TRIGGERED (per the no-repeat-pings rule): it fires
only when a run did something AND the summary differs from the previous run's,
so persistent idle days never re-ping.

Cron entry: ``burndown-daily``.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import autonomy, config, discovery_archive

log = logging.getLogger("pi-ceo.burndown")

# State file for edge-triggered Telegram (gitignored — RA-3006: never track a
# runtime-mutated .harness file). Holds the last run's summary signature only.
_STATE_FILE = Path(__file__).resolve().parents[2] / ".harness" / "burndown-state.json"

# Fetch open P3 (priority 3) Todo issues per portfolio project, most-recent
# first. The ``unstarted`` state filter is what dedups against in-flight work:
# a ticket we worked transitions to In Progress and a ticket we closed goes to
# Canceled, so neither is re-selected on the next run.
_P3_CANDIDATES_QUERY = """
query BurndownP3Issues($projectId: String!) {
    project(id: $projectId) {
        issues(filter: {
            state: { type: { eq: "unstarted" } }
            priority: { eq: 3 }
        }, first: 25, orderBy: updatedAt) {
            nodes {
                id
                identifier
                title
                description
                priority
                url
                estimate
                updatedAt
                state { id name type }
                labels { nodes { name } }
            }
        }
    }
}
"""


@dataclass
class BurndownReport:
    started_at: str = ""
    finished_at: str = ""
    cap: int = 0
    candidates: int = 0            # total P3 Todo findings fetched
    worked: list[str] = field(default_factory=list)   # dispatched to build pipeline
    closed: list[str] = field(default_factory=list)   # closed-to-Canceled with reason
    errors: list[str] = field(default_factory=list)
    telegram_sent: bool = False


def _burndown_cap() -> int:
    """Per-run cap. Reads config (env-backed) so tests/operators can override."""
    return int(getattr(config, "TAO_BURNDOWN_DAILY_CAP", 5))


def fetch_p3_candidates(api_key: str) -> list[dict]:
    """Fetch open P3 (priority-3) Todo findings across every portfolio project,
    most-recent first. Each issue is annotated with ``_repo_url`` / ``_team_id``
    / ``_project_name`` (mirroring ``autonomy.fetch_todo_issues``) so the work
    and close paths route to the correct repo and team.

    Per-project fetch failures are logged and skipped — they never abort the run.
    """
    projects = autonomy._load_portfolio_projects()
    seen: set[str] = set()
    merged: list[dict] = []

    for p in projects:
        try:
            data = autonomy._gql(api_key, _P3_CANDIDATES_QUERY, {"projectId": p["project_id"]})
        except Exception as exc:  # noqa: BLE001
            log.warning("burndown: project %s fetch failed: %s", p["name"], exc)
            continue
        nodes = (data.get("project") or {}).get("issues", {}).get("nodes") or []
        for issue in nodes:
            iid = issue.get("id")
            if not iid or iid in seen:
                continue
            seen.add(iid)
            issue["_repo_url"] = p["repo_url"]
            issue["_team_id"] = p["team_id"]
            issue["_project_name"] = p["name"]
            merged.append(issue)

    # Rank by recency (updatedAt desc). v1 keeps this simple — recency only, no
    # speculative "value" score (per the spec's devil's-advocate cut).
    merged.sort(key=lambda i: i.get("updatedAt") or "", reverse=True)
    return merged


def _close_reason(identifier: str, reason: str) -> str:
    return (
        "**Auto-closed by P3 backlog-burndown (RA-6670)**\n\n"
        f"This P3 finding is not engineering work the autonomous pipeline can "
        f"action (reason: `{reason}`), so it has been closed to keep the backlog "
        "legible and prevent it sitting unworked indefinitely.\n\n"
        "Re-open if it becomes actionable — the original finding metadata is "
        "preserved in the ticket history."
    )


async def run_burndown(cap: int | None = None) -> BurndownReport:
    """Run one burndown sweep. Returns a BurndownReport.

    For each of the top-K P3 candidates: work it (engineering ticket) or close
    it with a reason (no-code / manual / legal). ``cap=0`` fetches and decides
    nothing-claimed — a safe dry-run that proves the wiring without spend.
    """
    from .sessions import create_session  # late import — avoids circular import

    started = datetime.now(timezone.utc)
    cap = _burndown_cap() if cap is None else cap
    report = BurndownReport(started_at=started.isoformat(), cap=cap)

    api_key = (config.LINEAR_API_KEY or "").strip()
    if not api_key:
        report.errors.append("no_linear_api_key")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        log.warning("burndown: LINEAR_API_KEY not set — skipping run")
        return report

    try:
        candidates = fetch_p3_candidates(api_key)
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"fetch_failed:{exc}")
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    report.candidates = len(candidates)
    selected = candidates[:cap] if cap > 0 else []
    log.info("burndown: %d P3 candidates, cap=%d, claiming %d", len(candidates), cap, len(selected))

    # Per-team Canceled-state cache (mirrors discovery_archive).
    canceled_state_cache: dict[str, str | None] = {}

    from . import kill_switch as _ks

    for issue in selected:
        identifier = issue.get("identifier", "?")
        team_id = issue.get("_team_id", autonomy._TEAM_ID)

        # Decide work vs close. Conservative: only the provably-unworkable class
        # (no-code / manual / legal, per autonomy._should_skip_no_code) is
        # auto-closed; everything else is worked, never silently closed.
        skip_no_code, skip_reason = autonomy._should_skip_no_code(issue)
        if skip_no_code:
            if team_id not in canceled_state_cache:
                canceled_state_cache[team_id] = discovery_archive._resolve_canceled_state_id(team_id)
            state_id = canceled_state_cache[team_id]
            if not state_id:
                report.errors.append(f"canceled_state_not_found:{identifier}")
                continue
            ok = discovery_archive._close_to_canceled(
                issue["id"], state_id, _close_reason(identifier, skip_reason or "no-code"),
            )
            if ok:
                report.closed.append(identifier)
            else:
                report.errors.append(f"close_failed:{identifier}")
            continue

        # Work path. Hard-stop file aborts the run cleanly before spending on the
        # next build session (RA-1966 spend axis).
        try:
            _ks.check_hard_stop()
        except _ks.KillSwitchAbort as abort:
            log.warning("burndown: hard-stop file detected — halting run (%s)", abort.snapshot)
            report.errors.append("hard_stop")
            break

        try:
            await autonomy._process_autonomy_issue(config, create_session, issue)
            report.worked.append(identifier)
        except Exception as exc:  # noqa: BLE001 — never let one ticket abort the run
            log.warning("burndown: work dispatch for %s failed: %s", identifier, exc)
            report.errors.append(f"work_failed:{identifier}")

    report.finished_at = datetime.now(timezone.utc).isoformat()
    log.info(
        "burndown done: candidates=%d worked=%d closed=%d errors=%d",
        report.candidates, len(report.worked), len(report.closed), len(report.errors),
    )
    return report


def _read_last_signature() -> str | None:
    try:
        return json.loads(_STATE_FILE.read_text()).get("signature")
    except Exception:  # noqa: BLE001 — missing/corrupt state = no prior signature
        return None


def _write_signature(signature: str) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps({"signature": signature}))
    except Exception as exc:  # noqa: BLE001 — state-file IO must never block
        log.warning("burndown: could not persist state file: %s", exc)


def _maybe_send_telegram(report: BurndownReport) -> bool:
    """Edge-triggered Telegram. Sends only when the run did something AND the
    summary differs from the previous run — so idle days never re-ping
    (per the no-repeat-alert rule). Returns True iff a message was sent.
    """
    activity = len(report.worked) + len(report.closed)
    if activity == 0:
        return False
    signature = f"{len(report.worked)}/{len(report.closed)}/{len(report.errors)}"
    if signature == _read_last_signature():
        return False
    autonomy._send_watchdog_telegram(
        f"🧹 RA-6670 burndown: {len(report.worked)} worked / "
        f"{len(report.closed)} closed / {len(report.errors)} errors "
        f"(from {report.candidates} P3 candidates)"
    )
    _write_signature(signature)
    return True


async def _fire_burndown_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'burndown', ...}."""
    log_arg.info("Firing burndown trigger id=%s", trigger.get("id"))
    report = await run_burndown()
    report.telegram_sent = _maybe_send_telegram(report)
    log_arg.info(
        "burndown id=%s done: candidates=%d worked=%d closed=%d errors=%d telegram=%s",
        trigger.get("id"), report.candidates, len(report.worked),
        len(report.closed), len(report.errors), report.telegram_sent,
    )


__all__ = [
    "BurndownReport",
    "fetch_p3_candidates",
    "run_burndown",
    "_fire_burndown_trigger",
]
