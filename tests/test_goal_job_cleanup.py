"""Goal analysis job clean-up (UNI-3306 PR 3, grill 14 Q7): the store method, the batching
handler and the cron row, on the fake PostgREST (tests/goal_jobs_helpers.py). The SQL
function itself is proven on a real Postgres in test_goal_analysis_jobs_pg_purge.py.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.server import goal_analysis_cleanup as cleanup
from app.server import goal_analysis_jobs as jobs
from app.server.cron_fire_script import _command_for, _fire_script_trigger
from app.server.cron_handler_registry import resolve_handler
from app.server.cron_triggers import _matches
from tests.goal_jobs_helpers import FakeRest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rest(monkeypatch: pytest.MonkeyPatch) -> FakeRest:
    fake = FakeRest()
    monkeypatch.setattr(jobs, "_request", fake)
    return fake


def _row(rest: FakeRest, status: str, days_ago: float | None, name: str) -> dict[str, Any]:
    """A job row in `status`; ended `days_ago` days before the fake database clock."""
    ended = None if days_ago is None else (rest.now - timedelta(days=days_ago)).isoformat()
    row = {"id": name, "status": status, "attempt": 1, "retry_count": 0, "ended_at": ended}
    rest.rows.append(row)
    return row


def _ids(rest: FakeRest) -> set[str]:
    return {r["id"] for r in rest.rows}


def test_purge_deletes_old_finished_and_failed_and_keeps_the_rest(rest: FakeRest) -> None:
    _row(rest, "finished", 91, "old-finished")
    _row(rest, "failed", 91, "old-failed")
    _row(rest, "finished", 89, "new-finished")
    _row(rest, "failed", 89, "new-failed")
    for status in ("queued", "running", "interrupted"):
        _row(rest, status, None, f"active-{status}")
    assert jobs.purge_ended(100) == 2
    assert _ids(rest) == {"new-finished", "new-failed", "active-queued", "active-running", "active-interrupted"}


def test_purge_returns_zero_only_when_nothing_is_old_enough(rest: FakeRest) -> None:
    _row(rest, "finished", 89, "new")
    assert jobs.purge_ended(10) == 0
    assert _ids(rest) == {"new"}


def test_purge_sends_the_limit_and_the_limit_bounds_a_run(rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    for n in range(5):
        _row(rest, "finished", 100 + n, f"old-{n}")
    seen: list[tuple[str, str, Any]] = []
    real = jobs._request

    def spy(method: str, path: str, data: dict[str, Any] | None = None) -> bytes:
        seen.append((method, path, data))
        return real(method, path, data)

    monkeypatch.setattr(jobs, "_request", spy)
    assert jobs.purge_ended(2) == 2
    assert seen == [("POST", "rpc/goal_job_purge_ended", {"p_limit": 2})]
    assert len(rest.rows) == 3
    assert jobs.purge_ended(2) == 2 and jobs.purge_ended(2) == 1 and jobs.purge_ended(2) == 0


@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5, "5", None])
def test_purge_rejects_a_limit_outside_one_to_one_thousand(rest: FakeRest, limit: Any) -> None:
    _row(rest, "finished", 100, "old")
    with pytest.raises(ValueError):
        jobs.purge_ended(limit)
    assert _ids(rest) == {"old"}


def test_purge_raises_when_the_function_is_missing_never_zero(rest: FakeRest) -> None:
    _row(rest, "finished", 100, "old")
    rest.functions_missing = True
    with pytest.raises(jobs.GoalJobStoreError) as err:
        jobs.purge_ended(10)
    assert err.value.code == "function_missing"
    assert _ids(rest) == {"old"}


def test_purge_raises_when_the_table_is_missing(rest: FakeRest) -> None:
    rest.missing = True
    with pytest.raises(jobs.GoalJobStoreError) as err:
        jobs.purge_ended(10)
    assert err.value.code == "table_missing"


@pytest.mark.parametrize("raw", [b"", b"not json", b'{"id": "x"}', b'[{"no_id": 1}]', b'["a-bare-string"]',
                                 b'[{"id": "a"}, {"id": "b"}, {"id": "c"}]'])
def test_purge_raises_on_a_reply_it_cannot_count(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    """Empty, non-JSON, non-list, id-less and more-ids-than-limit replies are errors, not counts."""
    monkeypatch.setattr(jobs, "_request", lambda method, path, data=None: raw)
    with pytest.raises(jobs.GoalJobStoreError) as err:
        jobs.purge_ended(2)
    assert err.value.code == "bad_response"


def test_purge_all_due_runs_batches_until_one_is_not_full(rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cleanup, "BATCH", 2)
    for n in range(5):
        _row(rest, "finished", 100 + n, f"old-{n}")
    _row(rest, "queued", None, "active")
    assert cleanup.purge_all_due() == (5, False)
    assert _ids(rest) == {"active"}


def test_purge_all_due_is_capped_and_reports_the_backlog(rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cleanup, "BATCH", 2)
    monkeypatch.setattr(cleanup, "MAX_BATCHES", 3)
    for n in range(10):
        _row(rest, "failed", 100 + n, f"old-{n}")
    assert cleanup.purge_all_due() == (6, True)
    assert len(rest.rows) == 4


def test_purge_all_due_stops_at_the_first_failed_call(rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cleanup, "BATCH", 2)
    for n in range(4):
        _row(rest, "finished", 100 + n, f"old-{n}")
    rest.functions_missing = True
    with pytest.raises(jobs.GoalJobStoreError):
        cleanup.purge_all_due()


def test_main_prints_the_count_and_exits_zero(rest: FakeRest, capsys: pytest.CaptureFixture[str]) -> None:
    _row(rest, "finished", 100, "old")
    assert cleanup.main() == 0
    assert capsys.readouterr().out.strip() == "goal_job_cleanup deleted=1 backlog_left=False"


def test_main_exits_one_and_names_the_failure_on_stderr(rest: FakeRest, capsys: pytest.CaptureFixture[str]) -> None:
    """cron_fire_script logs a non-zero exit at ERROR with stderr: a failure must reach it and must not read as 'deleted 0'."""
    _row(rest, "finished", 100, "old")
    rest.functions_missing = True
    assert cleanup.main() == 1
    out = capsys.readouterr()
    assert "FAILED code=function_missing" in out.err
    assert "deleted=" not in out.out + out.err
    assert _ids(rest) == {"old"}


def test_the_configured_cron_row_is_daily_enabled_and_runs_this_module() -> None:
    raw = json.loads((REPO_ROOT / "config/harness/cron-triggers.json").read_text())
    rows = [t for t in (raw["triggers"] if isinstance(raw, dict) else raw) if t.get("id") == "goal-jobs-cleanup-daily"]
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "script" and row["enabled"] is True
    assert isinstance(row["hour"], int) and isinstance(row["minute"], int)
    fires = [(h, m) for h in range(24) for m in range(60) if _matches(dict(row), h, m)]
    assert fires == [(row["hour"], row["minute"])]
    assert resolve_handler("script") is _fire_script_trigger
    argv = _command_for(row["script"])
    assert argv[1:] == ["-m", "app.server.goal_analysis_cleanup"]
    # Never run it here: app/.env.local can point it at a real database. Check the entry point statically.
    assert importlib.util.find_spec(argv[-1]) is not None
    assert 'if __name__ == "__main__":\n    sys.exit(main())' in Path(cleanup.__file__).read_text()
