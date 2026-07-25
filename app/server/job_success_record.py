"""
job_success_record.py — Job-authored last-success records (fleet reliability).

The fleet's watchdogs historically inferred a cron job's health from the mtime
of the newest artefact file the job (supposedly) produced. That is a lie
detector with the lie built in: a file's existence or mtime is NOT proof that
the job actually ran and succeeded. Multiple incidents share this one root
cause —

  * RA-6902 — a 74-day-stale artefact was read as healthy;
  * RA-1469 — Pi-SEO silently skipped for 161h;
  * RA-7085 — a watchdog silently missed for 475h;
  * empire-morning-close-loop — the 06:30 slot was eaten by a
    `gateway --replace` restart and the miss was invisible.

In every case a MISSED or SKIPPED run stayed invisible because "file exists /
mtime recent" was trusted instead of a real, freshness-stamped success claim
authored by the job itself.

This module replaces mtime-of-newest-file health checks with a JOB-AUTHORED
success record. On genuine success — and only then — a job calls
``record_success(job_id)``, which writes ``{job_id, status, ts, detail}`` to
``.harness/job-success/<job_id>.json``. A watchdog then asks
``job_health(job_id, threshold_h)`` and receives a FAIL-CLOSED verdict: a
missing, stale, failed or skipped record reads as UNHEALTHY, never healthy. A
run that never happened writes nothing, so it reads as ``MISSING`` and the
watchdog fires instead of being fooled by a leftover file.

Taxonomy (the ``status`` a job may author, and the verdict a watchdog reads):

    status      meaning (author side)          verdict when latest + fresh
    ----------  -----------------------------  ---------------------------
    ok          genuine success                HEALTHY (if within threshold)
    skipped     intentional no-op this cycle   SKIPPED  (never HEALTHY)
    failed      ran but failed                 FAILED   (never HEALTHY)
    (none)      never ran / record lost        MISSING  (never HEALTHY)

    plus STALE: a real ``ok`` record whose ts is older than the threshold
    (the Missed / Late case).

Only a fresh ``ok`` record is HEALTHY. Everything else is an alertable state.

Durability note: the record lives on disk under ``.harness/job-success/``.
On a host whose filesystem resets on deploy (Railway), the file can vanish and
read as ``MISSING`` until the job authors its next success — which fails CLOSED
(alert-eligible), the safe direction. Watchdogs that must survive redeploy
without a false positive additionally consult the durable, Supabase-backed
trigger ``last_fired_at`` overlay (see ``cron_watchdogs._validated_trigger_age_h``);
this module deliberately owns only the job-authored, mtime-free signal.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

# Status values a job may author.
STATUS_OK = "ok"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
_VALID_STATUSES = frozenset({STATUS_OK, STATUS_SKIPPED, STATUS_FAILED})

# Health verdict states a watchdog reads.
HEALTHY = "healthy"
STALE = "stale"
MISSING = "missing"
FAILED = "failed"
SKIPPED = "skipped"


def _job_success_dir() -> Path:
    """Return the on-disk directory holding job-authored success records.

    Pulled into a function so tests can monkeypatch this single seam without
    reaching into the ``Path(__file__).parent...`` chain — mirroring the
    ``cron_watchdogs._board_meetings_dir()`` convention.
    """
    return Path(__file__).parent.parent.parent / ".harness" / "job-success"


def _record_path(job_id: str) -> Path:
    # Keep the filename filesystem-safe; job_ids are slugs like
    # "board-meeting-daily" but guard against a stray separator anyway.
    safe = job_id.replace("/", "_").replace("\\", "_")
    return _job_success_dir() / f"{safe}.json"


def record(job_id: str, status: str = STATUS_OK, *, detail: str | None = None,
           ts: float | None = None) -> bool:
    """Write a job-authored record ``{job_id, status, ts, detail}`` atomically.

    Call this from the JOB, on the outcome it is asserting — ``record_success``
    only on genuine success. Returns True on write, False on any failure
    (observability must never crash the job). ``ts`` defaults to now.
    """
    if not job_id:
        return False
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"job_success_record.record: status must be one of {sorted(_VALID_STATUSES)}, "
            f"got {status!r}"
        )
    payload = {
        "job_id": job_id,
        "status": status,
        "ts": float(ts) if ts is not None else time.time(),
        "detail": detail,
    }
    try:
        directory = _job_success_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = _record_path(job_id)
        tmp = path.with_suffix(".json.tmp")
        # Atomic publish so a torn write never leaves a fresh-but-corrupt
        # record that a reader would mistake for a valid success.
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def record_success(job_id: str, *, detail: str | None = None,
                   ts: float | None = None) -> bool:
    """Author an ``ok`` record. Call ONLY on genuine success."""
    return record(job_id, STATUS_OK, detail=detail, ts=ts)


def record_skipped(job_id: str, *, detail: str | None = None,
                   ts: float | None = None) -> bool:
    """Author a ``skipped`` record — an intentional no-op this cycle."""
    return record(job_id, STATUS_SKIPPED, detail=detail, ts=ts)


def record_failed(job_id: str, *, detail: str | None = None,
                  ts: float | None = None) -> bool:
    """Author a ``failed`` record — the job ran but did not succeed."""
    return record(job_id, STATUS_FAILED, detail=detail, ts=ts)


def read_record(job_id: str) -> dict | None:
    """Return the validated record dict, or None when it is absent/corrupt.

    Fail-closed: a missing file, unreadable JSON, an unknown status, or a
    non-finite ts all return None so the caller treats the job as unproven
    rather than trusting a malformed claim.
    """
    if not job_id:
        return None
    path = _record_path(job_id)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if status not in _VALID_STATUSES:
        return None
    ts = data.get("ts")
    # Reject bool (a subclass of int) and non-numeric / non-finite timestamps.
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return None
    if not math.isfinite(float(ts)):
        return None
    return data


@dataclass(frozen=True)
class Verdict:
    """A fail-closed health verdict for one job.

    ``state`` is one of HEALTHY / STALE / MISSING / FAILED / SKIPPED.
    ``age_h`` is the record's age in hours (None when MISSING).
    ``record`` is the underlying record dict (None when MISSING).
    """
    state: str
    age_h: float | None
    record: dict | None

    @property
    def healthy(self) -> bool:
        return self.state == HEALTHY


def job_health(job_id: str, threshold_h: float, *, now: float | None = None) -> Verdict:
    """Return the fail-closed health Verdict for ``job_id``.

    Only a fresh ``ok`` record (age < ``threshold_h``) is HEALTHY. A real
    ``ok`` record older than the threshold is STALE (Missed / Late). A latest
    record of ``failed`` / ``skipped`` maps to FAILED / SKIPPED regardless of
    age — an explicit non-success is never healthy. No record at all is
    MISSING. None of these are ever masked by a file's existence or mtime.
    """
    clock = time.time() if now is None else now
    rec = read_record(job_id)
    if rec is None:
        return Verdict(MISSING, None, None)
    age_h = max(clock - float(rec["ts"]), 0.0) / 3600.0
    status = rec["status"]
    if status == STATUS_FAILED:
        return Verdict(FAILED, age_h, rec)
    if status == STATUS_SKIPPED:
        return Verdict(SKIPPED, age_h, rec)
    # status == ok
    if age_h < threshold_h:
        return Verdict(HEALTHY, age_h, rec)
    return Verdict(STALE, age_h, rec)


def success_age_h(job_id: str, *, now: float | None = None) -> float | None:
    """Age in hours of the latest GENUINE success, or None when unproven.

    Returns a number only when the latest record is ``ok`` (proof of life).
    A missing, failed or skipped record returns None — the caller then has no
    proof-of-life from this signal and must fail closed. Designed for watchdogs
    that combine several liveness signals with ``min(...)``: a None contributes
    nothing, so a job with no genuine success reads as maximally silent.
    """
    clock = time.time() if now is None else now
    rec = read_record(job_id)
    if rec is None or rec["status"] != STATUS_OK:
        return None
    return max(clock - float(rec["ts"]), 0.0) / 3600.0
