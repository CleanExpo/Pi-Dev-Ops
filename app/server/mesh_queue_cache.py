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

import os
import threading
import time
from typing import Any, Callable

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


def candidates(graphql: Callable[[str], dict], now: Callable[[], float] = time.monotonic):
    """`mesh_lanes.candidates(graphql, strict=True)`, read at most once per TTL_S.

    Raises mesh_lanes.IncompleteRead for a failed read, and for any call inside the
    back-off window after one — the queue is unknown, never empty.
    """
    with _lock:
        t = now()
        if _state["value"] is not None and t - _state["at"] < TTL_S:
            return _state["value"]
        if _state["failed_at"] is not None and t - _state["failed_at"] < BACKOFF_S:
            raise mesh_lanes.IncompleteRead(
                f"Linear read failed {int(t - _state['failed_at'])}s ago; backing off for {int(BACKOFF_S)}s")
        try:
            value = mesh_lanes.candidates(graphql, strict=True)
        except mesh_lanes.IncompleteRead:
            _state.update(failed_at=t)
            raise
        _state.update(at=t, value=value, failed_at=None)
        return value
