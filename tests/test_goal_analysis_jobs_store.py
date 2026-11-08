"""Goal analysis job store (UNI-3306 PR 1): fencing, one retry, links only.

The fake (tests/goal_jobs_helpers.py) applies PostgREST filters for real and runs the
rpc/<name> job functions with its own clock as the database clock, so the store can
never supply a time of its own. The SQL is proven on a real Postgres in
test_goal_analysis_jobs_pg.py.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import pytest

from app.server import goal_analysis_jobs as jobs
from tests.goal_jobs_helpers import FakeRest


@pytest.fixture
def rest(monkeypatch: pytest.MonkeyPatch) -> FakeRest:
    fake = FakeRest()
    monkeypatch.setattr(jobs, "_request", fake)
    return fake


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    real = jobs._request

    def spy(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        seen.append((method, path))
        return real(method, path, data)

    monkeypatch.setattr(jobs, "_request", spy)
    return seen


def _submit(key: str = "key-0001", goal: str = "Finalise Stage 1") -> dict[str, Any]:
    return jobs.submit("ra", goal, "Tickets written", key)


def test_goal_hash_ignores_whitespace_but_not_words() -> None:
    assert jobs.goal_sha256(" Finalise  Stage 1\n", "Done") == jobs.goal_sha256("Finalise Stage 1", "Done")
    assert jobs.goal_sha256("Finalise Stage 1", "Done") != jobs.goal_sha256("Finalise Stage 2", "Done")
    assert jobs.goal_sha256("a b", "c") != jobs.goal_sha256("a", "b c")


def test_duplicate_submit_returns_the_active_job(rest: FakeRest) -> None:
    first = _submit("key-0001")
    again = _submit("key-0002")
    same_key = _submit("key-0001")
    assert again["id"] == first["id"] == same_key["id"]
    assert len(rest.rows) == 1


def test_key_reused_for_another_goal_is_refused(rest: FakeRest) -> None:
    _submit("key-0001")
    with pytest.raises(jobs.KeyMismatch):
        _submit("key-0001", goal="Something else entirely")


def test_claim_fences_on_attempt(rest: FakeRest) -> None:
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    assert jobs.claim(job["id"], "railway") is None
    row = rest.rows[0]
    assert (row["status"], row["attempt"], row["claimed_by"]) == ("running", 1, "mini")


def test_two_servers_claim_once_with_no_read_before_the_write(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The old claim read the row, then wrote; a second server could act on the stale read.
    Now a claim is one conditional write, so there is no read for a second server to share."""
    job = _submit()
    seen = _spy(monkeypatch)
    assert jobs.claim(job["id"], "mini") == 1
    assert jobs.claim(job["id"], "railway") is None
    assert seen == [("POST", "rpc/goal_job_claim")] * 2
    assert rest.rows[0]["claimed_by"] == "mini"


def test_stale_attempt_cannot_write(rest: FakeRest) -> None:
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    rest.advance(120)
    assert jobs.recover_expired() == [job["id"]]
    assert jobs.claim(job["id"], "railway") == 2
    assert jobs.heartbeat(job["id"], 1, "mini") is False
    assert jobs.finish(job["id"], 1, {"drafts": []}, []) is False
    assert jobs.fail(job["id"], 1, "late") is False
    assert rest.rows[0]["status"] == "running" and rest.rows[0]["result"] is None
    assert jobs.finish(job["id"], 2, {"drafts": []}, ["https://linear.app/x"]) is True
    assert rest.rows[0]["status"] == "finished" and rest.rows[0]["ended_at"]


def test_one_retry_then_failed(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    rest.advance(120)
    jobs.recover_expired()
    assert rest.rows[0]["status"] == "interrupted"
    assert jobs.claim(job["id"], "mini") == 2
    assert rest.rows[0]["retry_count"] == 1
    rest.advance(120)
    jobs.recover_expired()
    assert rest.rows[0]["status"] == "failed"
    assert "retry" in rest.rows[0]["failure_reason"]
    assert jobs.claim(job["id"], "mini") is None


def test_heartbeat_extends_the_claim(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    rest.advance(50)
    assert jobs.heartbeat(job["id"], 1, "mini") is True
    rest.advance(50)
    assert jobs.recover_expired() == []


def test_renewal_inside_the_recovery_margin_wins(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A heartbeat at T0+57 renews the claim to T0+117; recovery at T0+120 (cutoff T0+115)
    must leave the job running, and recovery is one write with no separate read."""
    job = _submit()
    jobs.claim(job["id"], "mini")
    rest.advance(57)
    assert jobs.heartbeat(job["id"], 1, "mini") is True
    rest.advance(63)
    seen = _spy(monkeypatch)
    assert jobs.recover_expired() == []
    assert seen == [("POST", "rpc/goal_job_recover")]
    assert rest.rows[0]["status"] == "running"


@pytest.mark.parametrize("reply", [
    b"", b"oops", b"{}", b"null", b"[null]", b'[{"id": 1}]',
    b'[{"id": "x"}]', b'[{"id": "x", "status": "running", "attempt": "1", "retry_count": 0}]',
    b'[{"id": "x", "status": "running", "attempt": 1, "retry_count": 2}]',
])
def test_a_bad_reply_is_an_error_never_no_job(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch, reply: bytes) -> None:
    monkeypatch.setattr(jobs, "_request", lambda *_a, **_k: reply)
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.get("00000000-0000-0000-0000-000000000000")
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.recover_expired()
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.claim("00000000-0000-0000-0000-000000000000", "mini")
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.finish("00000000-0000-0000-0000-000000000000", 1, {}, [])
    if reply in (b"", b"oops", b"{}", b"null", b"[null]", b'[{"id": 1}]'):
        with pytest.raises(jobs.GoalJobStoreError):
            jobs.table_present()


def test_deadline_passed_is_recovered_even_with_fresh_heartbeat(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    for _ in range(7):
        rest.advance(50)
        jobs.heartbeat(job["id"], 1, "mini")
    assert jobs.recover_expired() == [job["id"]]


@pytest.mark.parametrize("link", [
    "raw source text pasted here", "https://example.com\nRAW_SOURCE_TEXT", "https://example.com\tx", "https://example.com\rx",
    "https://exa\x00mple.com", " https://example.com", "https://", "ftp://example.com", "example.com"])
def test_evidence_must_be_one_clean_link(rest: FakeRest, link: str) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    with pytest.raises(ValueError):
        jobs.finish(job["id"], 1, {"drafts": []}, [link])
    assert rest.rows[0]["status"] == "running"


def test_failed_needs_a_reason(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    with pytest.raises(ValueError):
        jobs.fail(job["id"], 1, "  ")


def test_missing_table_is_reported_not_empty(rest: FakeRest) -> None:
    rest.missing = True
    assert jobs.table_present() is False
    with pytest.raises(jobs.GoalJobStoreError):
        jobs.get("00000000-0000-0000-0000-000000000000")


def test_missing_functions_are_reported_not_present(rest: FakeRest) -> None:
    rest.functions_missing = True
    assert jobs.table_present() is False
    with pytest.raises(jobs.GoalJobStoreError) as exc:
        jobs.claim("00000000-0000-0000-0000-000000000000", "mini")
    assert exc.value.code == "function_missing"


def test_presence_probe_changes_nothing(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    before = [dict(r) for r in rest.rows]
    rest.advance(10)
    assert jobs.table_present() is True
    assert rest.rows == before


def test_filter_values_are_encoded(rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _spy(monkeypatch)
    assert jobs.get("a&status=eq.finished") is None
    assert jobs.claim("a&status=eq.finished", "mini") is None  # rpc: the id travels in the body
    paths = [p for _m, p in seen]
    assert all("a&status" not in p for p in paths)
    assert urlsplit("x?" + paths[0].partition("?")[2]).query
    assert paths[1] == "rpc/goal_job_claim"


def test_lapsed_claim_cannot_publish_before_recovery(rest: FakeRest) -> None:
    """Review r3: the claim lapsed (deadline still ahead) and recovery has not run yet."""
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    rest.advance(61)
    assert jobs.finish(job["id"], 1, {"ok": True}, []) is False
    assert jobs.fail(job["id"], 1, "late") is False
    assert jobs.heartbeat(job["id"], 1, "mini") is False
    assert rest.rows[0]["status"] == "running" and rest.rows[0]["result"] is None


def test_deadline_passed_with_live_claim_cannot_publish(rest: FakeRest) -> None:
    """The claim is kept fresh by heartbeats, but the attempt deadline has passed."""
    job = _submit()
    jobs.claim(job["id"], "mini")
    for _ in range(6):
        rest.advance(50)
        jobs.heartbeat(job["id"], 1, "mini")
    rest.advance(10)
    assert jobs.finish(job["id"], 1, {"ok": True}, []) is False
    assert rest.rows[0]["status"] == "running"
    assert jobs.recover_expired() == [job["id"]]


@pytest.mark.parametrize("write", ["finish", "fail", "heartbeat"])
def test_a_write_delayed_in_transit_past_expiry_loses(rest: FakeRest, write: str) -> None:
    """Review r4: sent with 1 s of claim left, applied 3 s later. The database clock decides."""
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    rest.advance(59)
    rest.transit = 3
    call = {"finish": lambda: jobs.finish(job["id"], 1, {"ok": True}, []),
            "fail": lambda: jobs.fail(job["id"], 1, "late"),
            "heartbeat": lambda: jobs.heartbeat(job["id"], 1, "mini")}[write]
    assert call() is False
    assert rest.rows[0]["status"] == "running" and rest.rows[0]["result"] is None


@pytest.mark.parametrize("reply", [b"[]", b'[{"id": "a", "status": "queued", "attempt": 0, "retry_count": 0}, '
                                        b'{"id": "b", "status": "queued", "attempt": 0, "retry_count": 0}]'])
def test_submit_needs_exactly_one_created_row(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch, reply: bytes) -> None:
    monkeypatch.setattr(jobs, "_request", lambda *_a, **_k: reply)
    with pytest.raises(jobs.GoalJobStoreError) as err:
        _submit()
    assert err.value.code == "bad_response"
    if reply != b"[]":  # one job id changes at most one row
        with pytest.raises(jobs.GoalJobStoreError):
            jobs.claim("a", "mini")
