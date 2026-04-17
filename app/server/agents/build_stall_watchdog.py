"""
build_stall_watchdog.py — RA-1104 — detect and recover stalled build sessions.

Background async loop that polls the in-memory _sessions store every
WATCHDOG_INTERVAL_S seconds. For any session in a non-terminal state
("created", "cloning", "building", "evaluating", "pushing"), checks the
timestamp of the last output line. If older than STALL_THRESHOLD_S (default
15 min), the session is considered stalled and the watchdog:

  1. Marks session.status = "stalled" so the dashboard surfaces it
  2. Kills the OS-level subprocess if one is attached
  3. Persists the session snapshot
  4. Fires a Telegram alert via the existing helper script

Recovery strategy is "fail loud, fail fast": kill the stalled session
deterministically rather than try to resume in-place. The autonomy poller
or the user can re-trigger the build cleanly. This avoids the "zombie
process pretending to make progress" failure mode that's harder to debug
than an obvious red status.

Tunables (env):
    TAO_STALL_THRESHOLD_S        — minutes idle before stall (default 900s/15min)
    TAO_STALL_WATCHDOG_INTERVAL  — poll interval (default 60s)
    TAO_STALL_WATCHDOG_ENABLED   — "0" to disable entirely (default on)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Iterable

from .. import persistence  # session_model.py lives one level up; persistence too
from ..session_model import BuildSession, _sessions

_log = logging.getLogger(__name__)

STALL_THRESHOLD_S      = int(os.environ.get("TAO_STALL_THRESHOLD_S",        "900"))
WATCHDOG_INTERVAL_S    = int(os.environ.get("TAO_STALL_WATCHDOG_INTERVAL", "60"))
WATCHDOG_STARTUP_DELAY = 30   # don't fire on first boot — let initial sessions ramp
WATCHDOG_ENABLED       = os.environ.get("TAO_STALL_WATCHDOG_ENABLED", "1") == "1"

# Anything not in this set is considered "in flight" and watchdog-eligible
TERMINAL_STATUSES = {"complete", "failed", "killed", "interrupted", "stalled", "error"}


def _last_progress_ts(session: BuildSession) -> float:
    """Return the timestamp of the most recent output event, or session.started_at."""
    if session.output_lines:
        last = session.output_lines[-1]
        if isinstance(last, dict) and "ts" in last:
            try:
                return float(last["ts"])
            except (TypeError, ValueError):
                pass
    return float(session.started_at or 0.0)


def _send_telegram(message: str) -> None:
    """Best-effort Telegram alert. Reuses TELEGRAM_BOT_TOKEN + ALLOWED_USERS from env."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    allowed = os.environ.get("ALLOWED_USERS", "").strip()
    if not token or not allowed:
        return
    chat_id = allowed.split(",")[0].strip()
    if not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({
            "chat_id": chat_id,
            "text":    message,
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=8)
    except (urllib.error.URLError, OSError) as exc:
        _log.warning("watchdog: Telegram alert failed (non-fatal): %s", exc)


async def _kill_subprocess(session: BuildSession) -> None:
    """Best-effort kill of any OS-level subprocess attached to the session."""
    proc = getattr(session, "process", None)
    if proc is None:
        return
    try:
        if hasattr(proc, "returncode") and proc.returncode is None:
            proc.kill()
            await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError, OSError) as exc:
        _log.warning("watchdog: kill failed for session %s: %s", session.id, exc)


def _persist(session: BuildSession) -> None:
    """Write session snapshot to disk if persistence module is available."""
    try:
        persistence.save_session(session)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _stalled_sessions(now: float) -> Iterable[BuildSession]:
    for session in list(_sessions.values()):
        if session.status in TERMINAL_STATUSES:
            continue
        if (now - _last_progress_ts(session)) > STALL_THRESHOLD_S:
            yield session


async def _handle_stall(session: BuildSession) -> None:
    age_min = (time.time() - _last_progress_ts(session)) / 60.0
    _log.error(
        "RA-1104 STALL: session=%s status=%s idle=%.1f min — killing",
        session.id, session.status, age_min,
    )
    prior_status = session.status
    session.status = "stalled"
    session.error = (session.error or "") + f"\n[stall-watchdog] killed after {age_min:.1f} min idle"
    await _kill_subprocess(session)
    _persist(session)

    repo_short = (session.repo_url or "?").rsplit("/", 1)[-1].replace(".git", "")
    _send_telegram(
        f"🛑 <b>Build stalled</b>\n"
        f"<code>{session.id}</code> · <i>{repo_short}</i>\n"
        f"Was: <code>{prior_status}</code> · idle <b>{age_min:.0f} min</b>\n"
        f"Killed cleanly. Re-trigger from dashboard or wait for autonomy poll."
    )


async def stall_watchdog_loop() -> None:
    """Main async loop. Started from app_factory's on_startup hook."""
    if not WATCHDOG_ENABLED:
        _log.info("RA-1104: build stall watchdog disabled via TAO_STALL_WATCHDOG_ENABLED=0")
        return

    _log.info(
        "RA-1104: build stall watchdog active — threshold=%ds interval=%ds",
        STALL_THRESHOLD_S, WATCHDOG_INTERVAL_S,
    )

    # Startup delay so we don't kill anything during initial boot warmup
    await asyncio.sleep(WATCHDOG_STARTUP_DELAY)

    while True:
        try:
            now = time.time()
            for session in _stalled_sessions(now):
                await _handle_stall(session)
        except Exception as exc:  # noqa: BLE001
            # Never let a single iteration crash the loop
            _log.error("RA-1104 watchdog iteration failed (continuing): %s", exc)
        await asyncio.sleep(WATCHDOG_INTERVAL_S)
