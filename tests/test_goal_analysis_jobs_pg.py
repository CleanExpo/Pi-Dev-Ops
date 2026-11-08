"""Simultaneous submissions against a real, throwaway Postgres (UNI-3306 step 5, grill Q6).

Two sessions insert the same goal for the same project at the same moment. The
partial unique index must make exactly one of them win: the other blocks on the
first session's uncommitted row and then fails with unique_violation, so one
job exists and only one analysis can ever be started for it.

Runs in pgtap-pilot.yml's rls-assertions job after every migration is applied.
SCRATCH_DB_URL is that job's service container; a non-local URL is refused before
anything connects. Never a remote database.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import pytest

SCRATCH = os.environ.get("SCRATCH_DB_URL", "")
if not SCRATCH:
    if os.environ.get("GOAL_ANALYSIS_JOBS_PG_REQUIRED") == "1":
        raise RuntimeError("GOAL_ANALYSIS_JOBS_PG_REQUIRED=1 but SCRATCH_DB_URL is unset; refusing to skip")
    pytest.skip("needs an ephemeral Postgres in SCRATCH_DB_URL", allow_module_level=True)

import psycopg  # noqa: E402
from psycopg import errors  # noqa: E402

if urlsplit(SCRATCH).hostname not in {"localhost", "127.0.0.1"}:
    raise RuntimeError("SCRATCH_DB_URL must point at a local throwaway database")

INSERT = (
    "insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)"
    " values (%s, 'Finalise Stage 1', 'Tickets written', %s, %s)"
)


@pytest.fixture
def project():
    pid = f"race-{uuid.uuid4().hex[:12]}"
    yield pid
    with psycopg.connect(SCRATCH, autocommit=True) as c:
        c.execute("delete from goal_analysis_jobs where project_id = %s", (pid,))


def _seen_waiting_on_lock(pid: int, worker: threading.Thread) -> bool:
    """Blocking is observed, never assumed from a sleep: a third session must see the
    backend `pid` waiting on a lock while the other session is still open (10 s bound).
    Once it waits it cannot finish before that session commits, so nothing else has been
    recorded yet. A worker that never waits (no index to collide on) finishes on its own."""
    with psycopg.connect(SCRATCH, autocommit=True) as watch:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and worker.is_alive():
            row = watch.execute("select wait_event_type from pg_stat_activity where pid = %s",
                                (pid,)).fetchone()
            if row and row[0] == "Lock":
                return True
            time.sleep(0.02)
    return False


def _race(project_id: str, first_key: str, second_key: str, goal_hash_2: str) -> list[str]:
    """Session A inserts and holds its transaction open; session B inserts the
    competing row meanwhile. Returns what B saw: 'blocked' (observed in pg_stat_activity) while A was open, then
    'unique_violation' or 'inserted'."""
    seen: list[str] = []
    a = psycopg.connect(SCRATCH)
    b = psycopg.connect(SCRATCH)
    try:
        a.execute(INSERT, (project_id, "a" * 64, first_key))

        def second() -> None:
            try:
                b.execute(INSERT, (project_id, goal_hash_2, second_key))
                b.commit()
                seen.append("inserted")
            except errors.UniqueViolation:
                b.rollback()
                seen.append("unique_violation")

        t = threading.Thread(target=second)
        t.start()
        if _seen_waiting_on_lock(b.info.backend_pid, t):
            seen.append("blocked")
        a.commit()
        t.join(10)
        assert not t.is_alive(), "second session never finished"
    finally:
        a.close()
        b.close()
    return seen


def _count(project_id: str) -> int:
    with psycopg.connect(SCRATCH) as c:
        return c.execute("select count(*) from goal_analysis_jobs where project_id = %s",
                         (project_id,)).fetchone()[0]


def test_two_simultaneous_submissions_of_one_goal_create_one_job(project):
    seen = _race(project, f"k-{uuid.uuid4().hex}", f"k-{uuid.uuid4().hex}", "a" * 64)
    assert seen == ["blocked", "unique_violation"]
    assert _count(project) == 1


def test_two_simultaneous_submissions_with_one_key_create_one_job(project):
    key = f"k-{uuid.uuid4().hex}"
    seen = _race(project, key, key, "b" * 64)
    assert seen == ["blocked", "unique_violation"]
    assert _count(project) == 1


def test_different_goals_submitted_together_both_succeed(project):
    seen = _race(project, f"k-{uuid.uuid4().hex}", f"k-{uuid.uuid4().hex}", "b" * 64)
    assert seen[-1] == "inserted"
    assert _count(project) == 2
