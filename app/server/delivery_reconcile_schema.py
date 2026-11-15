"""RA-8100 delivery reconcile: THE one definition of the state file's shape (founder ruling D48).

``store.save`` and ``store.load`` both call ``problems``: a field the writer emits that this file does
not name fails the save, and a file missing a field the writer always writes fails the load. Every
dict below is an allow-list: each key has one check, every key is required unless listed in
``OPTIONAL``, and a key that is not named is rejected. Nothing is repaired or defaulted on load.
The tick's summary is built from ``SUMMARY`` (``new_summary``) and the tile's counters are read from it
(``TILE_COUNTERS``), so the writer, the loader and the tile share this one list.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

SCHEMA_VERSION = 1
MAX_TIME = 253402300799.0  # 9999-12-31T23:59:59Z: a later stored time has no date

Check = Callable[[Any], bool]


def number(value: Any) -> bool:
    """A finite number; an int never goes through float (a huge JSON int would overflow, not fail)."""
    return (isinstance(value, int) and not isinstance(value, bool)) \
        or (isinstance(value, float) and math.isfinite(value))


def text(value: Any) -> bool:
    return isinstance(value, str)


def name(value: Any) -> bool:
    """An identifier: text that is not empty (a subject, a key)."""
    return isinstance(value, str) and value != ""


def opt_text(value: Any) -> bool:
    return value is None or isinstance(value, str)


def null(value: Any) -> bool:
    return value is None


def flag(value: Any) -> bool:
    return isinstance(value, bool)


def time(value: Any) -> bool:
    return number(value) and 0 <= value <= MAX_TIME


def opt_time(value: Any) -> bool:
    return value is None or time(value)


def count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def positive(value: Any) -> bool:
    return count(value) and value >= 1


def texts(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def one_of(*allowed: str) -> Check:
    return lambda value: isinstance(value, str) and value in allowed


def mapping(check: Check) -> Check:
    """A dict with text keys whose every value passes ``check`` (a tally, a reason table)."""
    return lambda value: isinstance(value, dict) and all(isinstance(k, str) and check(v) for k, v in value.items())


def opt(check: Check) -> Check:
    return lambda value: value is None or check(value)


def shape(spec: dict[str, Check], optional: frozenset[str] = frozenset()) -> Check:
    """A dict holding exactly the keys of ``spec`` (those in ``optional`` may be absent), each passing its check."""
    def ok(value: Any) -> bool:
        return isinstance(value, dict) and all(isinstance(k, str) and k in spec for k in value) \
            and all(k in value for k in spec if k not in optional) \
            and all(spec[k](v) for k, v in value.items())
    return ok


_SEEN: dict[str, Check] = {"first_seen": time, "last_seen": time}  # the merge writes both on every entry

PR: dict[str, Check] = {"repo": text, "number": positive, "state": one_of("open", "closed", "merged", "error")}

_PLACED: dict[str, Check] = {  # ``delivery_stage._record`` plus ``Run.take`` (``refreshed_at``)
    "id": name, "project_id": text, "repo": text, "ref": text, "stage": text, "reason": opt_text,
    "owner": opt_text, "since": opt_text, "age_source": opt_text, "counted": null,
    "prs": lambda value: isinstance(value, list) and all(shape(PR)(item) for item in value),
    "pr_head_sha": opt_text, "reviewed_head_sha": opt_text, "authorised_head_sha": opt_text,
    "merge_sha": opt_text, "deployed_sha": opt_text, "verified_sha": opt_text, "tests_passed": flag,
    "acceptance_passed": flag, "live_source_provable": flag, "approval_identity_unverified": flag,
    "refreshed_at": time, **_SEEN}

RECORDS: dict[str, dict[str, Check]] = {  # one typed record per ``kind``
    "mission": {"kind": one_of("mission"), **_PLACED},
    "orphan_pr": {"kind": one_of("orphan_pr"), **_PLACED},
    "repo": {"kind": one_of("repo"), "id": name, "repo": text, "ref": text, "stage": one_of("repo"),  # ``repo_findings``
             "live_source": one_of("provable", "live_unconfirmed", "none"), "live_unconfirmed": opt_text,
             "merged_unverifiable": count, "counted": null, **_SEEN},
}

ALERT: dict[str, Check] = {  # ``delivery_stage._finding`` plus the merge's ``count``
    "key": name, "mission_id": name, "code": text, "severity": text, "next_owner": text, "message": text,
    "ref": text, "repo": text, "since": opt_text, "age_source": opt_text, "url": opt_text,
    "count": positive, **_SEEN}

# name: (check, the zero the tick starts from, shown on the tile as a counter)
SUMMARY_FIELDS: dict[str, tuple[Check, Callable[[], Any], bool]] = {
    "tick_at": (text, str, False), "complete": (flag, bool, False), "missions": (count, int, True),
    "by_severity": (mapping(count), dict, False), "by_code": (mapping(count), dict, False),
    "founder_or_critical": (texts, list, False), "skipped_repos": (texts, list, True),
    "unqueryable_projects": (texts, list, True), "refs_outside_scope": (count, int, True),
    "bot_prs": (count, int, True), "closed_unmerged": (count, int, True),
    "started_without_pr": (count, int, True), "completed_without_pr": (count, int, True),
    "not_refreshed": (count, int, True), "not_refreshed_ids": (texts, list, False),
    "vercel_unreadable": (count, int, True), "incomplete": (mapping(text), dict, True),
    "budget_left": (opt(mapping(count)), lambda: None, False),
}
SUMMARY: dict[str, Check] = {**{name: row[0] for name, row in SUMMARY_FIELDS.items()}, "error": text}
OPTIONAL = frozenset({"error"})  # the only key a stored summary may lack: a tick with no error has none
TILE_COUNTERS: tuple[str, ...] = tuple(name for name, row in SUMMARY_FIELDS.items() if row[2])

CHECKPOINT: dict[str, Check] = {"last_complete": opt_time}
STATE: tuple[str, ...] = ("version", "missions", "alerts", "checkpoint", "last_tick", "summary")


def new_summary(tick_at: str) -> dict[str, Any]:
    """Every summary key the tick always writes, zeroed."""
    return {**{name: row[1]() for name, row in SUMMARY_FIELDS.items()}, "tick_at": tick_at}


def _record_ok(rid: str, record: Any) -> bool:
    kind = record.get("kind") if isinstance(record, dict) else None
    spec = RECORDS.get(kind) if isinstance(kind, str) else None
    return spec is not None and shape(spec)(record) and record["id"] == rid


def _alert_ok(key: str, alert: Any) -> bool:
    return shape(ALERT)(alert) and alert["key"] == key


def _keyed(value: Any, entry_ok: Callable[[str, Any], bool], where: str) -> list[str]:
    if not isinstance(value, dict):
        return [where]
    return [f"{where}[{i}]" for i, (key, entry) in enumerate(value.items())
            if not (isinstance(key, str) and entry_ok(key, entry))]


def problems(data: Any) -> list[str]:
    """Where ``data`` is not a state file of ours (positions and key names only, never a stored value);
    an empty list means it is whole. A tick has run exactly when ``last_tick`` is set, and then, and only
    then, the summary is present and whole."""
    if not (isinstance(data, dict) and set(data) == set(STATE)):
        return ["state"]
    out = [] if data["version"] == SCHEMA_VERSION and not isinstance(data["version"], bool) else ["version"]
    out += _keyed(data["missions"], _record_ok, "missions") + _keyed(data["alerts"], _alert_ok, "alerts")
    out += [] if shape(CHECKPOINT)(data["checkpoint"]) else ["checkpoint"]
    out += [] if opt_time(data["last_tick"]) else ["last_tick"]
    never_run = data["last_tick"] is None
    summary_ok = data["summary"] is None if never_run else shape(SUMMARY, OPTIONAL)(data["summary"])
    return out + ([] if summary_ok else ["summary"])
