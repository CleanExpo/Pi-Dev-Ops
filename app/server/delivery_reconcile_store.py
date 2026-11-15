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
import math
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


_MAX_TICK = 253402300799.0  # 9999-12-31T23:59:59Z: a later stored tick has no date


def _text_or_none(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _time_ok(value: Any) -> bool:
    return _number(value) and 0 <= value <= _MAX_TICK


_TIMES = ("first_seen", "last_seen")  # the merge writes both on every stored record and alert


def _entry_ok(entry: Any, text_keys: tuple[str, ...], time_keys: tuple[str, ...]) -> bool:
    """A stored entry: a dict with text keys; ``text_keys`` text (or null) where present, and every one of
    ``time_keys`` PRESENT and a finite time in range. Nothing absent or of the wrong shape is repaired."""
    return isinstance(entry, dict) and all(isinstance(k, str) for k in entry) \
        and all(_text_or_none(entry[k]) for k in text_keys if k in entry) \
        and all(_time_ok(entry.get(k)) for k in time_keys)


def _record_ok(rid: str, record: Any) -> bool:
    prs = record.get("prs", []) if isinstance(record, dict) else None
    refreshed = record.get("refreshed_at", 0) if isinstance(record, dict) else None  # optional: classified only
    return _entry_ok(record, ("stage", "kind", "repo", "ref", "project_id"), _TIMES) and _time_ok(refreshed) \
        and record.get("id") == rid and isinstance(prs, list) and all(_entry_ok(p, ("repo", "state"), ()) for p in prs)


def _alert_ok(key: str, alert: Any) -> bool:
    count = alert.get("count") if isinstance(alert, dict) else None
    text = ("mission_id", "code", "severity", "ref", "since", "age_source", "next_owner", "message", "url", "repo")
    return _entry_ok(alert, text, _TIMES) \
        and alert.get("key") == key and isinstance(count, int) and not isinstance(count, bool) and count >= 1


def _summary_ok(summary: Any) -> bool:
    ids = summary.get("not_refreshed_ids", []) if isinstance(summary, dict) else None
    return isinstance(ids, list) and all(isinstance(i, str) for i in ids)


def _tick_ok(value: Any) -> bool:
    return value is None or _time_ok(value)


# The one owner of "this file is ours": the store and the status tile both load through here. The file
# has one writer, so any entry of the wrong shape means it is not ours: ``state_unreadable``, untouched.
def _valid_shape(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    cp, missions, alerts = data.get("checkpoint"), data.get("missions"), data.get("alerts")
    if not (isinstance(missions, dict) and isinstance(alerts, dict) and isinstance(cp, dict)
            and "last_complete" in cp and _tick_ok(cp["last_complete"]) and _tick_ok(data.get("last_tick"))):
        return False
    return all(_record_ok(k, r) for k, r in missions.items()) and all(_alert_ok(k, a) for k, a in alerts.items()) \
        and ("summary" not in data or _summary_ok(data["summary"]))


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
    """A finite number; an int never goes through float (a huge JSON int would overflow, not fail)."""
    return (isinstance(value, int) and not isinstance(value, bool)) \
        or (isinstance(value, float) and math.isfinite(value))


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
            alerts[key] = {**old, **fnd, "first_seen": _first_seen(old, now), "last_seen": now,
                           "count": old["count"] + 1}  # ``load`` proved the stored count present and whole
    return new_keys, counted


# THE RULE (one owner; RA-8100 B6 lead ruling, D33): nothing is inferred from absence. The tick passes two
# positively built sets: ``whole``, the subjects whose own read was proven whole on this tick, and ``scope``,
# the full scope list, which exists only when every scope-defining list was read whole (else None).
# On a tick that is ``complete`` a stored alert is removed only when its subject is in ``whole`` and it was
# not raised again, or ``scope`` is known and its subject is not in it; a stored record is removed only
# when ``scope`` is known, its subject is not in it and the tick did not emit it. Nothing else is ever
# removed: an incomplete tick, an emitted subject missing from ``whole``, a subject neither proven nor
# known out of scope, and an alert with no subject all keep everything. ``complete`` without a ``scope``
# disagrees with itself and removes nothing at all. ``not_refreshed_ids`` is only what the tile reports; removal never reads it.
# The status tile shows exactly the alerts stored (``shown_alerts``); it never re-filters them.
def _retire_alerts(alerts: dict[str, Any], raised: set[str], whole: set[str], scope: set[str]) -> None:
    def gone(subject: Any) -> bool:
        return isinstance(subject, str) and (subject in whole or subject not in scope)

    for key in [k for k, a in alerts.items() if k not in raised and isinstance(a, dict) and gone(a.get("mission_id"))]:
        del alerts[key]


def shown_alerts(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The alerts THE RULE kept, which the tile shows: every stored alert, never re-filtered."""
    alerts = state.get("alerts")
    return [a for a in alerts.values() if isinstance(a, dict)] if isinstance(alerts, dict) else []


def _texts(values: Any) -> set[str]:
    return {v for v in values if isinstance(v, str)}


def apply_tick(
    state: dict[str, Any],
    records: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    now: float,
    complete: bool,
    whole: Any = (),
    scope: Any = None,
) -> tuple[dict[str, Any], list[str]]:
    """Pure merge of one tick. Returns (new_state, keys first seen this tick)."""
    out = copy.deepcopy(state)
    seen = _merge_missions(out["missions"], copy.deepcopy(records), now)
    new_keys, raised = _merge_alerts(out["alerts"], copy.deepcopy(findings), now)
    if complete and scope is not None:  # a complete tick without a scope disagrees with itself: no removal
        inside = _texts(scope)
        _retire_alerts(out["alerts"], raised, _texts(whole), inside)
        for mid in [m for m in out["missions"] if m not in inside | seen]:
            del out["missions"][mid]  # left scope: absent from a scope list read whole
    if complete:
        out["checkpoint"]["last_complete"] = now
    out["last_tick"] = now
    return out, new_keys
