"""One canonical Jev spend ledger per machine (.claude/done/spm/2026-10-28-jev-spend-ledger/spec.md).

Every TypeSafe request this repository sends reserves its worst case here before it leaves and settles
after the reply. The Guardian watcher sums `COALESCE(actual_usd, reserved_usd)` by UTC `day`.

Path: JEV_SPEND_LEDGER if set, else ~/.local/state/jev/spend.sqlite; resolved on every call, never at import.
A reserve that cannot be written raises SpendUnrecorded and the caller must not send. A settle never raises:
the row keeps its reserve, which overcounts (the safe direction). JEV_DAILY_CAP_USD, when set, caps the
machine's Jev spend per UTC day; unset is uncapped (founder decision 2026-09-28).
"""
from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)
DEFAULT = "~/.local/state/jev/spend.sqlite"
REFUSALS = "spend-refusals.jsonl"
TIMEOUT_S = 10.0
SCHEMA = ("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, day TEXT NOT NULL, caller TEXT NOT NULL, "
          "reserved_usd REAL NOT NULL, actual_usd REAL, input_tokens INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL)")
_now = time.time  # tests freeze this; every day and timestamp comes from it, in UTC


class SpendUnrecorded(RuntimeError):
    """The reserve could not be written; the request must not be sent."""


class SpendCapReached(RuntimeError):
    """JEV_DAILY_CAP_USD would be exceeded; the request must not be sent."""


def ledger_path() -> Path:
    raw = os.environ.get("JEV_SPEND_LEDGER")
    if raw is not None and not raw.strip():
        raise ValueError("JEV_SPEND_LEDGER is set but empty")
    path = Path(os.path.expanduser(DEFAULT if raw is None else raw))
    if not path.is_absolute() or path.is_dir():
        raise ValueError(f"JEV_SPEND_LEDGER must be an absolute file path, got {raw!r}")
    return path


def daily_cap() -> float | None:
    raw = os.environ.get("JEV_DAILY_CAP_USD", "").strip()
    if not raw:
        return None
    cap = float(raw)
    if not math.isfinite(cap) or cap <= 0:
        raise ValueError("JEV_DAILY_CAP_USD must be a positive finite number")
    return cap


def _stamp() -> tuple[str, str]:
    stamp = _now()
    moment = datetime.fromtimestamp(stamp, UTC)
    return moment.date().isoformat(), moment.isoformat()


def _note_dir() -> Path | None:
    """Where refusal lines go: beside the configured ledger. A configured path that is empty or relative
    names no directory, and the line is only logged (it must never land in some other ledger's folder)."""
    raw = os.environ.get("JEV_SPEND_LEDGER")
    path = Path(os.path.expanduser(DEFAULT if raw is None else raw))
    if raw is not None and not raw.strip() or not path.is_absolute():
        return None
    return path.parent


def _note(kind: str, caller: str, exc: BaseException | None, row: int | None = None) -> None:
    """Best effort: one JSON line beside the ledger, and one error log line. Never request text."""
    entry = {"kind": kind, "caller": caller, "ledger": os.environ.get("JEV_SPEND_LEDGER", DEFAULT), "row": row,
             "at": _stamp()[1], "error": type(exc).__name__ if exc else None, "errno": getattr(exc, "errno", None)}
    log.error("jev spend %s: %s", kind, json.dumps(entry, sort_keys=True))
    target = _note_dir()
    if target is None:
        return
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(target / REFUSALS, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=TIMEOUT_S, isolation_level=None)
    db.execute(SCHEMA)
    db.execute("CREATE INDEX IF NOT EXISTS calls_day ON calls(day)")
    return db


def reserve(caller: str, reserved_usd: float) -> int:
    """Record one attempted request before it is sent; return its row id."""
    try:
        target = ledger_path()
        cap = daily_cap()
        day, created = _stamp()
        with contextlib.closing(_connect(target)) as db:
            db.execute("BEGIN IMMEDIATE")
            spent = db.execute("SELECT COALESCE(SUM(COALESCE(actual_usd, reserved_usd)), 0) FROM calls WHERE day=?",
                               (day,)).fetchone()[0]
            if cap is not None and spent + reserved_usd > cap:
                db.execute("ROLLBACK")
                _note("cap_reached", caller, None)
                raise SpendCapReached(f"daily Jev cap ${cap} reached")
            row = db.execute("INSERT INTO calls(day, caller, reserved_usd, status, created_at) VALUES (?, ?, ?, 'attempted', ?)",
                             (day, caller, float(reserved_usd), created)).lastrowid
            db.execute("COMMIT")
        return int(row)
    except SpendCapReached:
        raise
    except (sqlite3.Error, OSError, ValueError) as exc:
        _note("reserve_failed", caller, exc)
        raise SpendUnrecorded(f"jev spend not recorded: {type(exc).__name__}") from exc


def finish(row: int, status: str, actual_usd: float | None = None, input_tokens: int | None = None) -> bool:
    """Settle a reserved row. Never raises: on failure the row keeps its reserve and a line is logged."""
    try:
        with contextlib.closing(_connect(ledger_path())) as db:
            db.execute("UPDATE calls SET status=?, actual_usd=?, input_tokens=? WHERE id=?",
                       (status, actual_usd, input_tokens, row))
        return True
    except Exception as exc:  # noqa: BLE001 — a settle failure must never lose a paid reply
        _note("settle_failed", "finish", exc, row)
        return False  # settle failed
