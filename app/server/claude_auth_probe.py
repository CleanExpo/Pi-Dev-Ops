"""Cached `claude auth status` for generation readiness.

Readiness used to check only config and the CLI binary, so /health read "ok" for
four weeks while every generate was refused for a dead login. This runs the SAME
check dispatch runs (provider_policy.require_transport("anthropic_agent_sdk") with
the dispatch CLI and child environment, unchanged) on one background thread that
refreshes every REFRESH_S, so freshness never depends on how often anyone asks.

A result is trusted for TTL_S only. Older than that, or a failed check, or a
refresher that cannot start, reads as blocked, never as verified. Callers never
wait on the CLI: they get the last result, or a blocked "not yet verified" result
before the first one lands.
Only four status fields and a timestamp are kept; email, orgId and anything else
the CLI prints are dropped here and never reach /health or logs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
import time
from datetime import datetime, timezone

REFRESH_S = 240  # background refresh period
TTL_S = 300  # trust window; > REFRESH_S plus two 10 s CLI timeouts
PUBLIC_FIELDS = ("loggedIn", "authMethod", "apiProvider", "subscriptionType")
# Only these literal values are ever shown; any other string is reported as "other",
# so free text (an email, a token) printed into one of these keys never leaves here.
_SHOWN = {
    "authMethod": frozenset({"claude.ai", "none", "api_key", "oauth_token", "console"}),
    "apiProvider": frozenset({"firstParty", "bedrock", "vertex", "foundry", "anthropic_aws"}),
    "subscriptionType": frozenset({"max", "pro", "team", "enterprise", "free"}),
}
# What the shown fields must say for a login provider_policy admits. Used only to
# AND with the frozen verdict (never instead of it), so drift can add a block but
# never admit; tests/test_claude_auth_readiness.py pins it to the frozen rule.
_AGREES = {
    "loggedIn": frozenset({True}), "authMethod": frozenset({"claude.ai"}),
    "apiProvider": frozenset({"firstParty"}),
    "subscriptionType": frozenset({"max", "pro", "team", "enterprise"}),
}
_UNREADABLE = "subscription_only: subscription login could not be verified"
_STALE = "subscription_only: subscription login check is stale"
_CHANGED = "subscription_only: subscription login changed during the check"
_PENDING = "subscription_only: subscription login not yet verified"
_REBOUND = "subscription_only: subscription login not yet verified for the current CLI or environment"

log = logging.getLogger("pi-ceo.claude_auth_probe")
_clock = time.monotonic
_lock = threading.Lock()
_landed = threading.Event()
_stop = threading.Event()
_kick = threading.Event()  # wakes the refresher early
_snapshot: dict | None = None
_thread: threading.Thread | None = None
_epoch = 0  # bumped by reset() so an in-flight refresh cannot publish afterwards


def _public(payload: dict) -> dict:
    """Map the CLI payload onto known literals only. Nothing else is ever kept."""
    logged_in = payload.get("loggedIn")
    out: dict = {"loggedIn": logged_in if isinstance(logged_in, bool) else None}
    for key, allowed in _SHOWN.items():
        value = payload.get(key)
        out[key] = None if value is None else (value if isinstance(value, str) and value in allowed else "other")
    return out


def _agrees(fields: dict) -> bool:
    """True only when the shown fields describe a login the frozen check admits."""
    return all(fields.get(key) in allowed for key, allowed in _AGREES.items())


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


def _snap(fields: dict, error: str | None, checked_at: str | None, binding: str | None = None) -> dict:
    return {"auth": {**fields, "checked_at": checked_at}, "verified": error is None,
            "error": error, "at": _clock(), "binding": binding}


def _binding(cli: str, env: dict[str, str]) -> str:
    """Private fingerprint of exactly what was checked: CLI path, file identity, child env.

    A verdict holds only for the binary and environment it ran against. Only this
    digest is kept, inside the process; no path or environment value is exposed.
    """
    from .sdk_execution_boundary import _cli_identity
    material = repr((cli, _cli_identity(cli), sorted(env.items())))
    return hashlib.sha256(material.encode()).hexdigest()


def _current_binding() -> str | None:
    from .sdk_execution_boundary import _child_environment, _execution_cli
    try:
        return _binding(_execution_cli(), _child_environment())
    except Exception:  # noqa: BLE001 - unknown binding never matches a cached verdict
        return None


def refresh() -> dict:
    """Run dispatch's own auth check once, with dispatch's CLI and env, and cache it."""
    from .provider_policy import ProviderPolicyError, require_transport
    from .sdk_execution_boundary import ExecutionBoundaryError, _child_environment, _execution_cli
    global _snapshot
    with _lock:
        epoch = _epoch
    cli = env = binding = None
    error = None
    try:
        cli, env = _execution_cli(), _child_environment()
        binding = _binding(cli, env)
        require_transport("anthropic_agent_sdk", cli_path=cli, env=env)
    except (ProviderPolicyError, ExecutionBoundaryError) as exc:
        error = str(exc)
    except Exception as exc:  # noqa: BLE001 - a probe defect must read as unverified, never ready
        log.warning("claude auth probe failed: %s", type(exc).__name__)
        error = _UNREADABLE
    fields = _status_fields(cli, env) if cli and env is not None else dict.fromkeys(PUBLIC_FIELDS)
    if error is None and not _agrees(fields):
        error = _CHANGED  # the display read contradicts the verdict: never publish both
    snap = _snap(fields, error, datetime.now(timezone.utc).isoformat(), binding)
    with _lock:
        if epoch == _epoch:
            _snapshot = snap
            _landed.set()
    return snap


def snapshot() -> dict:
    """Return the cached result without waiting.

    One rule: verified only for a passing check of the CURRENT CLI and child env,
    younger than TTL_S. Every other state carries an error, so readiness blocks:
    not yet checked, stale, CLI/env changed since the check, refresher unstartable.
    """
    try:
        _schedule()
        started = True
    except Exception as exc:  # noqa: BLE001 - e.g. "can't start new thread"; /health must not 500
        log.warning("claude auth refresher could not start: %s", type(exc).__name__)
        started = False
    with _lock:
        snap = _snapshot
    if snap is None:
        return _snap(dict.fromkeys(PUBLIC_FIELDS), _PENDING if started else _UNREADABLE, None)
    if _clock() - snap["at"] >= TTL_S:
        return {**snap, "verified": False, "error": _STALE}
    if snap["verified"] and snap["binding"] != _current_binding():
        _kick.set()  # re-check the new CLI/env now rather than at the next period
        return {**snap, "verified": False, "error": _REBOUND}
    return snap


def _refresh_loop(stop: threading.Event, kick: threading.Event) -> None:
    while not stop.is_set():
        try:
            refresh()
        except Exception as exc:  # noqa: BLE001 - the refresher must outlive one bad run
            log.warning("claude auth probe crashed: %s", type(exc).__name__)
        kick.wait(REFRESH_S)
        kick.clear()


def _start_refresh() -> None:
    """Ensure exactly one refresher thread is running."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_refresh_loop, args=(_stop, _kick),
                                   name="claude-auth-probe", daemon=True)
        _thread.start()


_schedule = _start_refresh  # tests replace this so the real CLI never runs under pytest


def wait_for_refresh(timeout: float) -> bool:
    """Block until a result has landed since the last reset(). Tests and tooling only."""
    return _landed.wait(timeout)


def reset() -> None:
    """Drop the cache and stop the refresher. An in-flight result is discarded."""
    global _snapshot, _thread, _stop, _kick, _epoch
    with _lock:
        _stop.set()
        _kick.set()
        thread = _thread
        _snapshot, _thread, _stop, _kick = None, None, threading.Event(), threading.Event()
        _epoch += 1
        _landed.clear()
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=5)
