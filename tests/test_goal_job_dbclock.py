"""One database clock for every displayed age; all transport is fake."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from app.server import goal_analysis_jobs as jobs
from app.server.routes import goal_ticket_async as route
from tests.test_goal_ticket_async_view import ROW

NOW = datetime(2026, 11, 11, 0, 3, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize("offset", [61, -61])
@pytest.mark.parametrize("age", [0, 90])
def test_read_uses_database_clock_despite_app_skew(monkeypatch, offset, age):
    class AppClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW - timedelta(seconds=offset)
    monkeypatch.setattr(route, "datetime", AppClock)
    monkeypatch.setattr(route.worker, "enabled", lambda: True)
    row = {**ROW, "last_progress_at": (NOW - timedelta(seconds=age)).isoformat()}
    calls = []
    def request(method, path, data=None):
        calls.append(path)
        return json.dumps(NOW.isoformat() if path == "rpc/goal_job_now" else [row]).encode()
    monkeypatch.setattr(jobs, "_request", request)
    view = route.read_job(ROW["id"])
    assert view["last_progress_age_s"] == age
    assert view["elapsed_s"] == 180
    assert calls[-1] == "rpc/goal_job_now"


def test_duplicate_submit_reads_clock_after_row_in_same_thread(monkeypatch):
    import threading
    calls = []
    monkeypatch.setattr(route.worker, "availability", lambda: (True, ""))
    monkeypatch.setattr(route, "get_project", lambda _: {"id": "brief-1"})
    def submit(*args):
        calls.append(("row", threading.get_ident()))
        return dict(ROW)
    def request(method, path, data=None):
        assert (method, path) == ("POST", "rpc/goal_job_now")
        calls.append(("clock", threading.get_ident()))
        return json.dumps(NOW.isoformat()).encode()
    monkeypatch.setattr(jobs, "submit", submit)
    monkeypatch.setattr(jobs, "_request", request)
    view = asyncio.run(route.submit_job("a valid goal", "a valid acceptance", "brief-1", "key-123456"))
    assert view["elapsed_s"] == 180
    assert view["last_progress_age_s"] == 160
    assert [c[0] for c in calls] == ["row", "clock"]
    assert calls[0][1] == calls[1][1] != threading.get_ident()


@pytest.mark.parametrize("submit", [False, True])
def test_clock_failure_is_503(monkeypatch, submit):
    monkeypatch.setattr(route.worker, "enabled", lambda: True)
    monkeypatch.setattr(route.worker, "availability", lambda: (True, ""))
    monkeypatch.setattr(route, "get_project", lambda _: {"id": "brief-1"})
    monkeypatch.setattr(jobs, "get", lambda _: dict(ROW))
    monkeypatch.setattr(jobs, "submit", lambda *args: dict(ROW))
    def broken(*args):
        raise jobs.GoalJobStoreError("request_failed", "clock unavailable")
    monkeypatch.setattr(jobs, "_request", broken)
    with pytest.raises(HTTPException) as exc:
        if submit:
            asyncio.run(route.submit_job("a valid goal", "a valid acceptance", "brief-1", "key-123456"))
        else:
            route.read_job(ROW["id"])
    assert exc.value.status_code == 503


@pytest.mark.parametrize("body", [b"", b"null", b"[]", b"{}", b'"bad"', b'123', b'"2026-11-11"', b'"2026-11-11T00:00:00"', b'["2026-11-11T00:00:00Z"]'])
def test_db_now_rejects_invalid_reply(monkeypatch, body):
    monkeypatch.setattr(jobs, "_request", lambda *args: body)
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.db_now()


def test_db_now_and_queued_elapsed(monkeypatch):
    monkeypatch.setattr(jobs, "_request", lambda *args: b'"2026-11-11T00:03:01Z"')
    now = jobs.db_now()
    assert now == NOW
    assert route.job_view({**ROW, "started_at": None}, now=now)["elapsed_s"] == 181
