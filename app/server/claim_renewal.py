"""claim_renewal.py - a running cloud session keeps its own mesh claim alive.

WHY. `mesh_reaper.reap()` releases a claim past MESH_CLAIM_TTL_MINUTES unless
the claiming machine has a fresh heartbeat. Every cloud replica claims as the one
shared `session_lease.CLOUD_CLAIM_MACHINE` row, which never heartbeats, so a cloud
claim older than the TTL was always released - even with its session still
running (a build can run TAO_MAX_ITERS x 600 s = 250 min against a 90 min TTL).
The ticket was then offered to a second worker: double work.

THE OWNER OF "IS THIS CLAIM ALIVE" is the claim row's own `claimed_at`, which the
reaper already measures the TTL from. The process that inserted a cloud claim
renews it (`claimed_at = now`) every RENEW_INTERVAL_S, far inside the TTL floor of
65 min, so the reaper needs no special case. A replica that dies stops renewing
and its claim is reaped at the TTL exactly as before. Exempting the cloud row from
reaping instead would let a dead replica hold its ticket forever.

No schema change: `mesh_work_claims` has no heartbeat column, and `claimed_at` is
the only timestamp the reaper reads. Renewing it also moves the start-ledger
window in `mesh_lanes.repeat_claimed` forward by at most MAX_RENEW_MINUTES for a
claim that was alive that long, which only makes the repeat-claim guard slightly
stricter for that ticket.

LIFECYCLE. `session_lease.claim_linear_ticket` starts the renewer after a won
cloud claim; `release_linear_ticket` stops it. The renewer also stops by itself
when (a) its claim row is no longer open (reaped, released or finished: the PATCH
matches no row, so it can never resurrect a claim) or (b) MAX_RENEW_MINUTES have
passed (a claim kept after a finished session is not held forever). A failed
renewal is logged and retried next interval; it never raises into the session.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger("pi-ceo.claim_renewal")

# Well under MESH_CLAIM_TTL_MINUTES (floor 65 min): a dozen missed renewals fit.
RENEW_INTERVAL_S = 300.0
# Ceiling on an operator-set interval: three renewals inside the 65 min TTL floor,
# so no configuration can let the reaper release a live claim before it renews.
MAX_RENEW_INTERVAL_S = 65 * 60 / 3
# Above the longest build (25 iterations x 600 s = 250 min) with headroom.
MAX_RENEW_MINUTES = 360.0

_RENEWERS: dict[str, threading.Event] = {}  # linear_id -> stop flag of its live renewer
_LOCK = threading.Lock()


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def renew_once(claim_id: str, linear_id: str) -> str:
    """One conditional renewal. `renewed`, `gone` (claim no longer open) or `error`."""
    from . import supabase_log  # noqa: PLC0415 - avoid an import cycle at module load

    query = (
        f"mesh_work_claims?id=eq.{supabase_log._q(claim_id)}"
        f"&linear_id=eq.{supabase_log._q(linear_id)}&state=in.(claimed,working)"
    )
    body = {"claimed_at": datetime.now(timezone.utc).isoformat()}
    try:
        status, rows = supabase_log._request("PATCH", query, body, "return=representation")
    except Exception as exc:  # noqa: BLE001 - a renewal must never reach the session
        log.warning("claim renew failed for %s: %s", linear_id, exc)
        return "error"
    if not supabase_log._ok(status) or not isinstance(rows, list):
        log.warning("claim renew failed for %s (http=%s)", linear_id, status)
        return "error"
    return "renewed" if rows else "gone"


def _run(linear_id: str, claim_id: str, flag: threading.Event, interval_s: float, max_s: float) -> None:
    started = time.monotonic()
    try:
        while not flag.wait(interval_s):
            if time.monotonic() - started > max_s:
                log.info("claim renew for %s reached its %.0f s limit - no longer renewing", linear_id, max_s)
                return
            if renew_once(claim_id, linear_id) == "gone":
                log.info("claim renew for %s ended - claim is no longer open", linear_id)
                return
    finally:
        with _LOCK:
            if _RENEWERS.get(linear_id) is flag:
                del _RENEWERS[linear_id]


def start(linear_id: str, claim_id: str) -> None:
    """Begin renewing one cloud claim; replaces any renewer already running for the ticket.

    A no-op off the cloud: a machine claim is protected by its machine's heartbeat.
    """
    from . import session_lease  # noqa: PLC0415 - session_lease imports this module

    if not session_lease.is_cloud():
        return
    interval_s = _env_float("MESH_CLAIM_RENEW_INTERVAL_S", RENEW_INTERVAL_S)
    if interval_s > MAX_RENEW_INTERVAL_S:
        log.warning("MESH_CLAIM_RENEW_INTERVAL_S=%.0f outlasts the claim TTL floor; using %.0f s",
                    interval_s, MAX_RENEW_INTERVAL_S)
        interval_s = MAX_RENEW_INTERVAL_S
    max_s = _env_float("MESH_CLAIM_RENEW_MAX_MINUTES", MAX_RENEW_MINUTES) * 60.0
    flag = threading.Event()
    with _LOCK:
        previous = _RENEWERS.get(linear_id)
        if previous is not None:
            previous.set()
        _RENEWERS[linear_id] = flag
    threading.Thread(
        target=_run, args=(linear_id, claim_id, flag, interval_s, max_s),
        name=f"claim-renew-{linear_id}", daemon=True,
    ).start()


def stop(linear_id: str) -> None:
    """Stop renewing a ticket's claim. Safe when none is running."""
    with _LOCK:
        flag = _RENEWERS.pop(linear_id, None)
    if flag is not None:
        flag.set()
