"""tests/goal_jobs_helpers.py — the fake PostgREST behind the goal analysis job store tests.

Table queries apply PostgREST filters for real (eq, in, lt, gt), so a query the store
forgets to filter changes the wrong rows and the test sees it. rpc/<name> calls apply
the SAME rules as the SQL functions in 20261108T010000, with this fake's clock as the
database clock; `live()` mirrors goal_job_is_live() and is the only copy of that rule
here. The SQL itself is proven against a real Postgres in test_goal_analysis_jobs_pg.py.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, unquote

from app.server import goal_analysis_jobs as jobs

T0 = datetime(2026, 11, 8, 10, 0, tzinfo=timezone.utc)
CLAIM, DEADLINE, MARGIN = 60, 300, 5  # the constants in the SQL migration
_ACTIVE = ("queued", "running")


def _t(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))


class FakeRest:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.missing = False
        self.functions_missing = False
        self.now = T0
        self.transit = 0  # seconds the NEXT request spends in transit before it is applied

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self, method: str, path: str, data: dict[str, Any] | None = None) -> bytes:
        if self.transit:
            self.advance(self.transit)
            self.transit = 0
        return json.dumps(self._handle(method, path, data)).encode()

    def _handle(self, method: str, path: str, data: dict[str, Any] | None) -> Any:
        if self.missing:
            raise jobs.GoalJobStoreError("table_missing", "no table")
        table, _, query = path.partition("?")
        if table.startswith("rpc/"):
            assert method == "POST" and not query
            if self.functions_missing:
                raise jobs.GoalJobStoreError("function_missing", "no function")
            return [dict(r) for r in getattr(self, "_" + table[4:])(**(data or {}))]
        assert table == "goal_analysis_jobs"
        filters = [(k, unquote(v)) for k, v in parse_qsl(query, keep_blank_values=True)
                   if k not in ("select", "limit", "order")]
        if method == "POST":
            return [self._insert(dict(data or {}))]
        hit = [r for r in self.rows if all(_match(r, k, v) for k, v in filters)]
        if method == "PATCH":
            for row in hit:
                row.update(json.loads(json.dumps(data)))
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
                   result=None, failure_reason=None, started_at=None, ended_at=None)
        row.setdefault("evidence_links", [])
        self.rows.append(row)
        return dict(row)

    def _at(self, seconds: float = 0) -> str:
        return (self.now + timedelta(seconds=seconds)).isoformat()

    def live(self, row: dict[str, Any], attempt: int) -> bool:
        """Mirror of goal_job_is_live(): running, this attempt, claim and deadline ahead."""
        return (row["status"] == "running" and row["attempt"] == attempt
                and _t(row["claim_expires_at"]) > self.now and _t(row["attempt_deadline"]) > self.now)

    def _by_id(self, p_id: str) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["id"] == p_id]

    def _goal_job_claim(self, p_id: str, p_server: str) -> list[dict[str, Any]]:
        out = []
        for r in self._by_id(p_id):
            if r["status"] == "queued" or (r["status"] == "interrupted" and r["retry_count"] < 1):
                r.update(retry_count=1 if r["status"] == "interrupted" else r["retry_count"],
                         status="running", attempt=r["attempt"] + 1, claimed_by=p_server,
                         claim_expires_at=self._at(CLAIM), attempt_deadline=self._at(DEADLINE),
                         started_at=r.get("started_at") or self._at(), last_progress_at=self._at())
                out.append(r)
        return out

    def _goal_job_heartbeat(self, p_id: str, p_attempt: int, p_server: str) -> list[dict[str, Any]]:
        out = [r for r in self._by_id(p_id) if self.live(r, p_attempt) and r["claimed_by"] == p_server]
        for r in out:
            r.update(claim_expires_at=self._at(CLAIM), last_progress_at=self._at())
        return out

    def _goal_job_finish(self, p_id: str, p_attempt: int, p_result: Any, p_links: Any) -> list[dict[str, Any]]:
        out = [r for r in self._by_id(p_id) if self.live(r, p_attempt)]
        for r in out:
            r.update(status="finished", result=p_result, evidence_links=p_links,
                     ended_at=self._at(), claim_expires_at=None)
        return out

    def _goal_job_fail(self, p_id: str, p_attempt: int, p_reason: str) -> list[dict[str, Any]]:
        out = [r for r in self._by_id(p_id) if self.live(r, p_attempt)]
        for r in out:
            r.update(status="failed", failure_reason=p_reason, ended_at=self._at(), claim_expires_at=None)
        return out

    def _goal_job_recover(self) -> list[dict[str, Any]]:
        cutoff = self.now - timedelta(seconds=MARGIN)
        out = [r for r in self.rows if r["status"] == "running" and (
            _t(r["claim_expires_at"]) < cutoff or _t(r["attempt_deadline"]) < cutoff)]
        for r in out:
            if r["retry_count"] < 1:
                r.update(status="interrupted", claimed_by=None, claim_expires_at=None)
            else:
                r.update(status="failed", failure_reason="interrupted after its one retry",
                         ended_at=self._at(), claim_expires_at=None)
        return out


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
