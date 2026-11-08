"""Goal analysis job store (UNI-3306 PR 1): fencing, one retry, links only.

The fake below applies PostgREST filters for real (eq, in, lt, gt), so a write the
store forgets to filter on attempt changes the row and the test sees it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

import pytest

from app.server import goal_analysis_jobs as jobs

T0 = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
_ACTIVE = ("queued", "running")


class FakeRest:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.missing = False

    def __call__(self, method: str, path: str, data: dict[str, Any] | None = None) -> bytes:
        return json.dumps(self._handle(method, path, data)).encode()

    def _handle(self, method: str, path: str, data: dict[str, Any] | None) -> Any:
        if self.missing:
            raise jobs.GoalJobStoreError("table_missing", "no table")
        table, _, query = path.partition("?")
        assert table == "goal_analysis_jobs"
        filters = [(k, unquote(v)) for k, v in parse_qsl(query, keep_blank_values=True)
                   if k not in ("select", "limit", "order")]
        if method == "POST":
            return [self._insert(dict(data or {}))]
        hit = [r for r in self.rows if all(_match(r, k, v) for k, v in filters)]
        if method == "PATCH":
            for row in hit:
                row.update(json.loads(json.dumps(data)))
        if method == "DELETE":
            self.rows = [r for r in self.rows if r not in hit]
        return [dict(r) for r in hit]

    def _insert(self, row: dict[str, Any]) -> dict[str, Any]:
        for other in self.rows:
            same_key = other["idempotency_key"] == row["idempotency_key"]
            active = other["status"] in _ACTIVE or (
                other["status"] == "interrupted" and other["retry_count"] < 1)
            same_goal = (other["project_id"], other["goal_sha256"]) == (
                row["project_id"], row["goal_sha256"])
            if same_key or (active and same_goal):
                raise jobs.GoalJobStoreError("conflict", "409")
        row.update(id=str(uuid.uuid4()), status="queued", attempt=0, retry_count=0,
                   claimed_by=None, claim_expires_at=None, attempt_deadline=None,
                   result=None, failure_reason=None, ended_at=None)
        row.setdefault("evidence_links", [])
        self.rows.append(row)
        return dict(row)


def _match(row: dict[str, Any], key: str, cond: str) -> bool:
    op, _, val = cond.partition(".")
    have = row.get(key)
    if op == "eq":
        return str(have if not isinstance(have, bool) else str(have).lower()) == val
    if op == "in":
        return str(have) in val.strip("()").split(",")
    if op == "lt":
        return have is not None and datetime.fromisoformat(str(have)) < datetime.fromisoformat(val)
    if op == "gt":
        return have is not None and datetime.fromisoformat(str(have)) > datetime.fromisoformat(val)
    if op == "is":
        return have is None if val == "null" else False
    raise AssertionError(f"unsupported filter {key}={cond}")


@pytest.fixture
def rest(monkeypatch: pytest.MonkeyPatch) -> FakeRest:
    fake = FakeRest()
    clock = {"now": T0}
    monkeypatch.setattr(jobs, "_request", fake)
    monkeypatch.setattr(jobs, "_now", lambda: clock["now"])
    fake.clock = clock  # type: ignore[attr-defined]
    return fake


def _advance(rest: FakeRest, seconds: int) -> None:
    rest.clock["now"] = rest.clock["now"] + timedelta(seconds=seconds)  # type: ignore[attr-defined]


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


def test_two_servers_reading_the_same_row_claim_once(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _submit()
    stale = dict(rest.rows[0])
    assert jobs.claim(job["id"], "mini") == 1
    monkeypatch.setattr(jobs, "get", lambda _id: dict(stale))
    assert jobs.claim(job["id"], "railway") is None
    assert rest.rows[0]["claimed_by"] == "mini"


def test_stale_attempt_cannot_write(rest: FakeRest) -> None:
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    _advance(rest, 120)
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
    _advance(rest, 120)
    jobs.recover_expired()
    assert rest.rows[0]["status"] == "interrupted"
    assert jobs.claim(job["id"], "mini") == 2
    assert rest.rows[0]["retry_count"] == 1
    _advance(rest, 120)
    jobs.recover_expired()
    assert rest.rows[0]["status"] == "failed"
    assert "retry" in rest.rows[0]["failure_reason"]
    assert jobs.claim(job["id"], "mini") is None


def test_heartbeat_extends_the_claim(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    _advance(rest, 50)
    assert jobs.heartbeat(job["id"], 1, "mini") is True
    _advance(rest, 50)
    assert jobs.recover_expired() == []


def test_heartbeat_between_recovery_read_and_write_wins(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    _advance(rest, 120)
    real = jobs._request
    fired: list[bool] = []

    def interleave(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        if method == "PATCH" and not fired and "claim_expires_at=lt" in path:
            fired.append(True)
            # The worker's clock runs ~60 s behind: to it the claim (T0+60) is still live,
            # and its renewal (T0+117) lands past the recovering server's cutoff (T0+115).
            recovering_now = rest.clock["now"]  # type: ignore[attr-defined]
            rest.clock["now"] = T0 + timedelta(seconds=57)  # type: ignore[attr-defined]
            assert jobs.heartbeat(job["id"], 1, "mini") is True
            rest.clock["now"] = recovering_now  # type: ignore[attr-defined]
        return real(method, path, data)

    monkeypatch.setattr(jobs, "_request", interleave)
    assert jobs.recover_expired() == []
    assert fired and rest.rows[0]["status"] == "running"


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
    if reply in (b"", b"oops", b"{}", b"null", b"[null]", b'[{"id": 1}]'):
        with pytest.raises(jobs.GoalJobStoreError):
            jobs.table_present()


def test_deadline_passed_is_recovered_even_with_fresh_heartbeat(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    for _ in range(7):
        _advance(rest, 50)
        jobs.heartbeat(job["id"], 1, "mini")
    assert jobs.recover_expired() == [job["id"]]


def test_only_links_are_stored_as_evidence(rest: FakeRest) -> None:
    job = _submit()
    jobs.claim(job["id"], "mini")
    with pytest.raises(ValueError):
        jobs.finish(job["id"], 1, {"drafts": []}, ["raw source text pasted here"])
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


def test_filter_values_are_encoded(rest: FakeRest) -> None:
    seen: list[str] = []
    real = jobs._request

    def spy(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
        seen.append(path)
        return real(method, path, data)

    jobs._request = spy  # type: ignore[assignment]
    try:
        jobs.claim("a&status=eq.finished", "mini")
    finally:
        jobs._request = real  # type: ignore[assignment]
    assert all("a&status" not in p for p in seen)
    assert urlsplit("x?" + seen[0].partition("?")[2]).query


def test_lapsed_claim_cannot_publish_before_recovery(rest: FakeRest) -> None:
    """Review r3: the claim lapsed (deadline still ahead) and recovery has not run yet."""
    job = _submit()
    assert jobs.claim(job["id"], "mini") == 1
    _advance(rest, jobs.CLAIM_SECONDS + 1)
    assert jobs.finish(job["id"], 1, {"ok": True}, []) is False
    assert jobs.fail(job["id"], 1, "late") is False
    assert jobs.heartbeat(job["id"], 1, "mini") is False
    assert rest.rows[0]["status"] == "running" and rest.rows[0]["result"] is None


def test_deadline_passed_with_live_claim_cannot_publish(rest: FakeRest) -> None:
    """The claim is kept fresh by heartbeats, but the attempt deadline has passed."""
    job = _submit()
    jobs.claim(job["id"], "mini")
    for _ in range(6):
        _advance(rest, 50)
        jobs.heartbeat(job["id"], 1, "mini")
    _advance(rest, 10)
    assert jobs.finish(job["id"], 1, {"ok": True}, []) is False
    assert rest.rows[0]["status"] == "running"
    assert jobs.recover_expired() == [job["id"]]


@pytest.mark.parametrize("reply", [b"[]", b'[{"id": "a", "status": "queued", "attempt": 0, "retry_count": 0}, '
                                        b'{"id": "b", "status": "queued", "attempt": 0, "retry_count": 0}]'])
def test_submit_needs_exactly_one_created_row(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch, reply: bytes) -> None:
    monkeypatch.setattr(jobs, "_request", lambda *_a, **_k: reply)
    with pytest.raises(jobs.GoalJobStoreError) as err:
        _submit()
    assert err.value.code == "bad_response"
