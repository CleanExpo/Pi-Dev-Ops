"""mesh_queue_cache.py — one Linear read of the mesh queue, shared by every claim (RA-7910).

WHY. Every `POST /api/mesh/claim/self` used to read the whole claimable queue
from Linear: ~10 pages of 25 tickets, each page one request. Two runners poll
every ~40 s, so claiming alone spent ~1,800 requests an hour from one key whose
budget is 2,500 an hour shared with every other Pi-CEO feature. Once it ran out
Linear answered every page with HTTP 400 "Rate limit exceeded", the read came
back incomplete, and every claim was a 503 — the fleet could not take any work.

WHAT. The queue is read once and served to every caller for `TTL_S` (90 s). One
read at a time: a second caller waits for the first rather than starting its own.
A failed read backs off for `BACKOFF_S` (120 s) and raises IncompleteRead without
touching Linear, so a rate-limited key is not hammered back into the limit.

WHY STALENESS IS SAFE. claim_self re-filters every candidate against the claim
table on each call (open claims, claims in the last 24 h, failures on this host),
and the `mesh_work_claims_one_open` unique index rejects a racing double claim
with 409. A cached ticket that someone else just took is skipped, not re-taken.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
from typing import Any, Callable, Iterable, Iterator

from . import mesh_lanes

TTL_S = float(os.environ.get("MESH_QUEUE_CACHE_TTL_S", "90"))
BACKOFF_S = float(os.environ.get("MESH_QUEUE_BACKOFF_S", "120"))

_lock = threading.Lock()
_state: dict[str, Any] = {"at": None, "value": None, "failed_at": None}


def reset() -> None:
    """Drop the cached queue and any back-off (tests, and an operator forcing a fresh read)."""
    with _lock:
        _state.update(at=None, value=None, failed_at=None)


def forget(identifier: str) -> None:
    """Drop one claimed ticket from the cached queue.

    Called the moment a ticket is claimed (self-claim and dispatch both go through
    routes/mesh.py `_mark_issue_in_progress`). Without it a ticket claimed and
    finished inside one TTL is still in the cached list and is served again — the
    infinite re-claim loop that `_mark_issue_in_progress` exists to prevent.
    """
    with _lock:
        value = _state["value"]
        if value is not None and identifier:
            nodes, repos = value
            _state["value"] = ([n for n in nodes if n.get("identifier") != identifier], repos)


def _refuse_inside_backoff(t: float) -> None:
    """Raise IncompleteRead while a failed Linear read's back-off runs. Call under _lock."""
    if _state["failed_at"] is not None and t - _state["failed_at"] < BACKOFF_S:
        raise mesh_lanes.IncompleteRead(
            f"Linear read failed {int(t - _state['failed_at'])}s ago; backing off for {int(BACKOFF_S)}s")


def candidates(graphql: Callable[[str], dict], now: Callable[[], float] = time.monotonic):
    """`mesh_lanes.candidates(graphql, strict=True)`, read at most once per TTL_S.

    Raises mesh_lanes.IncompleteRead for a failed read, and for any call inside the
    back-off window after one — the queue is unknown, never empty. The back-off is
    checked before the cache: after a failed fresh re-read (`rechecked`) a cached
    queue would only lead the caller straight back to a rate-limited Linear.
    """
    with _lock:
        t = now()
        _refuse_inside_backoff(t)
        if _state["value"] is not None and t - _state["at"] < TTL_S:
            return _state["value"]
        try:
            value = mesh_lanes.candidates(graphql, strict=True)
        except mesh_lanes.IncompleteRead:
            _state.update(failed_at=now())  # back off from when it failed: a slow read can take minutes
            raise
        _state.update(at=t, value=value, failed_at=None)
        return value


def rechecked(graphql: Callable[[str], dict], ranked: Iterable[dict],
              now: Callable[[], float] = time.monotonic) -> Iterator[dict]:
    """Each cached candidate re-read from Linear and re-admitted before it is claimed.

    The shared read can be up to TTL_S old. A ticket blocked, labelled or moved in
    Linear since then must not be claimed from the stale copy, so each one goes
    through `mesh_lanes.explicit` — the same fresh read and admission rule dispatch
    uses — and is dropped from the cache when refused. Lazy: a claim that succeeds
    on the first candidate costs one request. Uncapped: a failed read stops the walk
    at once, and a refusal is a ticket changed inside the TTL, dropped after one read.

    Only a ticket Linear actually returned can be refused. Anything else — {} from
    `_linear_graphql` on a failure, or `issue: null` beside a GraphQL error, or a
    deleted ticket — raises IncompleteRead: unknown is not refused, so the ticket stays cached and the
    caller answers 503, never "queue empty". It starts the same BACKOFF_S as a
    failed queue read, so the next polls do not go back to Linear.
    """
    for node in ranked:
        with _lock:  # a peer's failed read may have started the back-off since this walk began
            _refuse_inside_backoff(now())
        answered: list[bool] = []

        def read(query: str) -> dict:
            data = graphql(query) or {}
            answered.append(isinstance(data, dict) and isinstance(data.get("issue"), dict))
            return data if isinstance(data, dict) else {}
        fresh = mesh_lanes.explicit(read, [node["identifier"]])
        if not answered or not all(answered):
            with _lock:
                _state.update(failed_at=now())
            raise mesh_lanes.IncompleteRead(f"fresh Linear read of {node['identifier']} failed")
        if fresh:
            yield fresh[0]
        else:
            forget(node["identifier"])


def linear_error_detail(exc: BaseException) -> str:
    """Linear's own error text from a failed request, e.g. its rate-limit message.

    Linear answers a rate-limited or malformed query with HTTP 400 and puts the
    reason in the JSON body; urllib's exception string says only "Bad Request".
    Messages only — never the request, headers or key. Never raises: it runs inside
    the route's exception handler, so a malformed body must not escape it.
    """
    if not isinstance(exc, urllib.error.HTTPError):
        return ""
    try:
        body = json.loads(exc.read() or b"{}")
    except Exception:  # noqa: BLE001  any unreadable body is "no detail", not a crash
        return ""
    errors = body.get("errors") if isinstance(body, dict) else None
    if not isinstance(errors, list):
        return ""
    messages = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
    return "; ".join(m for m in messages if m)[:300]
