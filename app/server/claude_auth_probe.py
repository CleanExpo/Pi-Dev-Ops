"""Cached `claude auth status` for generation readiness.

Readiness used to check only config and the CLI binary, so /health read "ok" for
four weeks while every generate was refused for a dead login. This runs the SAME
check dispatch runs (provider_policy.require_transport("anthropic_agent_sdk") with
the dispatch CLI and child environment, unchanged) on one background thread that
refreshes every REFRESH_S, so freshness never depends on how often anyone asks.

A result is trusted for TTL_S only. Older than that, or a failed check, or a
refresher that cannot start, reads as blocked, never as verified. Callers never
wait on the CLI: they get the last result, or None before the first one lands.
Only four status fields and a timestamp are kept; email, orgId and anything else
the CLI prints are dropped here and never reach /health or logs.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone

REFRESH_S = 240  # background refresh period
TTL_S = 300  # trust window; > REFRESH_S plus two 10 s CLI timeouts
PUBLIC_FIELDS = ("loggedIn", "authMethod", "apiProvider", "subscriptionType")
_UNREADABLE = "subscription_only: subscription login could not be verified"
_STALE = "subscription_only: subscription login check is stale"

log = logging.getLogger("pi-ceo.claude_auth_probe")
_clock = time.monotonic
_lock = threading.Lock()
_landed = threading.Event()
_stop = threading.Event()
_snapshot: dict | None = None
_thread: threading.Thread | None = None
_epoch = 0  # bumped by reset() so an in-flight refresh cannot publish afterwards


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
    check in refresh(); this second read only shows which field failed.
    """
    try:
        result = subprocess.run([cli, "auth", "status"], env=env, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=10, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        payload = {}
    return _public(payload if isinstance(payload, dict) else {})


def _snap(fields: dict, error: str | None, checked_at: str | None) -> dict:
    return {"auth": {**fields, "checked_at": checked_at},
            "verified": error is None, "error": error, "at": _clock()}


def refresh() -> dict:
    """Run dispatch's own auth check once, with dispatch's CLI and env, and cache it."""
    from .provider_policy import ProviderPolicyError, require_transport
    from .sdk_execution_boundary import ExecutionBoundaryError, _child_environment, _execution_cli
    global _snapshot
    with _lock:
        epoch = _epoch
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
    snap = _snap(fields, error, datetime.now(timezone.utc).isoformat())
    with _lock:
        if epoch == _epoch:
            _snapshot = snap
            _landed.set()
    return snap


def snapshot() -> dict | None:
    """Return the cached result without waiting. Stale or unschedulable reads as blocked."""
    try:
        _schedule()
        started = True
    except Exception as exc:  # noqa: BLE001 - e.g. "can't start new thread"; /health must not 500
        log.warning("claude auth refresher could not start: %s", type(exc).__name__)
        started = False
    with _lock:
        snap = _snapshot
    if snap is not None and _clock() - snap["at"] >= TTL_S:
        return {**snap, "verified": False, "error": _STALE}
    if snap is None and not started:
        return _snap(dict.fromkeys(PUBLIC_FIELDS), _UNREADABLE, None)
    return snap


def _refresh_loop(stop: threading.Event) -> None:
    while True:
        try:
            refresh()
        except Exception as exc:  # noqa: BLE001 - the refresher must outlive one bad run
            log.warning("claude auth probe crashed: %s", type(exc).__name__)
        if stop.wait(REFRESH_S):
            return


def _start_refresh() -> None:
    """Ensure exactly one refresher thread is running."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_refresh_loop, args=(_stop,),
                                   name="claude-auth-probe", daemon=True)
        _thread.start()


_schedule = _start_refresh  # tests replace this so the real CLI never runs under pytest


def wait_for_refresh(timeout: float) -> bool:
    """Block until a result has landed since the last reset(). Tests and tooling only."""
    return _landed.wait(timeout)


def reset() -> None:
    """Drop the cache and stop the refresher. An in-flight result is discarded."""
    global _snapshot, _thread, _stop, _epoch
    with _lock:
        _stop.set()
        thread = _thread
        _snapshot, _thread, _stop = None, None, threading.Event()
        _epoch += 1
        _landed.clear()
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=5)
