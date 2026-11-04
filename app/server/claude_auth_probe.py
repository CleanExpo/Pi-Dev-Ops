"""Cached `claude auth status` for generation readiness.

Readiness used to check only config and the CLI binary, so /health read "ok" for
four weeks while every generate was refused for a dead login. This runs the SAME
check dispatch runs (provider_policy.require_transport("anthropic_agent_sdk") with
the dispatch CLI and child environment, unchanged), on a background thread, at most
once per TTL_S. Callers never wait on the CLI: they get the last result, or None
before the first probe lands. Only four status fields and a timestamp are kept;
email, orgId and anything else the CLI prints are dropped here and never reach
/health or logs.
"""
from __future__ import annotations

import json
import logging
import subprocess
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


def _status_fields(cli: str, env: dict[str, str]) -> dict:
    """Display-only read of the login fields. Never decides anything; never logs output.

    provider_policy.py is frozen (founder ruling 22/10/2026), so its check cannot be
    split to hand back the payload it reads. The verdict comes from that unchanged
    check in refresh(); this second read only fills in which field failed.
    """
    try:
        result = subprocess.run([cli, "auth", "status"], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        payload = {}
    return _public(payload if isinstance(payload, dict) else {})


def refresh() -> dict:
    """Run dispatch's own auth check once, with dispatch's CLI and env, and cache it."""
    from .provider_policy import ProviderPolicyError, require_transport
    from .sdk_execution_boundary import ExecutionBoundaryError, _child_environment, _execution_cli
    cli = env = None
    error = None
    try:
        cli, env = _execution_cli(), _child_environment()
        require_transport("anthropic_agent_sdk", cli_path=cli, env=env)
    except (ProviderPolicyError, ExecutionBoundaryError) as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a probe defect must read as unverified, never ready
        log.warning("claude auth probe failed: %s", type(exc).__name__)
        error = _UNREADABLE
    fields = _status_fields(cli, env) if cli and env is not None else dict.fromkeys(PUBLIC_FIELDS)
    checked_at = datetime.now(timezone.utc).isoformat()
    snap = {"auth": {**fields, "checked_at": checked_at},
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
