"""RA-8100 delivery reconcile store: lease, atomic save, strict load, pure tick merge.

Independent of delivery_closure: records and findings are plain dicts.
  record:  {"id": str, ...}           (mission or orphan-PR identifier)
  finding: {"key": str, "mission_id": str | None, ...}
State keys: version, missions, alerts, checkpoint, last_tick.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


class StoreError(Exception):
    """State file unreadable or input malformed. Never means "empty"."""


def empty_state() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "missions": {},
        "alerts": {},
        "checkpoint": {"last_complete": None},
        "last_tick": None,
    }


@contextmanager
def lease(path: str | os.PathLike[str]) -> Iterator[bool]:
    """Non-blocking exclusive lock on a fresh descriptor. Yields False if held."""
    fd = os.open(os.fspath(path), os.O_RDWR | os.O_CREAT, 0o600)
    got = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except OSError:
            got = False
        yield got
    finally:
        if got:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _valid_shape(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    cp = data.get("checkpoint")
    return (
        isinstance(data.get("missions"), dict)
        and isinstance(data.get("alerts"), dict)
        and isinstance(cp, dict)
        and "last_complete" in cp
    )


def load(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Missing file gives empty state. Corrupt or wrong shape raises StoreError."""
    p = Path(path)
    try:
        raw = p.read_bytes()
    except FileNotFoundError:
        return empty_state()
    except OSError as exc:
        raise StoreError(f"state_unreadable:{type(exc).__name__}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise StoreError("state_corrupt") from exc
    if not _valid_shape(data):
        raise StoreError("state_wrong_shape")
    data.setdefault("version", SCHEMA_VERSION)
    data.setdefault("last_tick", None)
    return data


def save(path: str | os.PathLike[str], state: dict[str, Any]) -> bool:
    """Atomic write. Returns False (never raises) and leaves the old file intact."""
    target = os.fspath(path)
    directory = os.path.dirname(target) or "."
    tmp: str | None = None
    try:
        os.makedirs(directory, exist_ok=True)
        payload = json.dumps(state, sort_keys=True, indent=1)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        return True
    except (OSError, TypeError, ValueError):
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False


def _merge_missions(
    missions: dict[str, Any], records: list[dict[str, Any]], now: float
) -> set[str]:
    seen: set[str] = set()
    for rec in records:
        mid = rec.get("id") if isinstance(rec, dict) else None
        if not isinstance(mid, str) or not mid:
            raise StoreError("record_missing_id")
        old = missions.get(mid, {})
        merged = {**rec, "first_seen": old.get("first_seen", now), "last_seen": now}
        missions[mid] = merged
        seen.add(mid)
    return seen


def _merge_alerts(
    alerts: dict[str, Any], findings: list[dict[str, Any]], now: float
) -> list[str]:
    new_keys: list[str] = []
    counted: set[str] = set()
    for fnd in findings:
        key = fnd.get("key") if isinstance(fnd, dict) else None
        if not isinstance(key, str) or not key:
            raise StoreError("finding_missing_key")
        if key in counted:
            continue
        counted.add(key)
        old = alerts.get(key)
        if old is None:
            new_keys.append(key)
            alerts[key] = {**fnd, "first_seen": now, "last_seen": now, "count": 1}
        else:
            alerts[key] = {**old, "last_seen": now, "count": int(old.get("count", 0)) + 1}
    return new_keys


def _retain(state: dict[str, Any], seen: set[str]) -> None:
    """Complete tick only: drop missions not seen, and the alerts that point at them."""
    gone = {m for m in state["missions"] if m not in seen}
    for mid in gone:
        del state["missions"][mid]
    for key in [k for k, a in state["alerts"].items() if a.get("mission_id") in gone]:
        del state["alerts"][key]


def apply_tick(
    state: dict[str, Any],
    records: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    now: float,
    complete: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Pure merge of one tick. Returns (new_state, keys first seen this tick)."""
    out = copy.deepcopy(state)
    seen = _merge_missions(out["missions"], copy.deepcopy(records), now)
    new_keys = _merge_alerts(out["alerts"], copy.deepcopy(findings), now)
    if complete:
        _retain(out, seen)
        out["checkpoint"]["last_complete"] = now
    out["last_tick"] = now
    return out, new_keys
