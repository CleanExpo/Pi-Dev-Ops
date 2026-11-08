"""Submit-then-check goal analysis jobs, stored in Supabase (UNI-3306 PR 1).

One row per job in goal_analysis_jobs (migration 20261108T000000). Decisions from
grill 14-pdo-goal-analyze-async:
- Every time-dependent write (claim, heartbeat, finish, fail, recovery) is ONE UPDATE
  inside a SQL function (migration 20261108T010000), called by PostgREST RPC, so the
  database clock decides ownership and stamps every expiry. No time used in an ownership
  decision or an expiry value is computed here: a worker's clock, or a write delayed in
  transit, cannot make a lapsed claim look live.
- Q2 fencing: claim sets attempt to the next number; heartbeat, finish and fail change
  the row only while goal_job_is_live() holds (that attempt, running, claim unexpired,
  deadline not passed). Otherwise they return False and the caller stops.
- Q2 one retry: an interrupted job can be claimed again once; after that,
  recover_expired() fails it. The table also refuses retry_count above 1.
- Q3 claim expiry and attempt deadline live on the row (60 s and 300 s, set in SQL).
- Q1 evidence is stored as links only, never source text.
- Q7 clean-up: purge_ended() calls goal_job_purge_ended (migration 20261108T020000), which
  deletes finished and failed jobs 90 days after ended_at, at most `limit` per call.

A failed read raises GoalJobStoreError; it never comes back as "no job".
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .supabase_log import _q

_TABLE = "goal_analysis_jobs"


class GoalJobStoreError(Exception):
    def __init__(self, code: str, hint: str) -> None:
        super().__init__(hint)
        self.code = code
        self.hint = hint


class KeyMismatch(GoalJobStoreError):
    def __init__(self) -> None:
        super().__init__("key_mismatch", "This submission key was already used for a different goal.")


def goal_sha256(goal: str, acceptance: str) -> str:
    """The one owner of the normalisation rule: whitespace runs collapse, words and case stay."""
    parts = [" ".join(str(goal).split()), " ".join(str(acceptance).split())]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


def _resource(path: str) -> str:
    """The table or rpc/<function> a request path names, for error codes and messages."""
    return path.partition("?")[0]


def _request(method: str, path: str, data: dict[str, Any] | None = None) -> bytes:
    """Raw response bytes. Never parsed here: _rows() is the only reader of a reply."""
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
    where = f"{method} {_resource(path)}"
    try:
        with urlopen(req, timeout=8) as resp:
            return resp.read()
    except HTTPError as exc:
        missing = "function_missing" if path.startswith("rpc/") else "table_missing"
        code = {404: missing, 409: "conflict"}.get(exc.code, "request_failed")
        raise GoalJobStoreError(code, f"{where} failed with HTTP {exc.code}.") from exc
    except OSError as exc:
        raise GoalJobStoreError("request_failed", f"{where} could not reach Supabase.") from exc


_STATUSES = {"queued", "running", "finished", "failed", "interrupted"}


def _bad(where: str, what: str) -> GoalJobStoreError:
    return GoalJobStoreError("bad_response", f"{where} returned {what}.")


def _job_row(row: Any, where: str) -> dict[str, Any]:
    if not isinstance(row, dict) or not isinstance(row.get("id"), str):
        raise _bad(where, "a row without an id")
    attempt, retries = row.get("attempt"), row.get("retry_count")
    if (row.get("status") not in _STATUSES or type(attempt) is not int or attempt < 0
            or type(retries) is not int or retries not in (0, 1)):
        raise _bad(where, "a row without a valid status, attempt or retry count")
    return row


def _rows(method: str, path: str, data: dict[str, Any] | None = None,
          id_only: bool = False, exactly_one: bool = False) -> list[dict[str, Any]]:
    """The one reader of every reply, for table queries and rpc/<function> calls alike.
    Empty, non-JSON, non-list or incomplete rows all raise, so a failed or truncated read
    can never look like "no job", "not owned" or "nothing to recover"."""
    where = f"{method} {_resource(path)}"
    raw = _request(method, path, data)
    if not raw:
        raise _bad(where, "an empty body")
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise _bad(where, "a body that is not JSON") from exc
    if not isinstance(body, list):
        raise _bad(where, "no row list")
    if exactly_one and len(body) != 1:
        raise _bad(where, f"{len(body)} rows where exactly one was expected")
    if id_only:
        if not all(isinstance(r, dict) and isinstance(r.get("id"), str) for r in body):
            raise _bad(where, "a row without an id")
        return body
    return [_job_row(r, where) for r in body]


_NIL_ID = "00000000-0000-0000-0000-000000000000"


def _table(query: str) -> str:
    return f"{_TABLE}?{query}"


def _rpc_one(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """One job-writing function on one job id: the changed row, or None when nothing changed."""
    changed = _rows("POST", f"rpc/{name}", args)
    if len(changed) > 1:
        raise _bad(f"POST rpc/{name}", f"{len(changed)} rows for one job")
    return changed[0] if changed else None


def table_present() -> bool:
    """True only when the table AND its job functions exist (workers need both).

    The functions are created together in one migration transaction, so one probe proves
    them all: a heartbeat on the nil id with attempt 0 can never match a row (attempts
    start at 1), so it changes nothing.
    """
    try:
        _rows("GET", _table("select=id&limit=1"), id_only=True)
        _rows("POST", "rpc/goal_job_heartbeat", {"p_id": _NIL_ID, "p_attempt": 0, "p_server": ""})
    except GoalJobStoreError as exc:
        if exc.code in ("table_missing", "function_missing"):
            return False
        raise
    return True


def get(job_id: str) -> dict[str, Any] | None:
    found = _rows("GET", _table(f"id=eq.{_q(job_id)}&limit=1"))
    return found[0] if found else None


def runnable_ids() -> list[str]:
    """Jobs a worker could claim now: queued, or interrupted with the retry unused.
    The recovery loop uses this so a job whose server died before claiming is not lost."""
    rows = _rows("GET", _table("status=in.(queued,interrupted)&order=created_at.asc&limit=50"))
    return [r["id"] for r in rows if r["status"] == "queued" or r["retry_count"] < 1]


def _active_for(project_id: str, sha: str) -> dict[str, Any] | None:
    query = (f"project_id=eq.{_q(project_id)}&goal_sha256=eq.{sha}"
             "&status=in.(queued,running,interrupted)&order=created_at.desc")
    for row in _rows("GET", _table(query)):
        if row["status"] != "interrupted" or row["retry_count"] < 1:
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
        return _rows("POST", _table("select=*"), row, exactly_one=True)[0]
    except GoalJobStoreError as exc:
        if exc.code != "conflict":
            raise
    by_key = _rows("GET", _table(f"idempotency_key=eq.{_q(key)}&limit=1"))
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
    row = _rpc_one("goal_job_claim", {"p_id": job_id, "p_server": server})
    return row["attempt"] if row else None


def _is_link(link: Any) -> bool:
    """Allow-list: one plain http(s) URL with a host. The raw string is checked BEFORE parsing,
    because urlsplit silently drops tabs and newlines and would let embedded text through."""
    if not isinstance(link, str) or not link or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in link):
        return False
    parts = urlsplit(link)
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def heartbeat(job_id: str, attempt: int, server: str) -> bool:
    args = {"p_id": job_id, "p_attempt": int(attempt), "p_server": server}
    return _rpc_one("goal_job_heartbeat", args) is not None


def finish(job_id: str, attempt: int, result: dict[str, Any], evidence_links: list[str]) -> bool:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    for link in evidence_links:
        if not _is_link(link):
            raise ValueError("evidence must be links, never source text")
    args = {"p_id": job_id, "p_attempt": int(attempt), "p_result": result,
            "p_links": list(evidence_links)}
    return _rpc_one("goal_job_finish", args) is not None


def fail(job_id: str, attempt: int, reason: str) -> bool:
    if not str(reason).strip():
        raise ValueError("a failed job needs a reason")
    args = {"p_id": job_id, "p_attempt": int(attempt), "p_reason": str(reason).strip()[:2000]}
    return _rpc_one("goal_job_fail", args) is not None


def recover_expired() -> list[str]:
    """Running jobs whose claim lapsed or deadline passed: interrupted once, then failed.
    One UPDATE on the database clock, so there is no read-then-write window to race."""
    return [str(row["id"]) for row in _rows("POST", "rpc/goal_job_recover", {})]


PURGE_MAX_LIMIT = 1000  # the SQL function's own ceiling


def purge_ended(limit: int) -> int:
    """Delete finished and failed jobs 90 days past ended_at, at most `limit` rows.

    Returns how many rows the database reports it deleted. Any failed call raises
    GoalJobStoreError (function_missing, table_missing, request_failed, bad_response);
    it never comes back as 0, because 0 means "nothing was old enough"."""
    if type(limit) is not int or not 1 <= limit <= PURGE_MAX_LIMIT:
        raise ValueError(f"limit must be an integer from 1 to {PURGE_MAX_LIMIT}")
    deleted = _rows("POST", "rpc/goal_job_purge_ended", {"p_limit": limit}, id_only=True)
    if len(deleted) > limit:
        raise _bad("POST rpc/goal_job_purge_ended", f"{len(deleted)} ids for a limit of {limit}")
    return len(deleted)
