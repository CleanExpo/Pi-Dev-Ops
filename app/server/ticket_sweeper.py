"""app/server/ticket_sweeper.py — nightly Linear ticket-lifecycle sweeper (audit #17).

Problem (estate audit 2026-09-30): 105 of 136 started tickets untouched 14+
days; failed builds exit to Todo, which the poller never reads; In Review
tickets wait on red PRs with nothing telling a human. This sweep:

  (a) started, no activity 14d → comment + ``stale:14d``; moved to Todo ONLY
      when it has no PR, no open blocker and is not already a Blocked state
  (b) In Review whose PR is red, or open and unreviewed >3d → ``review:red-pr``.
      In Review is a deliberate human wait: surfaced, never moved.
  (c) failed build sitting in Todo → Ready for Pi-Dev once (``pi-dev:failed-retry-used``),
      then Pi-Dev: Blocked with ``pi-dev:blocked-reason:build-failed``

DRY-RUN BY DEFAULT. Linear writes happen only when ``TAO_TICKET_SWEEPER_WRITE=1``.
Counts persist to ``.harness/ticket-sweeper-state.json`` and are served on
``/api/mission-control/live`` as ``ticket_sweeper``. Cron entry: ``ticket-sweeper-nightly``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import autonomy, config
from . import ticket_sweeper_io as io

log = logging.getLogger("pi-ceo.ticket_sweeper")

_STATE_FILE = Path(__file__).resolve().parents[2] / ".harness" / "ticket-sweeper-state.json"
WRITE_ENV = "TAO_TICKET_SWEEPER_WRITE"
STALE_DAYS = 14
UNREVIEWED_DAYS = 3
STALE_LABEL = "stale:14d"
REVIEW_LABEL = "review:red-pr"
RETRY_LABEL = "pi-dev:failed-retry-used"
BLOCKED_REASON_LABEL = "pi-dev:blocked-reason:build-failed"
FAILED_MARKER = "Pi CEO build **failed**"  # session_linear.py failed-build comment

_COUNT_FIELDS = ("stale_labelled", "stale_to_todo", "review_red_pr", "review_unknown",
                 "failed_to_ready", "failed_to_blocked")


@dataclass
class SweepReport:
    started_at: str = ""
    finished_at: str = ""
    dry_run: bool = True
    complete: bool = True
    stale_labelled: list[str] = field(default_factory=list)   # labelled, left in place
    stale_to_todo: list[str] = field(default_factory=list)    # labelled + moved to Todo
    review_red_pr: list[str] = field(default_factory=list)
    review_unknown: list[str] = field(default_factory=list)   # PR state could not be read
    failed_to_ready: list[str] = field(default_factory=list)
    failed_to_blocked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def writes_enabled() -> bool:
    return os.environ.get(WRITE_ENV, "").strip() == "1"


# ── Decisions (pure) ─────────────────────────────────────────────────────────

def decide_stale(issue: dict) -> str | None:
    """'todo' (label + move), 'label' (label only), or None (not swept)."""
    state = ((issue.get("state") or {}).get("name") or "").lower()
    if state == "in review":
        return None
    if "blocked" in state or io.pr_refs(issue) or io.open_blockers(issue):
        return "label"
    return "todo"


def decide_review(facts: list[dict | None], now: datetime) -> str:
    """'red' when any open PR is red or unreviewed > 3d; 'unknown' when a PR
    could not be read and none was flagged; else 'ok'. ``None`` = read failed."""
    cutoff = now - timedelta(days=UNREVIEWED_DAYS)
    for f in facts:
        if f is None or not f["open"]:
            continue
        created = datetime.fromisoformat(f["created_at"].replace("Z", "+00:00")) if f["created_at"] else now
        if f["red"] or (not f["reviewed"] and created < cutoff):
            return "red"
    return "unknown" if any(f is None for f in facts) else "ok"


def decide_failed(issue: dict) -> str | None:
    """'ready' for a first failure, 'blocked' after the retry, else None."""
    bodies = [c.get("body") or "" for c in (issue.get("comments") or {}).get("nodes") or []]
    failures = sum(1 for b in bodies if b.startswith(FAILED_MARKER))
    labels = io.label_names(issue)
    if failures == 0 or BLOCKED_REASON_LABEL in labels:
        return None
    return "ready" if failures == 1 and RETRY_LABEL not in labels else "blocked"


# ── Writes (only when enabled) ───────────────────────────────────────────────

def _apply(api_key: str, issue: dict, report: SweepReport, *,
           label: str, comment: str | None = None, state: str | None = None) -> None:
    if report.dry_run:
        return
    iid, team = issue["id"], issue.get("_team_id") or autonomy._TEAM_ID
    try:
        if comment:
            autonomy.comment_on_issue(api_key, iid, comment)
        if label.lower() not in io.label_names(issue) and not autonomy.add_label_to_issue(api_key, iid, team, label):
            report.errors.append(f"label_failed:{issue.get('identifier')}")
        if state:
            autonomy.transition_issue(api_key, iid, state, team_id=team)
    except autonomy.LinearRateLimitError:
        raise
    except Exception as exc:  # noqa: BLE001 — one ticket never aborts the sweep
        report.errors.append(f"write_failed:{issue.get('identifier')}:{type(exc).__name__}")


def _sweep_stale(api_key: str, issues: list[dict], report: SweepReport) -> None:
    for issue in issues:
        verdict = decide_stale(issue)
        if verdict is None:
            continue
        move = verdict == "todo"
        (report.stale_to_todo if move else report.stale_labelled).append(issue["identifier"])
        note = ("moved to Todo: no linked PR and nothing blocking it." if move
                else "left in place: it has a linked PR, an open blocker, or is Blocked.")
        _apply(api_key, issue, report, label=STALE_LABEL, state="Todo" if move else None,
               comment=f"**Stale sweep:** no activity for {STALE_DAYS}+ days — {note}")


def _review_facts(issue: dict) -> list[dict | None]:
    out: list[dict | None] = []
    for repo, number in io.pr_refs(issue):
        try:
            out.append(io.pr_facts(repo, number))
        except Exception as exc:  # noqa: BLE001 — unreadable is "unknown", never green
            log.warning("ticket_sweeper: PR %s#%s unreadable: %s", repo, number, type(exc).__name__)
            out.append(None)
    return out


def _sweep_review(api_key: str, issues: list[dict], report: SweepReport, now: datetime) -> None:
    for issue in issues:
        facts = _review_facts(issue)
        if not facts:
            continue
        verdict = decide_review(facts, now)
        if verdict == "unknown":
            report.review_unknown.append(issue["identifier"])
        elif verdict == "red":
            report.review_red_pr.append(issue["identifier"])
            _apply(api_key, issue, report, label=REVIEW_LABEL)


def _sweep_failed(api_key: str, issues: list[dict], report: SweepReport) -> None:
    for issue in issues:
        verdict = decide_failed(issue)
        if verdict == "ready":
            report.failed_to_ready.append(issue["identifier"])
            _apply(api_key, issue, report, label=RETRY_LABEL, state=autonomy._READY_STATUS_NAME,
                   comment="**Failed-build sweep:** first failure — sent back to Ready for Pi-Dev once.")
        elif verdict == "blocked":
            report.failed_to_blocked.append(issue["identifier"])
            _apply(api_key, issue, report, label=BLOCKED_REASON_LABEL, state=autonomy._BLOCKED_STATUS_NAME,
                   comment="**Failed-build sweep:** failed again after its one retry — blocked for a human.")


# ── Run + state ──────────────────────────────────────────────────────────────

def run_sweep(now: datetime | None = None) -> SweepReport:
    now = now or datetime.now(timezone.utc)
    report = SweepReport(started_at=now.isoformat(), dry_run=not writes_enabled())
    api_key = (os.environ.get("LINEAR_API_KEY") or getattr(config, "LINEAR_API_KEY", "") or "").strip()
    try:
        if not api_key:
            report.errors.append("no_linear_api_key")
            return report
        buckets, fetch_errors = io.fetch_buckets(api_key, stale_days=STALE_DAYS, now=now)
        report.errors.extend(fetch_errors)
        _sweep_stale(api_key, buckets["stale"], report)
        _sweep_review(api_key, buckets["in_review"], report, now)
        _sweep_failed(api_key, buckets["recent_todo"], report)
    except autonomy.LinearRateLimitError:
        report.errors.append("linear_rate_limited")
    finally:
        report.complete = not report.errors or all(e.startswith(("label_failed", "write_failed")) for e in report.errors)
        report.finished_at = datetime.now(timezone.utc).isoformat()
        _write_state(report)
    return report


def _write_state(report: SweepReport) -> None:
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(report)))
        os.replace(tmp, _STATE_FILE)
    except Exception as exc:  # noqa: BLE001 — state IO must never break the sweep
        log.warning("ticket_sweeper: could not persist state: %s", exc)


def status_snapshot() -> dict:
    """Mission Control tile payload. Never-run reads as never-run, not as zero."""
    try:
        state = json.loads(_STATE_FILE.read_text())
    except Exception:  # noqa: BLE001 — missing/corrupt = never run
        return {"last_run_at": None, "dry_run": not writes_enabled(), "complete": False,
                "counts": None, "errors": []}
    return {
        "last_run_at": state.get("finished_at"),
        "dry_run": bool(state.get("dry_run", True)),
        "complete": bool(state.get("complete")),
        "counts": {k: len(state.get(k) or []) for k in _COUNT_FIELDS},
        "review_red_pr": (state.get("review_red_pr") or [])[:20],
        "errors": (state.get("errors") or [])[:10],
    }


async def _fire_ticket_sweeper_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'ticket_sweeper', ...}."""
    report = await asyncio.to_thread(run_sweep)
    log_arg.info(
        "ticket_sweeper id=%s dry_run=%s complete=%s %s errors=%d", trigger.get("id"),
        report.dry_run, report.complete,
        " ".join(f"{k}={len(getattr(report, k))}" for k in _COUNT_FIELDS), len(report.errors),
    )
