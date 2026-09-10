"""Session-derived panels for Mission Control: throughput, live sessions, completions.

Extracted from mission_control.py, which the size gate holds to 300 lines.

Every function here reads the in-process session store. Each one used to read a
field that no code ever wrote, so all three panels were empty by construction
while the smoke gate — which asserted key NAMES only — stayed green:

  * throughput / completions read `completed_at`; BuildSession had no such field
  * elapsed time parsed `started_at` (an epoch float) as an ISO string, inside a
    swallowed except, so it was always 0
  * the log tail read `last_log_line`; the field is `output_lines`
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("pi-ceo.mission_control")

_RUNNING = ("created", "cloning", "building", "evaluating", "running")
_TERMINAL = ("complete", "shipped", "done")


def _field(sess, name, default=None):
    """Read a field off a BuildSession or off a plain dict, whichever we were given."""
    value = getattr(sess, name, None)
    if value is None and isinstance(sess, dict):
        value = sess.get(name)
    return default if value is None else value


def as_datetime(value) -> datetime | None:
    """Coerce a session timestamp to an aware datetime, or None if it is not one.

    Sessions store `started_at` / `completed_at` as EPOCH FLOATS. These were fed
    to datetime.fromisoformat() inside a bare except, so every parse failed
    silently and every elapsed time rendered as 0. Epoch numbers are the common
    case here, so they are handled first and explicitly.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value)
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(value) -> str | None:
    """ISO-8601, or None. str() on an epoch float gives '1757483…', which the
    panel can neither render nor sort."""
    dt = as_datetime(value)
    return dt.isoformat() if dt else None


def last_log_line(sess) -> str:
    lines = _field(sess, "output_lines")
    return str(lines[-1]).strip() if lines else ""


def _store() -> dict:
    from .sessions import _sessions  # type: ignore

    return _sessions or {}


def hourly_throughput_24h() -> list[int]:
    """Completions per hour for the last 24h, oldest bucket first."""
    try:
        now = datetime.now(timezone.utc)
        buckets = [0] * 24
        for sess in _store().values():
            if _field(sess, "status") not in _TERMINAL:
                continue
            dt = as_datetime(_field(sess, "completed_at"))
            if dt is None:
                continue
            hours_ago = int((now - dt).total_seconds() // 3600)
            if 0 <= hours_ago < 24:
                buckets[23 - hours_ago] += 1
        return buckets
    except Exception as exc:  # noqa: BLE001
        log.debug("throughput read failed: %s", exc)
        return [0] * 24


def active_sessions() -> list[dict]:
    try:
        out = []
        now = datetime.now(timezone.utc)
        for sid, sess in _store().items():
            status = _field(sess, "status")
            if status not in _RUNNING:
                continue
            started = as_datetime(_field(sess, "started_at"))
            out.append({
                "id": sid[:12],
                "repo": str(_field(sess, "repo_url", "")).split("/")[-1] or "?",
                "phase": _field(sess, "phase", status),
                "status": status,
                "elapsed_s": max(0, int((now - started).total_seconds())) if started else 0,
                "issue_id": _field(sess, "linear_issue_id"),
                "last_log_tail": last_log_line(sess)[:120],
            })
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("active sessions read failed: %s", exc)
        return []


def recent_completions(limit: int = 6) -> list[dict]:
    try:
        completed = []
        for sid, sess in _store().items():
            if _field(sess, "status") not in _TERMINAL:
                continue
            completed.append({
                "id": sid[:12],
                "repo": str(_field(sess, "repo_url", "")).split("/")[-1] or "?",
                "branch": _field(sess, "branch"),
                "score": _field(sess, "evaluator_score"),
                "pr_url": _field(sess, "pr_url"),
                "issue_id": _field(sess, "linear_issue_id"),
                "completed_at": iso(_field(sess, "completed_at")),
            })
        completed.sort(key=lambda x: x.get("completed_at") or "", reverse=True)
        return completed[:limit]
    except Exception as exc:  # noqa: BLE001
        log.debug("recent completions read failed: %s", exc)
        return []
