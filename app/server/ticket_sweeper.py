"""app/server/ticket_sweeper.py — nightly Linear ticket-lifecycle sweeper (audit #17).

Problem (estate audit 2026-09-30): 105 of 136 started tickets untouched 14+
days; failed builds exit to Todo, which the poller never reads; In Review
tickets wait on red PRs with nothing telling a human. This sweep:

  (a) started, no activity 14d → comment + ``stale:14d``; moved to Todo ONLY
      when it has no PR, no open blocker and is not already a Blocked state
  (b) In Review whose PR is red, or open and unreviewed >3d → ``review:red-pr``.
      In Review is a deliberate human wait: surfaced, never moved.
  (c) failed build sitting in Todo → Ready for Pi-Dev once (``pi-dev:failed-retry-used``),
      then Pi-Dev: Blocked with ``pi-dev:blocked-reason:build-failed``. Only
      failures newer than the sweeper's own last comment count (see decide_failed).

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
from . import ticket_sweeper_write as wr

log = logging.getLogger("pi-ceo.ticket_sweeper")

_STATE_FILE = Path(__file__).resolve().parents[2] / ".harness" / "ticket-sweeper-state.json"
WRITE_ENV = "TAO_TICKET_SWEEPER_WRITE"
STALE_DAYS = 14
UNREVIEWED_DAYS = 3
STATE_MAX_AGE_H = 36  # nightly job: an older saved run is not "the latest" any more
STALE_LABEL = "stale:14d"
REVIEW_LABEL = "review:red-pr"
RETRY_LABEL = "pi-dev:failed-retry-used"
BLOCKED_REASON_LABEL = "pi-dev:blocked-reason:build-failed"
FAILED_MARKER = "Pi CEO build **failed**"  # session_linear.py failed-build comment
SWEEP_COMMENT_PREFIX = "**Failed-build sweep:**"  # the sweeper's own epoch marker

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
    pending_moves: list[dict] = field(default_factory=list)   # label+comment landed, move did not


def writes_enabled() -> bool:
    return os.environ.get(WRITE_ENV, "").strip() == "1"


# ── Decisions (pure) ─────────────────────────────────────────────────────────

def decide_stale(issue: dict) -> str | None:
    """'todo' (label + move), 'label' (label only), or None (not swept).
    An attachment or relation list that did not arrive whole is 'label': never move on a guess."""
    state = ((issue.get("state") or {}).get("name") or "").lower()
    if state == "in review":
        return None
    if "blocked" in state or io.pr_refs(issue) != [] or io.open_blockers(issue):
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
    """'ready', 'blocked', 'unread' or None for a Todo ticket.

    The sweeper's own last comment is the epoch: only build failures AFTER it
    count. Blocking needs BOTH durable markers — a sweeper comment and the
    retry label. No retry marker → a failure earns the one retry ('ready');
    a human removing the retry label grants another. After a grant, a new
    failure → 'blocked'. A ticket a human moved back after a block has no
    failure since, so it is left alone.
    """
    bodies, labels = io.ordered_bodies(issue), io.label_names(issue)
    if bodies is None or labels is None:
        return "unread"
    last = max((i for i, b in enumerate(bodies) if b.startswith(SWEEP_COMMENT_PREFIX)), default=-1)
    if not any(b.startswith(FAILED_MARKER) for b in bodies[last + 1:]):
        return None
    return "blocked" if last != -1 and RETRY_LABEL in labels else "ready"


# ── Writes (only when enabled) ───────────────────────────────────────────────

def _sweep_stale(api_key: str, issues: list[dict], report: SweepReport, now: datetime) -> None:
    cutoff = now - timedelta(days=STALE_DAYS)
    for issue in issues:
        verdict = decide_stale(issue)
        if verdict is None:
            continue
        move = verdict == "todo"
        note = ("moved to Todo: no linked PR and nothing blocking it." if move
                else "left in place: it has a linked PR, an open blocker, or is Blocked.")
        if wr.apply(api_key, issue, report, wr.Write(
                STALE_LABEL, f"**Stale sweep:** no activity for {STALE_DAYS}+ days — {note}",
                "Todo" if move else None,
                lambda f, v=verdict: io.older_than(f, cutoff) and decide_stale(f) == v,
                _GUARDS["stale"], "stale")):
            (report.stale_to_todo if move else report.stale_labelled).append(issue["identifier"])


def _review_facts(issue: dict) -> list[dict | None]:
    out: list[dict | None] = []
    refs = io.pr_refs(issue)
    if refs is None:
        return [None]  # attachment list incomplete → unknown, never green
    for repo, number in refs:
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
        elif verdict == "red" and wr.apply(
                api_key, issue, report, wr.Write(REVIEW_LABEL, recheck=lambda f: io.state_is(f, "In Review"))):
            report.review_red_pr.append(issue["identifier"])


def _has_retry_label(issue: dict) -> bool:
    """Pre-move guard: the durable retry marker is still on the ticket (a human may remove it)."""
    return RETRY_LABEL in (io.label_names(issue) or set())


# Checked just before any move, and again before finishing an unfinished one.
_GUARDS = {
    "stale": lambda f: decide_stale(f) == "todo",
    "ready": lambda f: io.state_is(f, "Todo") and _has_retry_label(f),
    "blocked": lambda f: io.state_is(f, "Todo") and _has_retry_label(f),
}


def _sweep_failed(api_key: str, issues: list[dict], report: SweepReport) -> None:
    for issue in issues:
        verdict = decide_failed(issue)
        if verdict == "unread":
            report.errors.append(f"comments_unread:{issue['identifier']}")
        elif verdict == "ready" and wr.apply(api_key, issue, report, wr.Write(
                RETRY_LABEL, f"{SWEEP_COMMENT_PREFIX} first failure — sent back to Ready for Pi-Dev once.",
                autonomy._READY_STATUS_NAME, lambda f: io.state_is(f, "Todo") and decide_failed(f) == "ready",
                _GUARDS["ready"], "ready")):
            report.failed_to_ready.append(issue["identifier"])
        elif verdict == "blocked" and wr.apply(api_key, issue, report, wr.Write(
                BLOCKED_REASON_LABEL, f"{SWEEP_COMMENT_PREFIX} failed again after its one retry — blocked for a human.",
                autonomy._BLOCKED_STATUS_NAME, lambda f: io.state_is(f, "Todo") and decide_failed(f) == "blocked",
                _GUARDS["blocked"], "blocked")):
            report.failed_to_blocked.append(issue["identifier"])


# ── Run + state ──────────────────────────────────────────────────────────────

def run_sweep(now: datetime | None = None) -> SweepReport:
    now = now or datetime.now(timezone.utc)
    report = SweepReport(started_at=now.isoformat(), dry_run=not writes_enabled(), complete=False)
    api_key = (os.environ.get("LINEAR_API_KEY") or getattr(config, "LINEAR_API_KEY", "") or "").strip()
    report.pending_moves = list(_read_state().get("pending_moves") or [])  # kept until finished
    _write_state(report)  # in-progress: the tile never shows the previous run while this one runs
    try:
        if not api_key:
            report.errors.append("no_linear_api_key")
            return report
        wr.resume_pending(api_key, report, _GUARDS)
        buckets, fetch_errors = io.fetch_buckets(api_key, stale_days=STALE_DAYS, now=now)
        report.errors.extend(fetch_errors)
        _sweep_stale(api_key, buckets["stale"], report, now)
        _sweep_review(api_key, buckets["in_review"], report, now)
        _sweep_failed(api_key, buckets["recent_todo"], report)
    except autonomy.LinearRateLimitError:
        report.errors.append("linear_rate_limited")
    except Exception as exc:  # noqa: BLE001 — a crash must persist as incomplete, never as a clean zero
        log.exception("ticket_sweeper: sweep crashed")
        report.errors.append(f"sweep_crashed:{type(exc).__name__}")
    finally:
        report.complete = not report.errors and not report.pending_moves  # unfinished moves = not done
        report.finished_at = datetime.now(timezone.utc).isoformat()
        _write_state(report)
    return report


# Set when the latest run could not be saved, so the tile never shows an OLDER
# complete run as current. Process-local; the next saved run clears it.
_unsaved_run_at: str | None = None


def _write_state(report: SweepReport) -> None:
    global _unsaved_run_at
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(report)))
        os.replace(tmp, _STATE_FILE)
        _unsaved_run_at = None
        _fail_file().unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 — state IO must never break the sweep
        log.warning("ticket_sweeper: could not persist state: %s", exc)
        _unsaved_run_at = report.finished_at or report.started_at
        for undo in (lambda: _fail_file().write_text(json.dumps({"at": _unsaved_run_at})),
                     lambda: _STATE_FILE.unlink(missing_ok=True)):
            try:  # an older saved run must not outlive this process as "current"
                undo()
            except OSError:
                pass  # disk refuses every write: the 36h staleness check still catches it


def _fail_file() -> Path:
    return _STATE_FILE.with_name("ticket-sweeper-save-failed.json")


def _read_state() -> dict:
    try:
        state = json.loads(_STATE_FILE.read_text())
        return state if isinstance(state, dict) else {}
    except Exception:  # noqa: BLE001 — missing/corrupt = nothing saved
        return {}


def status_snapshot() -> dict:
    """Mission Control tile payload. Never-run reads as never-run, not as zero,
    and a run that could not be saved reads as incomplete, not as the last saved one."""
    global _unsaved_run_at
    if _unsaved_run_at is None and _fail_file().exists():
        _unsaved_run_at = "unknown (save failed before a restart)"
    if _unsaved_run_at is not None:
        return {"last_run_at": _unsaved_run_at, "dry_run": not writes_enabled(), "complete": False,
                "counts": None, "errors": ["state_write_failed"]}
    state = _read_state()
    if not state:
        return {"last_run_at": None, "dry_run": not writes_enabled(), "complete": False,
                "counts": None, "errors": []}
    fresh = io.within(state.get("finished_at"), timedelta(hours=STATE_MAX_AGE_H))
    return {
        "last_run_at": state.get("finished_at"),
        "dry_run": bool(state.get("dry_run", True)),
        "complete": bool(state.get("complete")) and fresh,
        "counts": {k: len(state.get(k) or []) for k in _COUNT_FIELDS},
        "review_red_pr": (state.get("review_red_pr") or [])[:20],
        "errors": ([] if fresh else ["stale_state"]) + (state.get("errors") or [])[:10],
    }


async def _fire_ticket_sweeper_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'ticket_sweeper', ...}."""
    report = await asyncio.to_thread(run_sweep)
    log_arg.info(
        "ticket_sweeper id=%s dry_run=%s complete=%s %s errors=%d", trigger.get("id"),
        report.dry_run, report.complete,
        " ".join(f"{k}={len(getattr(report, k))}" for k in _COUNT_FIELDS), len(report.errors),
    )
