"""RA-7546 — treat a Railway mid-session wipe as infra, not a product fail.

First-source facts this module encodes:

* ``_sessions`` is an in-memory dict (``app/server/session_model.py``).
* ``GET /api/sessions`` serialises that dict only (``routes/sessions.py``).
* Railway production has **no volume**. ``LOG_DIR`` JSON is ephemeral, so
  ``restore_sessions()`` wakes to an empty store after every deploy.
* GC cannot explain a seconds-old smoke session: ``collect_garbage`` only
  drops *terminal* sessions older than ``TAO_GC_MAX_AGE`` (default 14400 s).

A 502/503, a 401 after a cookie-secret rotate, or a healthy list that no
longer contains the session all mean "the process restarted". The smoke
waits until authenticated ``/health`` reports ``uptime_s`` past the settle
floor, re-logins if needed, and respawns. Planner CLEAR is a separate
quiet-tip re-run — see ``.github/workflows/smoke_pipeline.yml``.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable


TRANSIENT_HTTP = frozenset({0, 502, 503, 504})
# ``blocked`` is a planner/adversary terminal (RA-1026 / RA-7546). ``stalled``
# is the RA-1104 watchdog. Smoke used to treat both as "still running".
SESSION_TERMINAL = frozenset({
    "complete", "failed", "killed", "interrupted", "blocked", "stalled",
})


def is_terminal_status(status: str | None) -> bool:
    """True when smoke classify/poll must stop (not hang). ``blocked`` is in."""
    return str(status or "") in SESSION_TERMINAL
# last_completed_phase is set when a phase finishes. ``plan`` means generate
# has been admitted; later names mean it already ran.
GENERATE_ADMITTED = frozenset({
    "plan", "generator", "evaluator", "adversary", "push", "push_failed",
})


def logs_stream_path(sid: str) -> str:
    """Heartbeat SSE (RA-6504). The old ``/logs`` path has no keep-alive."""
    return f"/api/sessions/{sid}/logs/stream"


def row_entered_generate(row: dict[str, Any]) -> bool:
    """True when /api/sessions proves generate was admitted or already ran."""
    last = str(row.get("last_phase") or "")
    if last in GENERATE_ADMITTED:
        return True
    metrics = row.get("phase_metrics")
    return isinstance(metrics, dict) and "generate" in metrics


def note_session_row(row: dict[str, Any]) -> str:
    """One-line poll snapshot so a stream drop is still diagnosable."""
    parts = [
        f"status={row.get('status')}",
        f"last_phase={row.get('last_phase') or '-'}",
        f"lines={row.get('lines')}",
    ]
    err = str(row.get("error") or "").strip()
    if err:
        parts.append(f"error={err}")
    return " ".join(parts)


def terminal_fail_message(row: dict[str, Any]) -> str:
    """Fail text for a non-complete terminal row (blocked/failed/...)."""
    status = row.get("status") or "unknown"
    msg = f"session terminal={status} last_phase={row.get('last_phase') or '-'}"
    err = str(row.get("error") or "").strip()
    if err:
        msg += f" error={err}"
    return msg


def settle_uptime_s() -> int:
    return int(os.environ.get("SMOKE_SETTLE_UPTIME_S", "90"))


def settle_poll_s() -> float:
    return float(os.environ.get("SMOKE_SETTLE_POLL_S", "5"))


def max_respawns() -> int:
    return int(os.environ.get("SMOKE_MAX_RESPAWNS", "2"))


def wall_clock_s() -> int:
    return int(os.environ.get("SMOKE_WALL_CLOCK_S", "2400"))


@dataclass
class Probe:
    http_status: int
    sessions: list[dict[str, Any]] | None = None
    uptime_s: int | None = None
    error: str = ""


def parse_session_list(body: str) -> list[dict[str, Any]] | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        rows = data.get("sessions", [])
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return None


def parse_uptime(body: str) -> int | None:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("uptime_s")
    return raw if isinstance(raw, int) else None


def find_session(rows: list[dict[str, Any]], sid: str) -> dict[str, Any] | None:
    prefix = sid[:8]
    return next((row for row in rows if str(row.get("id", "")).startswith(prefix)), None)


def classify_session_list(probe: Probe, sid: str) -> str:
    """found | wiped | bouncing | auth_stale"""
    if probe.http_status == 401:
        return "auth_stale"
    if probe.http_status in TRANSIENT_HTTP or probe.sessions is None:
        return "bouncing"
    if find_session(probe.sessions, sid) is not None:
        return "found"
    return "wiped"


def classify_backend(probe: Probe) -> str:
    """settled | young | bouncing | auth_stale"""
    if probe.http_status == 401:
        return "auth_stale"
    if probe.http_status in TRANSIENT_HTTP:
        return "bouncing"
    if probe.http_status != 200 or probe.sessions is None:
        return "bouncing"
    if probe.uptime_s is not None and probe.uptime_s < settle_uptime_s():
        return "young"
    return "settled"


def should_respawn(kind: str) -> bool:
    return kind in {"wiped", "bouncing", "auth_stale"}


def wait_until_settled(
    probe_fn: Callable[[], Probe],
    *,
    until: float,
    relogin: Callable[[], bool] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    now_fn: Callable[[], float] = time.time,
    log: Callable[[str], None] = print,
) -> bool:
    """Block until the backend is readable and past the uptime floor."""
    while now_fn() < until:
        probe = probe_fn()
        kind = classify_backend(probe)
        if kind == "auth_stale" and relogin is not None:
            log("[settle] cookie rejected after restart; re-login")
            if not relogin():
                return False
            continue
        if kind == "settled":
            log(f"[settle] backend ready http={probe.http_status} uptime={probe.uptime_s}")
            return True
        log(f"[settle] backend {kind} http={probe.http_status} uptime={probe.uptime_s}")
        remaining = until - now_fn()
        if remaining <= 0:
            break
        sleep_fn(min(settle_poll_s(), remaining))
    return False
