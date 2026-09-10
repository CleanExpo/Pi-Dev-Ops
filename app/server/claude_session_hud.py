"""claude_session_hud.py — reads the context-ceiling hook's own state files.

WHY THIS EXISTS. `~/.claude/hooks/PreToolUse/context_ceiling.py` already writes one
JSON file per Claude Code session to `~/.claude/.context-ceiling/<session_id>.json`
on every tool call — token usage, window size, percent-used, and a `stage` of
`ok` / `handoff` / `hard` (rules/context-ceiling.md). That hook's own comment
names an intended reader: "the dashboard". Nothing in this repo was that reader
until now — the data existed, un-surfaced.

HONESTY, not just plumbing. This can only ever see sessions on the HOST this
backend process runs on. On a cloud deploy (Railway) that directory is empty or
absent, which must never be read as "zero agents running" — that is the exact
surface-treatment RA-1109 exists to forbid. `available=False` with a `reason` is
the honest shape for that case; the frontend must render it distinctly from a
genuine empty list.

SCOPE. A corrupt or unreadable individual session file is skipped, not fatal —
one bad JSON write must not blank the whole panel. `LIVE_WINDOW_S` filters to
sessions updated recently; the directory accumulates one file per session ever
run, most of them hours or days stale, and a "live" panel showing all of them
would be scrolling history, not a HUD.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("pi-ceo.claude_session_hud")

CEILING_DIR = Path.home() / ".claude" / ".context-ceiling"

# A session not updated in this long is not "currently running" — it is history.
LIVE_WINDOW_S = 600


def _read_one(path: Path, now: float) -> dict | None:
    """One session's HUD entry, or None if the file is unreadable or stale."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        # ValueError covers json.JSONDecodeError AND UnicodeDecodeError — a
        # session file with invalid UTF-8 bytes must be skipped like any other
        # corrupt file, never crash the whole panel.
        log.debug("claude_session_hud: unreadable state file %s: %s", path.name, exc)
        return None
    ts = raw.get("ts")
    if not isinstance(ts, (int, float)):
        return None
    age_s = now - ts
    if age_s > LIVE_WINDOW_S or age_s < 0:
        return None
    cwd = raw.get("cwd") or ""
    return {
        "session_id": raw.get("session_id", path.stem),
        "project": Path(cwd).name if cwd else None,
        "stage": raw.get("stage"),
        "pct": raw.get("pct"),
        "used_tokens": raw.get("used_tokens"),
        "window": raw.get("window"),
        "age_s": round(age_s, 1),
    }


def _unavailable(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "checked_dir": str(CEILING_DIR),
        "sessions": [],
        "counts": {"live": 0, "handoff": 0, "hard": 0},
    }


def _list_state_files() -> list[Path] | None:
    """The session state files, or None if the directory cannot be listed.

    A directory that exists but cannot be LISTED (permissions, a transient
    mount issue) is "cannot see", not "zero sessions" — `glob()` failing here
    must never be read the same as an empty, genuinely-checked directory.
    """
    try:
        return list(CEILING_DIR.glob("*.json"))
    except OSError as exc:
        log.debug("claude_session_hud: directory unreadable: %s", exc)
        return None


def claude_session_hud() -> dict:
    """Live Claude Code sessions on THIS host, read from the context-ceiling state dir.

    Never fabricates: an absent/unreadable directory returns `available: False`
    with the exact path checked, so a proxy-fallback reader (see
    dashboard/lib/pi-ceo-fetch.ts) cannot mistake "cannot see" for "nothing running".
    """
    if not CEILING_DIR.is_dir():
        return _unavailable("state directory absent on this host")

    paths = _list_state_files()
    if paths is None:
        return _unavailable("state directory unreadable")

    now = time.time()
    sessions = [e for e in (_read_one(p, now) for p in paths) if e is not None]
    sessions.sort(key=lambda s: s["age_s"])

    return {
        "available": True,
        "reason": None,
        "checked_dir": str(CEILING_DIR),
        "sessions": sessions,
        "counts": {
            "live": len(sessions),
            "handoff": sum(1 for s in sessions if s["stage"] == "handoff"),
            "hard": sum(1 for s in sessions if s["stage"] == "hard"),
        },
    }
