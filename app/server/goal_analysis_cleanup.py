"""app/server/goal_analysis_cleanup.py — daily 90-day clean-up of goal analysis jobs (UNI-3306 PR 3).

Grill 14 Q7: finished and failed jobs are deleted 90 days after ended_at; active jobs are
never deleted by this. The cutoff is decided in SQL on the database clock
(goal_job_purge_ended, migration 20261108T020000); this module only calls it in bounded
batches. Cron entry: ``goal-jobs-cleanup-daily`` (type ``goal_job_cleanup``), run by the
in-process cron_loop on Railway.

A store failure is logged and re-raised, so the scheduler leaves last_fired_at unchanged
and boot catch-up retries. It is never reported as "deleted 0".
"""
from __future__ import annotations

import asyncio

from . import goal_analysis_jobs as jobs

BATCH = 500
MAX_BATCHES = 20  # at most 10,000 rows per run; a larger backlog continues tomorrow


def purge_all_due() -> tuple[int, bool]:
    """Delete due jobs in batches. Returns (rows deleted, backlog_left).

    backlog_left is True when every batch came back full, so more may be due.
    Raises GoalJobStoreError on the first failed call."""
    total = 0
    for _ in range(MAX_BATCHES):
        deleted = jobs.purge_ended(BATCH)
        total += deleted
        if deleted < BATCH:
            return total, False
    return total, True


async def _fire_goal_job_cleanup_trigger(trigger: dict, log) -> None:
    """Cron dispatcher hook. trigger = {type: 'goal_job_cleanup', ...}."""
    try:
        total, backlog = await asyncio.to_thread(purge_all_due)
    except jobs.GoalJobStoreError as exc:
        log.error("goal_job_cleanup id=%s FAILED code=%s: %s", trigger.get("id"), exc.code, exc.hint)
        raise
    log.info("goal_job_cleanup id=%s deleted=%d backlog_left=%s", trigger.get("id"), total, backlog)
