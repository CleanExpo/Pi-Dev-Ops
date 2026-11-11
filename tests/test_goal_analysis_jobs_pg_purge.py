"""goal_job_purge_ended on a real, throwaway Postgres (UNI-3306 PR 3, grill 14 Q7).

Finished and failed jobs are deleted 90 days after ended_at; queued, running and
interrupted jobs are never deleted by it; one call deletes at most p_limit rows. Ages are
set relative to the DATABASE clock (now() - interval) by the superuser, never a client
clock; the function runs as service_role. Fixtures and the skip/require rule come from
test_goal_analysis_jobs_pg.py, which also builds the database from all three migrations.
"""
from __future__ import annotations

import re
import uuid

import pytest

from tests import goal_jobs_pg_helpers as pg
from tests import test_goal_analysis_jobs_pg as base

import psycopg  # noqa: E402  (after base, whose import applies the skip/require rule)
from psycopg import errors  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

_call = base._call
db, project, admin, svc = base.db, base.project, base.admin, base.svc

_COLUMNS = {
    "finished": "result = '{}'::jsonb, ended_at = now() - %s::interval",
    "failed": "failure_reason = 'x', ended_at = now() - %s::interval",
    "queued": "created_at = now() - %s::interval",
    "interrupted": "created_at = now() - %s::interval",
    "running": ("attempt = 1, claimed_by = 'old-server', claim_expires_at = now() - %s::interval,"
                " attempt_deadline = now() - %s::interval"),
}


def _make(admin, project_id: str, status: str, age_days: int) -> str:
    """Insert a job (distinct goal hash, so no unique-index clash) and age it `age_days` days."""
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    job_id = str(admin.execute(base.INSERT + " returning id",
                               (project_id, sha, f"k-{uuid.uuid4().hex}")).fetchone()["id"])
    ages = (f"{age_days} days",) * _COLUMNS[status].count("%s")
    admin.execute(f"update goal_analysis_jobs set status = %s, {_COLUMNS[status]} where id = %s",
                  (status, *ages, job_id))
    return job_id


def _present(admin, ids: list[str]) -> set[str]:
    rows = admin.execute("select id::text from goal_analysis_jobs where id = any(%s::uuid[])", (ids,)).fetchall()
    return {r["id"] for r in rows}


def _purge(svc, limit: int) -> set[str]:
    return {str(r["id"]) for r in _call(svc, "goal_job_purge_ended", limit)}


def test_a_91_day_old_finished_and_failed_job_are_deleted_and_89_day_old_ones_kept(svc, admin, project):
    old = [_make(admin, project, s, 91) for s in ("finished", "failed")]
    new = [_make(admin, project, s, 89) for s in ("finished", "failed")]
    assert {i for i in _purge(svc, 1000) if i in old + new} == set(old)
    assert _present(admin, old) == set()
    assert _present(admin, new) == set(new)


@pytest.mark.parametrize("status", ["queued", "running", "interrupted"])
@pytest.mark.parametrize("age_days", [1, 91, 400])
def test_an_active_job_of_any_age_is_kept(svc, admin, project, status, age_days):
    job = _make(admin, project, status, age_days)
    assert job not in _purge(svc, 1000)
    assert _present(admin, [job]) == {job}


@pytest.mark.parametrize("status", ["queued", "running", "interrupted"])
def test_the_function_keeps_active_jobs_even_without_the_ended_at_constraint(db, project, status):
    """The table constraint goal_analysis_jobs_ended_iff_final already stops an active row having
    ended_at. This lifts it inside one rolled-back transaction, gives an active row a 400-day-old
    ended_at, and requires the function itself to keep it: its status filter is what is tested."""
    with psycopg.connect(db, row_factory=dict_row) as c:
        try:
            c.execute("alter table goal_analysis_jobs drop constraint goal_analysis_jobs_ended_iff_final")
            job = _make(c, project, status, 400)
            c.execute("update goal_analysis_jobs set ended_at = now() - interval '400 days' where id = %s", (job,))
            c.execute("set local role service_role")
            deleted = {str(r["id"]) for r in _call(c, "goal_job_purge_ended", 1000)}
            c.execute("reset role")
            assert job not in deleted
            assert _present(c, [job]) == {job}
        finally:
            c.rollback()


def test_the_limit_bounds_a_run_and_the_oldest_go_first(svc, admin, project):
    ages = [200, 190, 180, 170, 160]
    ids = [_make(admin, project, "finished", a) for a in ages]
    first = _purge(svc, 2)
    assert first == set(ids[:2])  # 200 and 190 days old
    assert len(_present(admin, ids)) == 3
    assert _purge(svc, 2) == set(ids[2:4])
    assert _purge(svc, 2) == {ids[4]}
    assert _purge(svc, 2) == set()


@pytest.mark.parametrize("limit", [0, -1, 1001, None])
def test_a_bad_limit_is_an_error_not_a_no_op(svc, admin, project, limit):
    job = _make(admin, project, "finished", 100)
    with pytest.raises(errors.InvalidParameterValue, match="p_limit must be between 1 and 1000"):
        svc.execute("select * from goal_job_purge_ended(%s)", (limit,))
    assert _present(admin, [job]) == {job}


def test_a_row_locked_by_another_session_is_skipped_then_taken(db, svc, admin, project):
    job = _make(admin, project, "finished", 100)
    with psycopg.connect(db) as a:
        a.execute("select 1 from goal_analysis_jobs where id = %s for update", (job,))
        svc.execute("set lock_timeout = '2s'")  # a purge that waits fails here instead of hanging
        try:
            assert job not in _purge(svc, 1000)
        finally:
            svc.execute("reset lock_timeout")
    assert job in _purge(svc, 1000)


@pytest.mark.parametrize("role", ["anon", "authenticated"])
def test_anon_and_authenticated_cannot_purge(db, project, admin, role):
    job = _make(admin, project, "finished", 100)
    with psycopg.connect(db, autocommit=True) as c:
        c.execute(f"set role {role}")
        with pytest.raises(errors.InsufficientPrivilege, match=r"permission denied for function goal_job_purge_ended"):
            c.execute("select * from goal_job_purge_ended(10)")
    assert _present(admin, [job]) == {job}


_NOW_SQL = ("create or replace function goal_job_now() returns timestamptz language sql volatile "
            "security invoker set search_path = public, pg_temp as $$ select {} $$")


@pytest.mark.parametrize("zone", ["America/Denver", "Australia/Sydney", "UTC"])
def test_the_cutoff_is_90_days_of_elapsed_time_in_any_session_time_zone(svc, admin, project, zone):
    """Review r1 P1: `- interval '90 days'` steps calendar days in the session TimeZone, so across a
    DST change a job 89 d 23 h 30 m old was deleted. The database clock is pinned for this test only."""
    admin.execute(_NOW_SQL.format("'2026-06-01 18:00:00+00'::timestamptz"))
    try:
        young = _make(admin, project, "finished", 1)
        old = _make(admin, project, "finished", 1)
        admin.execute("update goal_analysis_jobs set ended_at = %s where id = %s", ("2026-03-03 18:30:00+00", young))
        admin.execute("update goal_analysis_jobs set ended_at = %s where id = %s", ("2026-03-03 17:30:00+00", old))
        svc.execute(f"set time zone '{zone}'")
        deleted = _purge(svc, 1000)
        assert young not in deleted and old in deleted
        assert _present(admin, [young, old]) == {young}
    finally:
        admin.execute(_NOW_SQL.format("clock_timestamp()"))


def test_the_purge_migration_uses_no_calendar_interval():
    """The kind (calendar arithmetic that follows the session TimeZone) cannot come back by a new interval."""
    code = "\n".join(line.split("--", 1)[0] for line in
                     (pg.MIGRATIONS / pg.FILES[-1]).read_text(encoding="utf-8").splitlines())
    assert "goal_job_purge_ended" in code  # positive control: this is the purge migration
    assert not re.search(r"interval\s+'[^']*\b(day|days|week|weeks|month|months|year|years)\b", code, re.I)
