"""app/server/goal_analysis_cleanup.py — daily 90-day clean-up of goal analysis jobs (UNI-3306 PR 3).

Grill 14 Q7: finished and failed jobs are deleted 90 days after ended_at; active jobs are
never deleted by this. The cutoff is decided in SQL on the database clock
(goal_job_purge_ended, migration 20261108T020000); this module only calls it in bounded
batches.

Run as ``python -m app.server.goal_analysis_cleanup`` by the cron row
``goal-jobs-cleanup-daily`` (type ``script``): the in-process cron_loop on Railway starts
it once a day. The cron modules are frozen, so this uses the generic script trigger rather
than a new trigger type. Exit 0 prints the count; any store failure prints the reason to
stderr and exits 1, which cron_fire_script logs at ERROR. A failure is never "deleted 0".
"""
from __future__ import annotations

import sys

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


def main() -> int:
    try:
        total, backlog = purge_all_due()
    except jobs.GoalJobStoreError as exc:
        print(f"goal_job_cleanup FAILED code={exc.code}: {exc.hint}", file=sys.stderr)
        return 1
    print(f"goal_job_cleanup deleted={total} backlog_left={backlog}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
