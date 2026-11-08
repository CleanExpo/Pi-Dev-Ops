"""Submit-then-check goal analysis jobs, stored in Supabase (UNI-3306 PR 1).

One row per job in goal_analysis_jobs (migration 20261108T000000). Decisions from
grill 14-pdo-goal-analyze-async:
- Q2 fencing: claim() sets attempt to the next number; every later write filters on
  that attempt and the running status, so a server whose claim was taken over
  changes nothing (the write returns False and the caller stops).
- Q2 one retry: an interrupted job can be claimed again once; after that,
  recover_expired() fails it. The table also refuses retry_count above 1.
- Q3 claim expiry and attempt deadline live on the row.
- Q1 evidence is stored as links only, never source text.

A failed read raises GoalJobStoreError; it never comes back as "no job".
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .supabase_log import _q

_TABLE = "goal_analysis_jobs"
CLAIM_SECONDS = 60
ATTEMPT_SECONDS = 300
# Servers' clocks differ a little; a claim is only treated as expired this long after
# its recorded expiry.
SKEW_SECONDS = 5


class GoalJobStoreError(Exception):
    def __init__(self, code: str, hint: str) -> None:
        super().__init__(hint)
        self.code = code
        self.hint = hint


class KeyMismatch(GoalJobStoreError):
    def __init__(self) -> None:
        super().__init__("key_mismatch", "This submission key was already used for a different goal.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def goal_sha256(goal: str, acceptance: str) -> str:
    """The one owner of the normalisation rule: whitespace runs collapse, words and case stay."""
    parts = [" ".join(str(goal).split()), " ".join(str(acceptance).split())]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


def _request(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    from .supabase_log import _cfg

    url, key = _cfg()
    if not url or not key:
        raise GoalJobStoreError("supabase_not_configured", "Supabase is not configured.")
    req = Request(
        f"{url}/rest/v1/{path}",
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "apikey": key,
                 "Authorization": f"Bearer {key}", "Prefer": "return=representation",
                 "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read() or b"[]")
    except HTTPError as exc:
        code = {404: "table_missing", 409: "conflict"}.get(exc.code, "request_failed")
        raise GoalJobStoreError(code, f"{method} {_TABLE} failed with HTTP {exc.code}.") from exc
    except OSError as exc:
        raise GoalJobStoreError("request_failed", f"{method} {_TABLE} could not reach Supabase.") from exc


def _rows(method: str, query: str, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    body = _request(method, f"{_TABLE}?{query}", data)
    if not isinstance(body, list):
        raise GoalJobStoreError("bad_response", f"{method} {_TABLE} returned no row list.")
    if not all(isinstance(row, dict) for row in body):
        raise GoalJobStoreError("bad_response", f"{method} {_TABLE} returned a malformed row.")
    return body


def table_present() -> bool:
    try:
        _rows("GET", "select=id&limit=1")
    except GoalJobStoreError as exc:
        if exc.code == "table_missing":
            return False
        raise
    return True


def get(job_id: str) -> dict[str, Any] | None:
    found = _rows("GET", f"id=eq.{_q(job_id)}&limit=1")
    return found[0] if found else None


def _active_for(project_id: str, sha: str) -> dict[str, Any] | None:
    query = (f"project_id=eq.{_q(project_id)}&goal_sha256=eq.{sha}"
             "&status=in.(queued,running,interrupted)&order=created_at.desc")
    for row in _rows("GET", query):
        if row.get("status") != "interrupted" or int(row.get("retry_count") or 0) < 1:
            return row
    return None


def submit(project_id: str, goal: str, acceptance: str, key: str) -> dict[str, Any]:
    """Create a queued job, or return the job this key or this goal already has."""
    if not 8 <= len(key) <= 200:
        raise ValueError("idempotency key must be 8 to 200 characters")
    sha = goal_sha256(goal, acceptance)
    row = {"project_id": project_id, "goal": goal, "acceptance": acceptance,
           "goal_sha256": sha, "idempotency_key": key}
    try:
        return _rows("POST", "select=*", row)[0]
    except GoalJobStoreError as exc:
        if exc.code != "conflict":
            raise
    by_key = _rows("GET", f"idempotency_key=eq.{_q(key)}&limit=1")
    if by_key:
        if (by_key[0].get("goal_sha256"), by_key[0].get("project_id")) != (sha, project_id):
            raise KeyMismatch()
        return by_key[0]
    active = _active_for(project_id, sha)
    if active is None:
        raise GoalJobStoreError("conflict_unresolved", "The job conflicted but no matching job was found.")
    return active


def claim(job_id: str, server: str) -> int | None:
    """Take a queued job, or an interrupted one with its retry unused. Returns the new attempt."""
    row = get(job_id)
    if row is None:
        return None
    status, retries = row.get("status"), int(row.get("retry_count") or 0)
    if status == "interrupted" and retries < 1:
        retries = 1
    elif status != "queued":
        return None
    old, now = int(row.get("attempt") or 0), _now()
    changed = _rows("PATCH", f"id=eq.{_q(job_id)}&attempt=eq.{old}&status=eq.{status}", {
        "status": "running", "attempt": old + 1, "retry_count": retries, "claimed_by": server,
        "claim_expires_at": _iso(now + timedelta(seconds=CLAIM_SECONDS)),
        "attempt_deadline": _iso(now + timedelta(seconds=ATTEMPT_SECONDS)),
        "started_at": row.get("started_at") or _iso(now), "last_progress_at": _iso(now)})
    return old + 1 if changed else None


def _fenced(job_id: str, attempt: int) -> str:
    return f"id=eq.{_q(job_id)}&attempt=eq.{int(attempt)}&status=eq.running"


def heartbeat(job_id: str, attempt: int, server: str) -> bool:
    now = _now()
    return bool(_rows("PATCH", f"{_fenced(job_id, attempt)}&claimed_by=eq.{_q(server)}", {
        "claim_expires_at": _iso(now + timedelta(seconds=CLAIM_SECONDS)),
        "last_progress_at": _iso(now)}))


def finish(job_id: str, attempt: int, result: dict[str, Any], evidence_links: list[str]) -> bool:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    for link in evidence_links:
        if not (isinstance(link, str) and link.startswith(("https://", "http://")) and " " not in link):
            raise ValueError("evidence must be links, never source text")
    return bool(_rows("PATCH", _fenced(job_id, attempt), {
        "status": "finished", "result": result, "evidence_links": list(evidence_links),
        "ended_at": _iso(_now()), "claim_expires_at": None}))


def fail(job_id: str, attempt: int, reason: str) -> bool:
    if not str(reason).strip():
        raise ValueError("a failed job needs a reason")
    return bool(_rows("PATCH", _fenced(job_id, attempt), {
        "status": "failed", "failure_reason": str(reason).strip()[:2000],
        "ended_at": _iso(_now()), "claim_expires_at": None}))


def recover_expired() -> list[str]:
    """Running jobs whose claim lapsed or deadline passed: interrupted once, then failed."""
    cutoff = _q(_iso(_now() - timedelta(seconds=SKEW_SECONDS)))
    # The PATCH repeats the expiry test that found the row, so a heartbeat that renews the
    # claim between this read and the write makes the write change nothing.
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    for column in ("attempt_deadline", "claim_expires_at"):
        for row in _rows("GET", f"status=eq.running&{column}=lt.{cutoff}"):
            found.setdefault(str(row["id"]), (column, row))
    recovered: list[str] = []
    for job_id, (column, row) in found.items():
        if int(row.get("retry_count") or 0) < 1:
            change = {"status": "interrupted", "claimed_by": None, "claim_expires_at": None}
        else:
            change = {"status": "failed", "failure_reason": "interrupted after its one retry",
                      "ended_at": _iso(_now()), "claim_expires_at": None}
        still_expired = f"{_fenced(job_id, int(row.get('attempt') or 0))}&{column}=lt.{cutoff}"
        if _rows("PATCH", still_expired, change):
            recovered.append(job_id)
    return recovered
