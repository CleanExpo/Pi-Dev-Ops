"""Async path of POST /api/goal-ticket/analyze and its status read (UNI-3306 PR 2).

Only used when GOAL_ANALYZE_ASYNC is on. Every store failure is an error response:
a failed read is never "not found", and unavailable async is never a silent inline run.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from .. import goal_analysis_jobs as jobs
from .. import goal_analysis_worker as worker
from ..goal_analyze import validate_analyze
from ..goal_projects import GoalProjectStoreError, get_project

_VIEW = ("id", "status", "attempt", "retry_count", "result", "failure_reason",
         "evidence_links", "created_at", "started_at", "ended_at")


def job_view(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row.get(key) for key in _VIEW}


def _unavailable() -> HTTPException:
    _usable, reason = worker.availability()
    return HTTPException(503, {"error": "async_unavailable", "hint": reason})


def _store_error(exc: jobs.GoalJobStoreError) -> HTTPException:
    status = 409 if isinstance(exc, jobs.KeyMismatch) else 503
    return HTTPException(status, {"error": exc.code, "hint": exc.hint})


def submit_job(goal: str, acceptance: str, project_id: str, key: str | None) -> dict[str, Any]:
    """Queue (or find) the job and start it. Raises HTTPException on every failure."""
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
    except GoalProjectStoreError as exc:
        raise HTTPException(503, {"error": exc.code, "hint": exc.hint}) from exc
    except jobs.GoalJobStoreError as exc:
        raise _store_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(400, {"error": "validation", "fields": ["idempotency_key"], "hint": str(exc)}) from exc
    if row["status"] == "queued":
        worker.launch(row["id"])  # a duplicate launch loses the claim, so one model call
    return job_view(row)


def read_job(job_id: str) -> dict[str, Any]:
    if not worker.enabled():
        raise HTTPException(404, {"error": "async_disabled", "hint": "async goal analysis is switched off"})
    try:
        row = jobs.get(job_id)
    except jobs.GoalJobStoreError as exc:
        raise _store_error(exc) from exc
    if row is None:
        raise HTTPException(404, {"error": "not_found", "hint": "No such analysis job."})
    return job_view(row)
