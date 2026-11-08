"""goal_analysis_jobs against a real, throwaway Postgres (UNI-3306 step 5, grill Q2, Q3, Q6).

Part 1, simultaneous submissions: two sessions insert the same goal for the same project
at the same moment. The partial unique index must make exactly one of them win: the
other blocks on the first session's uncommitted row and then fails with unique_violation.

Part 2, the job functions (migration 20261108T010000): claim, heartbeat, finish, fail
and recovery decide ownership on the database clock. Times are moved by rewriting the
row as the superuser, never by a client clock; the functions run as service_role.

Each run builds a NEW database holding the two goal job migrations from this checkout
(tests/goal_jobs_pg_helpers.py): on SCRATCH_DB_URL's server when set (pgtap-pilot.yml's
service container), otherwise on a cluster started here from local Postgres binaries.
It skips only when neither exists; GOAL_ANALYSIS_JOBS_PG_REQUIRED=1 turns that skip
into a failure. Never a remote database.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

import pytest

from tests import goal_jobs_pg_helpers as pg

SCRATCH = os.environ.get("SCRATCH_DB_URL", "")
BINS = None if SCRATCH else pg.bindir()
if not SCRATCH and not BINS:
    if os.environ.get("GOAL_ANALYSIS_JOBS_PG_REQUIRED") == "1":
        raise RuntimeError("GOAL_ANALYSIS_JOBS_PG_REQUIRED=1 but there is no SCRATCH_DB_URL and no "
                           "local postgres binary; refusing to skip")
    pytest.skip("needs SCRATCH_DB_URL or a local postgres server binary (initdb, pg_ctl)",
                allow_module_level=True)

import psycopg  # noqa: E402
from psycopg import errors  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

INSERT = (
    "insert into goal_analysis_jobs (project_id, goal, acceptance, goal_sha256, idempotency_key)"
    " values (%s, 'Finalise Stage 1', 'Tickets written', %s, %s)"
)


@pytest.fixture(scope="module")
def db():
    with pg.database(SCRATCH, BINS) as url:
        yield url


@pytest.fixture
def project(db):
    pid = f"race-{uuid.uuid4().hex[:12]}"
    yield pid
    with psycopg.connect(db, autocommit=True) as c:
        c.execute("delete from goal_analysis_jobs where project_id = %s", (pid,))


def _seen_waiting_on_lock(db: str, pid: int, worker: threading.Thread) -> bool:
    """Blocking is observed, never assumed from a sleep: a third session must see the
    backend `pid` waiting on a lock while the other session is still open (10 s bound).
    Once it waits it cannot finish before that session commits, so nothing else has been
    recorded yet. A worker that never waits (no index to collide on) finishes on its own."""
    with psycopg.connect(db, autocommit=True) as watch:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and worker.is_alive():
            row = watch.execute("select wait_event_type from pg_stat_activity where pid = %s",
                                (pid,)).fetchone()
            if row and row[0] == "Lock":
                return True
            time.sleep(0.02)
    return False


def _race(db: str, project_id: str, first_key: str, second_key: str, goal_hash_2: str) -> list[str]:
    """Session A inserts and holds its transaction open; session B inserts the
    competing row meanwhile. Returns what B saw: 'blocked' (observed in pg_stat_activity) while A was open, then
    'unique_violation' or 'inserted'."""
    seen: list[str] = []
    a = psycopg.connect(db)
    b = psycopg.connect(db)
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
        if _seen_waiting_on_lock(db, b.info.backend_pid, t):
            seen.append("blocked")
        a.commit()
        t.join(10)
        assert not t.is_alive(), "second session never finished"
    finally:
        a.close()
        b.close()
    return seen


def _count(db: str, project_id: str) -> int:
    with psycopg.connect(db) as c:
        return c.execute("select count(*) from goal_analysis_jobs where project_id = %s",
                         (project_id,)).fetchone()[0]


def test_two_simultaneous_submissions_of_one_goal_create_one_job(db, project):
    seen = _race(db, project, f"k-{uuid.uuid4().hex}", f"k-{uuid.uuid4().hex}", "a" * 64)
    assert seen == ["blocked", "unique_violation"]
    assert _count(db, project) == 1


def test_two_simultaneous_submissions_with_one_key_create_one_job(db, project):
    key = f"k-{uuid.uuid4().hex}"
    seen = _race(db, project, key, key, "b" * 64)
    assert seen == ["blocked", "unique_violation"]
    assert _count(db, project) == 1


def test_different_goals_submitted_together_both_succeed(db, project):
    seen = _race(db, project, f"k-{uuid.uuid4().hex}", f"k-{uuid.uuid4().hex}", "b" * 64)
    assert seen[-1] == "inserted"
    assert _count(db, project) == 2


# --- Part 2: the job functions, on the database clock ---------------------------------

_SIGS = ("goal_job_claim(%s::uuid, 'x')", "goal_job_heartbeat(%s::uuid, 1, 'x')",
         "goal_job_finish(%s::uuid, 1, '{}'::jsonb, '[]'::jsonb)", "goal_job_fail(%s::uuid, 1, 'x')",
         "goal_job_recover()", "goal_job_is_live(null::goal_analysis_jobs, 1)",
         "goal_job_retry_unused(null::goal_analysis_jobs)")


@pytest.fixture
def admin(db):
    with psycopg.connect(db, autocommit=True, row_factory=dict_row) as c:
        yield c


@pytest.fixture
def svc(db):
    with psycopg.connect(db, autocommit=True, row_factory=dict_row) as c:
        c.execute("set role service_role")
        yield c


@pytest.fixture
def job(admin, project) -> str:
    return str(admin.execute(INSERT + " returning id", (project, "c" * 64, f"k-{uuid.uuid4().hex}"))
               .fetchone()["id"])


def _call(conn, fn: str, *args) -> list[dict]:
    marks = ", ".join(["%s"] * len(args))
    return conn.execute(f"select * from {fn}({marks})", args).fetchall()


def _shift(admin, job_id: str, column: str, interval: str) -> None:
    """Move a timestamp relative to the DATABASE clock (now() + interval)."""
    assert column in ("claim_expires_at", "attempt_deadline")
    admin.execute(f"update goal_analysis_jobs set {column} = now() + %s::interval where id = %s",
                  (interval, job_id))


def _row(admin, job_id: str) -> dict:
    return admin.execute("select * from goal_analysis_jobs where id = %s", (job_id,)).fetchone()


def _finish(svc, job_id: str, attempt: int) -> list[dict]:
    return _call(svc, "goal_job_finish", job_id, attempt, Jsonb({"ok": True}), Jsonb(["https://linear.app/x"]))


def test_claim_twice_second_gets_no_row(svc, admin, job):
    first = _call(svc, "goal_job_claim", job, "mini")
    assert [(r["status"], r["attempt"], r["retry_count"], r["claimed_by"]) for r in first] == [
        ("running", 1, 0, "mini")]
    r = first[0]
    assert (r["claim_expires_at"] - r["started_at"]).total_seconds() == 60
    assert (r["attempt_deadline"] - r["started_at"]).total_seconds() == 300
    assert _call(svc, "goal_job_claim", job, "railway") == []
    assert _row(admin, job)["claimed_by"] == "mini"


def test_finish_by_the_live_attempt_wins(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    done = _finish(svc, job, 1)
    assert len(done) == 1 and done[0]["status"] == "finished" and done[0]["result"] == {"ok": True}
    assert done[0]["ended_at"] is not None and done[0]["claim_expires_at"] is None
    assert done[0]["evidence_links"] == ["https://linear.app/x"]


def test_writes_after_the_claim_expired_change_nothing(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "claim_expires_at", "-1 second")
    assert _finish(svc, job, 1) == []
    assert _call(svc, "goal_job_fail", job, 1, "late") == []
    assert _call(svc, "goal_job_heartbeat", job, 1, "mini") == []
    row = _row(admin, job)
    assert row["status"] == "running" and row["result"] is None


def test_writes_after_the_deadline_passed_change_nothing(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "attempt_deadline", "-1 second")
    assert _finish(svc, job, 1) == []
    assert _call(svc, "goal_job_fail", job, 1, "late") == []
    assert _call(svc, "goal_job_heartbeat", job, 1, "mini") == []
    assert _row(admin, job)["status"] == "running"


def test_a_stale_attempt_number_changes_nothing(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    for stale in (0, 2):
        assert _finish(svc, job, stale) == []
        assert _call(svc, "goal_job_fail", job, stale, "late") == []
        assert _call(svc, "goal_job_heartbeat", job, stale, "mini") == []
    assert _row(admin, job)["status"] == "running"


def _recovered(svc, job_id: str) -> list[dict]:
    return [r for r in _call(svc, "goal_job_recover") if str(r["id"]) == job_id]


def test_recovery_interrupts_once_then_fails(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "claim_expires_at", "-2 seconds")
    assert _recovered(svc, job) == []  # inside the 5 s recovery margin
    _shift(admin, job, "claim_expires_at", "-10 seconds")
    [r] = _recovered(svc, job)
    assert (r["status"], r["claimed_by"], r["claim_expires_at"], r["ended_at"]) == ("interrupted", None, None, None)
    [again] = _call(svc, "goal_job_claim", job, "railway")
    assert (again["attempt"], again["retry_count"]) == (2, 1)
    _shift(admin, job, "attempt_deadline", "-10 seconds")
    [r] = _recovered(svc, job)
    assert r["status"] == "failed" and r["failure_reason"] == "interrupted after its one retry"
    assert r["ended_at"] is not None
    assert _call(svc, "goal_job_claim", job, "mini") == []


def test_heartbeat_by_another_server_changes_nothing(svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "claim_expires_at", "10 seconds")
    before = _row(admin, job)["claim_expires_at"]
    assert _call(svc, "goal_job_heartbeat", job, 1, "railway") == []
    assert _row(admin, job)["claim_expires_at"] == before
    [r] = _call(svc, "goal_job_heartbeat", job, 1, "mini")
    assert r["claim_expires_at"] > before


@pytest.mark.parametrize("role", ["anon", "authenticated"])
@pytest.mark.parametrize("sig", _SIGS)
def test_anon_and_authenticated_cannot_execute(db, job, role, sig):
    with psycopg.connect(db, autocommit=True) as c:
        c.execute(f"set role {role}")
        with pytest.raises(errors.InsufficientPrivilege, match=r"permission denied for function goal_job_"):
            c.execute(f"select * from {sig}", (job,) if "%s" in sig else ())
