"""Cached `claude auth status` for generation readiness.

Readiness used to check only config and the CLI binary, so /health read "ok" for
four weeks while every generate was refused for a dead login. This runs the SAME
check dispatch runs (provider_policy.read_claude_auth + check_claude_auth, with the
dispatch CLI and child environment), on a background thread, at most once per
TTL_S. Callers never wait on the CLI: they get the last result, or None before the
first probe lands. Only four status fields and a timestamp are kept; email, orgId
and anything else the CLI prints are dropped here and never reach /health or logs.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

TTL_S = 300  # refresh at most every ~5 minutes
MAX_AGE_S = 900  # a result this old means refreshes stopped landing: not evidence
PUBLIC_FIELDS = ("loggedIn", "authMethod", "apiProvider", "subscriptionType")
_UNREADABLE = "subscription_only: subscription login could not be verified"
_STALE = "subscription_only: subscription login check is stale"

log = logging.getLogger("pi-ceo.claude_auth_probe")
_clock = time.monotonic
_lock = threading.Lock()
_snapshot: dict | None = None
_thread: threading.Thread | None = None


def _public(payload: dict) -> dict:
    """Keep only short scalar status values; anything else reads as unknown."""
    out = {}
    for key in PUBLIC_FIELDS:
        value = payload.get(key)
        ok = value is None or isinstance(value, bool) or (isinstance(value, str) and len(value) <= 40)
        out[key] = value if ok else None
    return out


def refresh() -> dict:
    """Run the dispatch auth check once and cache the redacted result."""
    from .provider_policy import ProviderPolicyError, check_claude_auth, read_claude_auth
    from .sdk_execution_boundary import ExecutionBoundaryError, _child_environment, _execution_cli
    payload: dict = {}
    error = None
    try:
        payload = read_claude_auth(_execution_cli(), _child_environment())
        check_claude_auth("anthropic_agent_sdk", payload)
    except (ProviderPolicyError, ExecutionBoundaryError) as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a probe defect must read as unverified, never ready
        log.warning("claude auth probe failed: %s", type(exc).__name__)
        error = _UNREADABLE
    checked_at = datetime.now(timezone.utc).isoformat()
    snap = {"auth": {**_public(payload), "checked_at": checked_at},
            "verified": error is None, "error": error, "at": _clock()}
    global _snapshot
    with _lock:
        _snapshot = snap
    return snap


def snapshot() -> dict | None:
    """Return the cached result without waiting; start a refresh when one is due."""
    with _lock:
        snap = _snapshot
    age = None if snap is None else _clock() - snap["at"]
    if age is None or age >= TTL_S:
        _schedule()
    if age is not None and age >= MAX_AGE_S:
        return {**snap, "verified": False, "error": _STALE}
    return snap


def _refresh_quietly() -> None:
    try:
        refresh()
    except Exception as exc:  # noqa: BLE001 - background thread must not die loudly
        log.warning("claude auth probe crashed: %s", type(exc).__name__)


def _start_refresh() -> None:
    """Single-flight: at most one probe thread at a time."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_refresh_quietly, name="claude-auth-probe", daemon=True)
        _thread.start()


_schedule = _start_refresh  # tests replace this so the real CLI never runs under pytest


def wait_for_refresh(timeout: float) -> bool:
    """Join the in-flight probe, if any. True when nothing is still running."""
    thread = _thread
    if thread is None:
        return True
    thread.join(timeout)
    return not thread.is_alive()


def reset() -> None:
    global _snapshot, _thread
    with _lock:
        _snapshot = None
        _thread = None
