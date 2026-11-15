"""RA-8100 delivery reconcile store: lease, atomic save, strict load, pure tick merge.

Independent of delivery_closure: records and findings are plain dicts.
  record:  {"id": str, ...}           (mission or orphan-PR identifier)
  finding: {"key": str, "mission_id": str | None, ...}
The file's shape has one definition, ``delivery_reconcile_schema``: ``save`` and ``load`` both call it.
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

from . import delivery_reconcile_schema as schema

SCHEMA_VERSION = schema.SCHEMA_VERSION


class StoreError(Exception):
    """State file unreadable or input malformed. Never means "empty"."""


def empty_state() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "missions": {},
        "alerts": {},
        "checkpoint": {"last_complete": None},
        "last_tick": None,
        "summary": None,  # no tick has run: the schema allows None exactly while ``last_tick`` is None
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


# The one owner of "this file is ours": the store and the status tile both load through here, and the
# check is the schema's, the same one ``save`` runs. The file has one writer, so anything the schema does
# not accept means it is not ours: ``state_unreadable``, untouched. Nothing is repaired or defaulted.
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
    if schema.problems(data):
        raise StoreError("state_wrong_shape")
    return data


def save(path: str | os.PathLike[str], state: dict[str, Any]) -> bool:
    """Atomic write of a state the schema accepts. Returns False (never raises) and leaves the old file
    intact: a state the loader would refuse is never written."""
    if schema.problems(state):
        return False
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


def _first_seen(old: dict[str, Any], now: float) -> float:
    """The stored first-seen time; a future, missing or non-numeric one is replaced by ``now``."""
    value = old.get("first_seen")
    return value if schema.number(value) and value <= now else now


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
            alerts[key] = {**old, **fnd, "first_seen": _first_seen(old, now), "last_seen": now,
                           "count": old["count"] + 1}  # ``load`` proved the stored count present and whole
    return new_keys, counted


# THE RULE (one owner; RA-8100 B6 lead ruling D33, and founder ruling D48): nothing is inferred from absence.
# The tick passes two positively built sets: ``whole``, the subjects whose own read was proven whole on this
# tick, and ``scope``, the full scope list, which exists only when every scope-defining list was read whole
# (else None). ``complete`` is not a third input: it IS "the scope is known" (``complete`` below, its one
# owner), so the stored flag, the checkpoint and the removal rule cannot disagree.
# On a complete tick a stored alert is removed only when its subject is in ``whole`` and it was not raised
# again, or its subject is not in ``scope``; a stored record is removed, by the same two tests, only when
# the tick did not emit it and its subject is in ``whole`` (read whole and no longer placed, for example a
# mission whose only pull closed) or is not in ``scope``. Nothing else is ever removed: an incomplete tick, an emitted
# subject missing from ``whole``, a subject neither proven nor known out of scope, and an alert with no
# subject all keep everything. ``not_refreshed_ids`` is only what the tile reports; removal never reads it.
# The status tile shows exactly the alerts stored (``shown_alerts``); it never re-filters them.
def complete(scope: Any) -> bool:
    """THE one definition of a complete tick: its scope is known. Nothing else may decide it."""
    return scope is not None


def _retire_alerts(alerts: dict[str, Any], raised: set[str], whole: set[str], scope: set[str]) -> None:
    def gone(subject: Any) -> bool:
        return isinstance(subject, str) and (subject in whole or subject not in scope)

    for key in [k for k, a in alerts.items() if k not in raised and isinstance(a, dict) and gone(a.get("mission_id"))]:
        del alerts[key]


def shown_alerts(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The alerts THE RULE kept, which the tile shows: every stored alert, never re-filtered. The state
    came through ``load``, so nothing is skipped or defaulted here: a wrong shape raises, it is not empty."""
    return list(state["alerts"].values())


def _texts(values: Any) -> set[str]:
    return {v for v in values if isinstance(v, str)}


def apply_tick(
    state: dict[str, Any],
    records: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    now: float,
    whole: Any = (),
    scope: Any = None,
    summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Pure merge of one tick. Returns (new_state, keys first seen this tick). The stored summary is
    ``summary`` with ``complete`` set here, from the scope: a caller's own value is never kept. With no
    summary none is invented: the state then has a tick and no summary, which ``save`` refuses."""
    out = copy.deepcopy(state)
    done = complete(scope)
    seen = _merge_missions(out["missions"], copy.deepcopy(records), now)
    new_keys, raised = _merge_alerts(out["alerts"], copy.deepcopy(findings), now)
    if done:
        inside, proven = _texts(scope), _texts(whole)
        _retire_alerts(out["alerts"], raised, proven, inside)
        for mid in [m for m in out["missions"] if m not in seen and (m in proven or m not in inside)]:
            del out["missions"][mid]  # read whole and no longer emitted, or absent from a scope read whole
        out["checkpoint"]["last_complete"] = now
    out["last_tick"] = now
    out["summary"] = None if summary is None else {**copy.deepcopy(summary), "complete": done}
    return out, new_keys
