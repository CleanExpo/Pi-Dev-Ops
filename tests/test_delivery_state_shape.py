"""RA-8100 B6 part 3: the stored state file is checked deeply on load (one owner: ``store.load``).

The file has one writer, so a record or alert of the wrong shape means the file is not ours. It goes
down the existing ``state_unreadable`` path: the file is untouched, the tick reports it and the tile
says unreadable (never an exception). Numbers are strict too (finite, in range, counts whole and
positive), and every field the store always writes must be present: nothing is repaired. Every state ``apply_tick`` writes loads back.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from _delivery_reconcile_support import NOW, PIDEV, reg_entry, run, setup_tick, stored, tick_summary

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store


def _good() -> dict:
    state = store.empty_state()
    state["missions"]["M"] = stored({"id": "M", "stage": "done", "prs": [{"repo": PIDEV, "number": 4, "state": "open"}]})
    state["alerts"]["K"] = stored({"key": "K", "mission_id": "M", "code": "X", "severity": "critical"}, alert=True)
    state["summary"] = tick_summary(NOW.timestamp() - 60, False, not_refreshed_ids=["M"])
    state["last_tick"] = NOW.timestamp() - 60
    return state


_ABSENT = object()  # the field is removed: every field the store always writes must be present


def _set(state: dict, where: str, value: object) -> dict:
    *parents, last = where.split(".")
    target = state
    for part in parents:
        target = target[part]
    if value is _ABSENT:
        del target[last]
    else:
        target[last] = value
    return state


BAD = [
    ("alerts.K.mission_id", ["M"]), ("alerts.K.mission_id", {"id": "M"}), ("alerts.K.mission_id", 5),
    ("alerts.K.mission_id", None), ("alerts.K.mission_id", ""), ("alerts.K.key", _ABSENT), ("missions.M.kind", "other"),
    ("alerts.K.key", 5), ("alerts.K", ["K"]), ("alerts.K", "K"),
    ("missions.M", ["M"]), ("missions.M", None), ("missions.M.id", 7), ("missions.M.stage", ["done"]),
    ("missions.M.prs", "x"), ("missions.M.prs", [["x"]]),
    ("summary", []), ("summary.not_refreshed_ids", [["M"]]), ("summary.not_refreshed_ids", "M"),
    ("summary.not_refreshed_ids", [5]), ("last_tick", float("nan")), ("last_tick", 1e300), ("last_tick", float("inf")),
    ("last_tick", True), ("last_tick", "2026"), ("last_tick", -1e12), ("checkpoint.last_complete", ["x"]),
    ("alerts.K.count", "bad"), ("alerts.K.count", -1), ("alerts.K.count", 0), ("alerts.K.count", True),
    ("alerts.K.count", 1.5), ("alerts.K.first_seen", 9e99), ("alerts.K.first_seen", "bad"),
    ("alerts.K.first_seen", float("nan")), ("alerts.K.last_seen", None), ("alerts.K.key", "OTHER"),
    ("missions.M.first_seen", "bad"), ("missions.M.first_seen", -1.0), ("missions.M.last_seen", float("inf")),
    ("missions.M.refreshed_at", "x"), ("missions.M.project_id", ["p"]), ("missions.M.id", "OTHER"),
    ("alerts.K.ref", ["RA-1"]), ("alerts.K.since", 5), ("alerts.K.next_owner", 5), ("alerts.K.message", ["m"]),
    ("alerts.K.url", {"u": 1}), ("alerts.K.repo", 5),
    ("last_tick", 10**400), ("alerts.K.first_seen", 10**400), ("missions.M.refreshed_at", 10**400),
    ("alerts.K.count", _ABSENT), ("alerts.K.first_seen", _ABSENT), ("alerts.K.last_seen", _ABSENT),
    ("alerts.K.key", _ABSENT), ("missions.M.first_seen", _ABSENT), ("missions.M.last_seen", _ABSENT),
    ("missions.M.id", _ABSENT),
]


def _write(path: Path, state: dict) -> bytes:
    body = json.dumps(state).encode("utf-8")  # NaN and Infinity are written as JSON's NaN tokens
    path.write_bytes(body)
    return body


@pytest.mark.parametrize("where,value", BAD, ids=[f"{w}={'absent' if v is _ABSENT else repr(v)}"[:40] for w, v in BAD])
def test_a_wrong_shaped_entry_is_state_unreadable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, where: str,
                                                  value: object) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    body = _write(st.path, _set(_good(), where, value))
    with pytest.raises(store.StoreError):
        store.load(st.path)
    out = run(st)
    assert out.get("error") == "state_unreadable" and out["persisted"] is False
    assert st.path.read_bytes() == body and st.github == [] and st.gql == []
    tile = dr.status_snapshot(st.path, NOW)
    assert tile["state"] == "unreadable" and "state_unreadable" in tile["errors"]


def test_positive_control_a_normal_file_loads_and_shows(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    _write(path, _good())
    assert store.load(path)["missions"]["M"]["id"] == "M"
    tile = dr.status_snapshot(path, NOW)
    assert tile["state"] == "ok" and [i["code"] for i in tile["items"]] == ["X"]


def test_a_state_the_store_writes_always_loads(tmp_path: Path) -> None:
    state, _ = store.apply_tick(store.empty_state(), [stored({"id": "M", "stage": "done"})],
                                [stored({"key": "K", "mission_id": "OTHER", "code": "X"}, alert=True)], 1.0,
                                scope=["M"], summary=tick_summary(1.0, True))
    path = tmp_path / "state.json"
    assert store.save(path, state)
    assert store.load(path) == state


_RECORDS = [stored({"id": "M", "stage": "done", "project_id": "p", "repo": PIDEV,
                    "prs": [{"repo": PIDEV, "number": 4, "state": "open"}]}, 5.0),
            stored({"id": f"pr:{PIDEV}#9", "kind": "orphan_pr", "stage": "building"}),
            stored({"id": f"repo:{PIDEV}", "kind": "repo", "stage": "repo", "live_source": "live_unconfirmed"})]
_FINDINGS = [stored({"key": "K-M", "mission_id": "M", "code": "FALSE_DONE", "severity": "critical", "ref": "RA-1",
                     "next_owner": "founder", "message": "m"}, alert=True),
             stored({"key": "K-PR", "mission_id": f"pr:{PIDEV}#9", "code": "UNOWNED_24H", "severity": "reminder"},
                    alert=True),
             stored({"key": "K-NONE", "mission_id": "OTHER", "code": "INFO", "severity": "info"}, alert=True)]


def _ticks(seed: int) -> list[tuple]:
    """A deterministic spread of ticks: subsets of records and findings, ``whole`` and ``scope`` sets (or
    None: an incomplete tick)."""
    out = []
    for i in range(6):
        bits = (seed * 7 + i * 13) % 64
        out.append(([r for j, r in enumerate(_RECORDS) if bits >> j & 1],
                    [f for j, f in enumerate(_FINDINGS) if bits >> (j + 3) & 1],
                    ["M", f"pr:{PIDEV}#9", f"repo:{PIDEV}"][: bits % 4],
                    None if bits & 2 else ["M", f"repo:{PIDEV}"][: bits % 3]))
    return out


@pytest.mark.parametrize("seed", range(40))
def test_round_trip_every_state_apply_tick_writes_loads_as_valid(tmp_path: Path, seed: int) -> None:
    state, now, path = store.empty_state(), 1000.0 + seed, tmp_path / "state.json"
    for records, findings, whole, scope in _ticks(seed):
        state, _ = store.apply_tick(state, records, findings, now, whole=whole, scope=scope,
                                    summary=tick_summary(now, scope is not None))
        assert store.save(path, state)
        state, now = store.load(path), now + 600
