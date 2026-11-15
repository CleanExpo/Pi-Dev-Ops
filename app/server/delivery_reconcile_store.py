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
        seen.add(mid)
        old = missions.get(mid)
        old = old if isinstance(old, dict) else {}
        missions[mid] = {**rec, "first_seen": _first_seen(old, now), "last_seen": now}
    return seen


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _first_seen(old: dict[str, Any], now: float) -> float:
    """The stored first-seen time; a future, missing or non-numeric one is replaced by ``now``."""
    value = old.get("first_seen")
    return value if _number(value) and value <= now else now


def _merge_alerts(
    alerts: dict[str, Any], findings: list[dict[str, Any]], now: float
) -> tuple[list[str], set[str]]:
    """Returns (keys first seen this tick, every key raised this tick)."""
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
        if not isinstance(old, dict):
            new_keys.append(key)
            alerts[key] = {**fnd, "first_seen": now, "last_seen": now, "count": 1}
        else:
            count = old.get("count")
            count = count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0
            alerts[key] = {**old, **fnd, "first_seen": _first_seen(old, now), "last_seen": now,
                           "count": count + 1}  # a bad stored count restarts; it never fails the tick
    return new_keys, counted


def _drop_alerts(alerts: dict[str, Any], subjects: set[str], raised: set[str]) -> None:
    for key in [k for k, a in alerts.items()
                if k not in raised and (not isinstance(a, dict) or a.get("mission_id") in subjects)]:
        del alerts[key]


def _retain(state: dict[str, Any], keep: set[str]) -> None:
    """Complete tick only: drop subjects neither read whole nor held, and the alerts that point at them."""
    gone = {m for m in state["missions"] if m not in keep}
    for mid in gone:
        del state["missions"][mid]
    _drop_alerts(state["alerts"], gone, set())


# THE RULE (one owner): a stored alert is dropped or hidden only when its own subject was read WHOLE
# this tick. ``held`` (the tick's ``not_refreshed_ids``) names every subject whose read was cut, failed
# or came back not whole: its stored alerts stay and the status tile shows them, and it is never
# dropped. Its record: what the tick emitted for it replaces the stored one (a failed read emits UNKNOWN,
# spec row 1; first_seen is kept); a subject the budget cut emits nothing, so its record stays as it was
# (spec line 112). A subject read whole keeps only the alerts that read raised again.
def apply_tick(
    state: dict[str, Any],
    records: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    now: float,
    complete: bool,
    held: Any = (),
) -> tuple[dict[str, Any], list[str]]:
    """Pure merge of one tick. Returns (new_state, keys first seen this tick)."""
    out = copy.deepcopy(state)
    keep = {h for h in held if isinstance(h, str)}
    seen = _merge_missions(out["missions"], copy.deepcopy(records), now)
    new_keys, raised = _merge_alerts(out["alerts"], copy.deepcopy(findings), now)
    _drop_alerts(out["alerts"], seen - keep, raised)
    if complete:
        _retain(out, seen | keep)
        out["checkpoint"]["last_complete"] = now
    out["last_tick"] = now
    return out, new_keys
