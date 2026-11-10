"""UNI-3306 step 6: the job status read carries last_progress_at for the dashboard,
and still leaves out the claim internals."""
from datetime import datetime, timezone

from app.server.routes import goal_ticket_async as route

ROW = {
    "id": "0b6c2f8e-6f1e-4d55-9a57-2f3f6b7f1a10",
    "status": "running",
    "attempt": 1,
    "retry_count": 0,
    "result": None,
    "failure_reason": None,
    "evidence_links": [],
    "created_at": "2026-11-11T00:00:00+00:00",
    "started_at": "2026-11-11T00:00:01+00:00",
    "last_progress_at": "2026-11-11T00:00:21+00:00",
    "ended_at": None,
    # Never shown to the browser:
    "claimed_by": "server-a",
    "claim_expires_at": "2026-11-11T00:01:21+00:00",
    "attempt_deadline": "2026-11-11T00:05:01+00:00",
    "goal": "secret goal text",
    "acceptance": "acceptance text",
    "idempotency_key": "dash-key-123456",
    "goal_sha256": "0" * 64,
    "project_id": "brief-1",
}


def test_view_includes_last_progress_at():
    assert route.job_view(ROW)["last_progress_at"] == ROW["last_progress_at"]


def test_view_keys_are_exactly_the_public_fields():
    assert set(route.job_view(ROW)) == {
        "id", "status", "attempt", "retry_count", "result", "failure_reason",
        "evidence_links", "created_at", "started_at", "last_progress_at", "ended_at",
        "last_progress_age_s",
    }


def test_view_reports_progress_age_on_the_server_clock():
    # Review r1 P1: a duplicate submit can return a job already stalled for minutes;
    # the age must come from the server, not start at zero in the browser.
    now = datetime(2026, 11, 11, 0, 3, 21, tzinfo=timezone.utc)
    assert route.job_view(ROW, now=now)["last_progress_age_s"] == 180.0


def test_progress_age_is_none_when_absent_or_unreadable_and_never_negative():
    now = datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)
    assert route.job_view({**ROW, "last_progress_at": None}, now=now)["last_progress_age_s"] is None
    assert route.job_view({**ROW, "last_progress_at": "not a time"}, now=now)["last_progress_age_s"] is None
    assert route.job_view({**ROW, "last_progress_at": "2026-11-11T00:00:30Z"}, now=now)["last_progress_age_s"] == 0.0


def test_read_job_returns_last_progress_at(monkeypatch):
    monkeypatch.setattr(route.worker, "enabled", lambda: True)
    monkeypatch.setattr(route.jobs, "get", lambda job_id: dict(ROW) if job_id == ROW["id"] else None)
    view = route.read_job(ROW["id"])
    assert view["last_progress_at"] == ROW["last_progress_at"]
    assert "claimed_by" not in view and "goal" not in view
