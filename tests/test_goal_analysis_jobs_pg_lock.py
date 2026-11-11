"""Goal job functions under a held row lock, on a real Postgres (UNI-3306 review r5).

Review r5: now() is the transaction start, so a write that waited on a row lock judged
expiry on a time from before the wait. The migration's rule is LOCK FIRST, THEN READ THE
CLOCK ONCE (goal_job_now()). These tests hold the row lock in another session until the
claim has expired, then require the waiting write to change nothing; and they hold the
migration text to the one-clock rule so the kind cannot come back by a new now().
Fixtures and the skip/require logic come from test_goal_analysis_jobs_pg.py.
"""
from __future__ import annotations

import re
import threading
import time

import pytest

from tests import goal_jobs_pg_helpers as pg
from tests import test_goal_analysis_jobs_pg as base

import psycopg  # noqa: E402  (after base, whose import applies the skip/require rule)
from psycopg.rows import dict_row  # noqa: E402

_call, _finish, _row, _seen_waiting_on_lock, _shift = (
    base._call, base._finish, base._row, base._seen_waiting_on_lock, base._shift)
# The same pytest fixtures, exposed here by name.
db, project, admin, svc, job = base.db, base.project, base.admin, base.svc, base.job

WRITES = {
    "finish": lambda c, j: _finish(c, j, 1),
    "fail": lambda c, j: _call(c, "goal_job_fail", j, 1, "late"),
    "heartbeat": lambda c, j: _call(c, "goal_job_heartbeat", j, 1, "mini"),
}


def _write_while_locked(db: str, job_id: str, write, hold_until_expired: bool) -> list[dict]:
    """Session A locks the row; the write runs in session B and must be SEEN waiting on the
    lock. A releases after the claim expiry (or at once), and B's result is returned."""
    out: list[list[dict]] = []
    a = psycopg.connect(db)
    b = psycopg.connect(db, autocommit=True, row_factory=dict_row)
    try:
        b.execute("set role service_role")
        expires = a.execute("select claim_expires_at from goal_analysis_jobs where id = %s for update",
                            (job_id,)).fetchone()[0]
        t = threading.Thread(target=lambda: out.append(write(b, job_id)))
        t.start()
        assert _seen_waiting_on_lock(db, b.info.backend_pid, t), "write did not wait on the row lock"
        if hold_until_expired:
            while a.execute("select clock_timestamp() <= %s", (expires,)).fetchone()[0]:
                time.sleep(0.05)
        a.commit()
        t.join(10)
        assert not t.is_alive(), "write never finished"
    finally:
        a.close()
        b.close()
    return out[0]


@pytest.mark.parametrize("name", sorted(WRITES))
def test_a_write_that_waited_past_the_claim_expiry_changes_nothing(db, svc, admin, job, name):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "claim_expires_at", "1 second")
    before = _row(admin, job)
    assert _write_while_locked(db, job, WRITES[name], hold_until_expired=True) == []
    after = _row(admin, job)
    assert (after["status"], after["claim_expires_at"], after["result"]) == (
        "running", before["claim_expires_at"], None)


def test_a_write_that_waited_while_still_live_succeeds(db, svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    [r] = _write_while_locked(db, job, WRITES["finish"], hold_until_expired=False)
    assert r["status"] == "finished"


def test_recovery_skips_a_row_being_written_then_takes_it(db, svc, admin, job):
    _call(svc, "goal_job_claim", job, "mini")
    _shift(admin, job, "claim_expires_at", "-10 seconds")
    with psycopg.connect(db) as a:
        a.execute("select 1 from goal_analysis_jobs where id = %s for update", (job,))
        svc.execute("set lock_timeout = '2s'")  # a recovery that waits fails here instead of hanging
        try:
            assert [r for r in _call(svc, "goal_job_recover") if str(r["id"]) == job] == []
        finally:
            svc.execute("reset lock_timeout")
    [r] = [r for r in _call(svc, "goal_job_recover") if str(r["id"]) == job]
    assert r["status"] == "interrupted"


def test_the_migrations_read_the_clock_only_in_goal_job_now():
    """The functions migration and the purge migration (FILES[1:]) share one clock owner."""
    code = "".join("\n".join(line.split("--", 1)[0] for line in
                             (pg.MIGRATIONS / name).read_text(encoding="utf-8").splitlines()) + "\n"
                   for name in pg.FILES[1:])
    banned = re.findall(r"\b(now\s*\(|current_timestamp|transaction_timestamp|statement_timestamp|localtimestamp)",
                        code, re.IGNORECASE)
    assert banned == []
    assert len(re.findall(r"clock_timestamp\s*\(", code)) == 1
    owner = re.search(r"FUNCTION goal_job_now\(\).*?\$\$(.*?)\$\$", code, re.DOTALL)
    assert owner and "clock_timestamp()" in owner.group(1)
