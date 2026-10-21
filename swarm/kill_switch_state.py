"""swarm/kill_switch_state.py — the send gate and the panic flag's identity.

Split out of kill_switch.py (file-length limit); kill_switch re-exports
send_gate and panic_id, so callers import from one place.

send_gate() is one flock. Outbound sends hold it from the last halt check
through the send; trigger() holds it while it raises the flag; resume() holds
it while it checks and clears; panic_id() holds it while it observes.

Every panic writes a fresh random id and its time into the flag file itself
(Codex rounds on 9b8fc6d2 and 1922fa7f). A resume clears only the panic whose
id it observed, so nothing depends on a second file, on a counter surviving
corruption, or on the clock moving forward. An unreadable flag refuses every
resume and never blocks a panic, which rewrites it. A /panic sent in Telegram
also stores its Telegram message date (tg_at), so a Telegram /resume is
ordered against it by Telegram's clock alone, never the host's.
"""
from __future__ import annotations

import fcntl
import json
import logging
import math
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

log = logging.getLogger("swarm.kill_switch")

UNREADABLE = "!unreadable"  # an observation of an unreadable flag; matches no panic id


def _dir() -> Path:
    from . import config
    config.SWARM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return config.SWARM_LOG_DIR


def flag_path() -> Path:
    return _dir() / "kill_switch.flag"


@contextmanager
def send_gate() -> Iterator[None]:
    """Hold from the last halt check through an outbound send.

    trigger() takes the same lock before raising the flag, so a panic either
    lands first (the send sees it and stops) or waits for the in-flight send
    to finish. A send never starts after a panic has completed. Not re-entrant.
    """
    with (_dir() / "kill_switch.send_gate.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _time(v: object) -> bool:
    return (isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) and v > 0)


def _parse(raw: bytes) -> tuple[str, float, float | None] | None:
    """(id, unix time, Telegram date or None) from the flag's bytes, or None
    when malformed: undecodable bytes, a non-object, an empty id, or a time
    that is not a finite positive number (NaN and infinity included)."""
    try:
        text = raw.decode("utf-8").strip()
        rec = json.loads(text)
    except UnicodeDecodeError:
        return None
    except ValueError:
        rec = None
    if isinstance(rec, dict):
        pid, at, tg_at = rec.get("id"), rec.get("at"), rec.get("tg_at")
        ok = (isinstance(pid, str) and pid != "" and _time(at)
              and (tg_at is None or _time(tg_at)))
        return (pid, float(at), None if tg_at is None else float(tg_at)) if ok else None
    try:  # a flag written before panic ids existed holds only a timestamp
        at = datetime.fromisoformat(text).timestamp()
    except (ValueError, OverflowError, OSError):
        return None
    return (f"legacy:{text}", at, None) if _time(at) else None


def flag_state() -> tuple[str, str, float, float | None]:
    """(status, panic id, unix time, Telegram date of a Telegram /panic or None);
    status is "absent", "ok" or "unreadable" (then id "" and times 0.0/None)."""
    try:
        raw = flag_path().read_bytes()
    except FileNotFoundError:
        return "absent", "", 0.0, None
    except OSError as exc:
        log.error("kill_switch.flag unreadable (%s): resumes refused until a panic", exc)
        return "unreadable", "", 0.0, None
    parsed = _parse(raw)
    if parsed is None:
        log.error("kill_switch.flag unreadable: resumes refused until a panic rewrites it")
        return "unreadable", "", 0.0, None
    return "ok", *parsed


def panic_id() -> str:
    """What a resume must observe: the current panic's id, "" when none, or
    UNREADABLE. Taken under send_gate(), so it only sees a completed panic."""
    with send_gate():
        status, pid, _, _ = flag_state()
    return UNREADABLE if status == "unreadable" else pid


def write_flag(tg_at: float | None = None) -> str:
    """Write a fresh panic id and time into the flag (caller holds send_gate()).

    `tg_at` is the Telegram date of a /panic sent in Telegram, else None.
    Returns "engaged" or "already_engaged". Every panic changes the id, so no
    resume observed before it can clear it."""
    flag = flag_path()
    action = "already_engaged" if flag.exists() else "engaged"
    tmp = flag.with_name(flag.name + ".tmp")
    rec = {"id": uuid.uuid4().hex, "at": time.time(),
           "tg_at": tg_at if tg_at is not None and _time(tg_at) else None}
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    tmp.replace(flag)
    return action


__all__ = ["UNREADABLE", "flag_path", "flag_state", "panic_id", "send_gate", "write_flag"]
