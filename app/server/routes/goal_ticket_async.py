"""Async path of POST /api/goal-ticket/analyze and its status read (UNI-3306 PR 2).

Only used when GOAL_ANALYZE_ASYNC is on. Every store failure is an error response:
a failed read is never "not found", and unavailable async is never a silent inline run.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from .. import goal_analysis_jobs as jobs
from .. import goal_analysis_worker as worker
from ..goal_analyze import validate_analyze
from ..goal_projects import GoalProjectStoreError, get_project

# last_progress_at lets the dashboard show when the job last made progress (grill 14 Q5).
_VIEW = ("id", "status", "attempt", "retry_count", "result", "failure_reason",
         "evidence_links", "created_at", "started_at", "last_progress_at", "ended_at")


def _age_seconds(stamp: Any, now: datetime) -> float | None:
    """Seconds since an ISO timestamp, on the database clock; None when absent or unreadable."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0.0, (now - then).total_seconds())


def job_view(row: dict[str, Any], now: datetime) -> dict[str, Any]:
    view = {key: row.get(key) for key in _VIEW}
    view["elapsed_s"] = _age_seconds(row.get("started_at") or row.get("created_at"), now)
    view["last_progress_age_s"] = _age_seconds(row.get("last_progress_at"), now)
    return view


def _unavailable() -> HTTPException:
    _usable, reason = worker.availability()
    return HTTPException(503, {"error": "async_unavailable", "hint": reason})


def _store_error(exc: jobs.GoalJobStoreError) -> HTTPException:
    status = 409 if isinstance(exc, jobs.KeyMismatch) else 503
    return HTTPException(status, {"error": exc.code, "hint": exc.hint})


async def submit_job(goal: str, acceptance: str, project_id: str, key: str | None) -> dict[str, Any]:
    """Queue (or find) the job and start it. Raises HTTPException on every failure.
    All Supabase I/O runs off the event loop, so heartbeats are never delayed by it."""
    row = await asyncio.to_thread(_queue, goal, acceptance, project_id, key)
    if row["status"] == "queued":
        worker.launch(row["id"])  # a duplicate launch loses the claim; no slot: recovery runs it
    return row


def _queue(goal: str, acceptance: str, project_id: str, key: str | None) -> dict[str, Any]:
    if not worker.availability()[0]:
        raise _unavailable()
    missing = validate_analyze(goal, acceptance, project_id)
    if missing:
        raise HTTPException(400, {"error": "validation", "fields": missing,
                                  "hint": "Goal, acceptance, and a brief are required."})
    try:
        if not get_project(project_id):
            raise HTTPException(400, {"error": "unknown_project", "project_id": project_id,
                                      "hint": "Create a brief first, then select it."})
        row = jobs.submit(project_id, goal, acceptance, key or f"auto-{uuid.uuid4()}")
        view = job_view(row, jobs.db_now())
    except GoalProjectStoreError as exc:
        raise HTTPException(503, {"error": exc.code, "hint": exc.hint}) from exc
    except jobs.GoalJobStoreError as exc:
        raise _store_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, {"error": "validation", "fields": ["idempotency_key"], "hint": str(exc)}) from exc
    return view


def read_job(job_id: str) -> dict[str, Any]:
    if not worker.enabled():
        raise HTTPException(404, {"error": "async_disabled", "hint": "async goal analysis is switched off"})
    try:
        row = jobs.get(job_id)
        if row is None:
            raise HTTPException(404, {"error": "not_found", "hint": "No such analysis job."})
        return job_view(row, jobs.db_now())
    except jobs.GoalJobStoreError as exc:
        raise _store_error(exc) from exc
