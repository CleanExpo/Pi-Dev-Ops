"""RA-8100 B1: delivery reconcile store (lease, load, save, apply_tick)."""
from __future__ import annotations

import copy
import importlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.server import delivery_reconcile_store as store


def _rec(mid: str = "M1", **extra: Any) -> dict[str, Any]:
    return {"id": mid, "stage": "BUILDING", **extra}


def _fnd(key: str = "K1", mid: str = "M1", **extra: Any) -> dict[str, Any]:
    return {"key": key, "mission_id": mid, "code": "X", **extra}


def test_missing_file_gives_empty_state(tmp_path: Path) -> None:
    state = store.load(tmp_path / "absent.json")
    assert state["missions"] == {}
    assert state["alerts"] == {}
    assert state["checkpoint"]["last_complete"] is None


@pytest.mark.parametrize("body", [b"{not json", b"", b"[]", b'{"missions": 3}'])
def test_corrupt_or_wrong_shape_raises_and_is_untouched(tmp_path: Path, body: bytes) -> None:
    p = tmp_path / "s.json"
    p.write_bytes(body)
    with pytest.raises(store.StoreError):
        store.load(p)
    assert p.read_bytes() == body


def test_save_load_round_trip(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    state, _ = store.apply_tick(store.empty_state(), [_rec()], [_fnd()], 100.0, True)
    assert store.save(p, state) is True
    assert store.load(p) == state


def test_save_failure_keeps_old_bytes_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "s.json"
    old, _ = store.apply_tick(store.empty_state(), [_rec()], [], 1.0, True)
    assert store.save(p, old)
    before = p.read_bytes()
    new, _ = store.apply_tick(old, [_rec("M2")], [], 2.0, True)

    def boom(*_a: Any, **_k: Any) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", boom)
    assert store.save(p, new) is False
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["s.json"]


def test_lease_exclusive_then_released(tmp_path: Path) -> None:
    lock = tmp_path / "s.lock"
    with store.lease(lock) as first:
        assert first is True
        with store.lease(lock) as second:
            assert second is False
    with store.lease(lock) as third:
        assert third is True


def test_lease_released_when_body_raises(tmp_path: Path) -> None:
    lock = tmp_path / "s.lock"
    with pytest.raises(RuntimeError):
        with store.lease(lock) as got:
            assert got
            raise RuntimeError("x")
    with store.lease(lock) as again:
        assert again is True


def test_apply_tick_is_pure() -> None:
    state, _ = store.apply_tick(store.empty_state(), [_rec()], [_fnd()], 1.0, True)
    snap = copy.deepcopy(state)
    recs, fnds = [_rec("M2")], [_fnd("K2", "M2")]
    rsnap, fsnap = copy.deepcopy(recs), copy.deepcopy(fnds)
    out, _ = store.apply_tick(state, recs, fnds, 2.0, True)
    assert state == snap and recs == rsnap and fnds == fsnap
    assert out is not state


def test_five_ticks_dedupe_alert() -> None:
    state = store.empty_state()
    news: list[list[str]] = []
    for i in range(1, 6):
        state, new = store.apply_tick(state, [_rec()], [_fnd()], float(i), True)
        news.append(new)
    assert news == [["K1"], [], [], [], []]
    assert list(state["alerts"]) == ["K1"]
    assert state["alerts"]["K1"]["count"] == 5
    assert state["alerts"]["K1"]["first_seen"] == 1.0
    assert state["alerts"]["K1"]["last_seen"] == 5.0
    assert len(state["missions"]) == 1


def test_duplicate_key_in_one_tick_counts_once() -> None:
    state, new = store.apply_tick(store.empty_state(), [_rec()], [_fnd(), _fnd()], 1.0, True)
    assert new == ["K1"] and state["alerts"]["K1"]["count"] == 1


def test_incomplete_tick_keeps_checkpoint_and_removes_nothing() -> None:
    state, _ = store.apply_tick(
        store.empty_state(), [_rec("A"), _rec("B")], [_fnd("KA", "A"), _fnd("KB", "B")], 10.0, True
    )
    out, _ = store.apply_tick(state, [_rec("A")], [_fnd("KA", "A")], 20.0, False)
    assert out["checkpoint"]["last_complete"] == 10.0
    assert set(out["missions"]) == {"A", "B"}
    assert set(out["alerts"]) == {"KA", "KB"}
    assert out["alerts"]["KB"]["count"] == 1


def test_complete_tick_advances_checkpoint_and_retains_scope() -> None:
    state, _ = store.apply_tick(
        store.empty_state(), [_rec("A"), _rec("B")], [_fnd("KA", "A"), _fnd("KB", "B")], 10.0, True
    )
    out, _ = store.apply_tick(state, [_rec("A")], [_fnd("KA", "A")], 20.0, True)
    assert out["checkpoint"]["last_complete"] == 20.0
    assert set(out["missions"]) == {"A"}
    assert set(out["alerts"]) == {"KA"}


def test_alert_retired_only_when_its_subject_is_read_whole() -> None:
    state, _ = store.apply_tick(store.empty_state(), [_rec()], [_fnd()], 1.0, True)
    held, _ = store.apply_tick(state, [_rec()], [], 2.0, True, held=["M1"])
    assert held["alerts"]["K1"]["count"] == 1 and held["alerts"]["K1"]["last_seen"] == 1.0
    out, _ = store.apply_tick(state, [_rec()], [], 2.0, True)
    assert "K1" not in out["alerts"]


def test_mission_first_seen_kept() -> None:
    state, _ = store.apply_tick(store.empty_state(), [_rec()], [], 1.0, True)
    out, _ = store.apply_tick(state, [_rec(stage="MERGED")], [], 9.0, True)
    assert out["missions"]["M1"]["first_seen"] == 1.0
    assert out["missions"]["M1"]["stage"] == "MERGED"


def test_malformed_input_raises() -> None:
    with pytest.raises(store.StoreError):
        store.apply_tick(store.empty_state(), [{"stage": "x"}], [], 1.0, True)
    with pytest.raises(store.StoreError):
        store.apply_tick(store.empty_state(), [], [{"code": "x"}], 1.0, True)


def test_restored_job_keeps_alert_first_seen(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    state, _ = store.apply_tick(store.empty_state(), [_rec()], [_fnd()], 1.0, True)
    assert store.save(p, state)
    fresh = importlib.reload(store)
    out, new = fresh.apply_tick(fresh.load(p), [_rec()], [_fnd()], 2.0, True)
    assert new == []
    assert out["alerts"]["K1"]["first_seen"] == 1.0
    assert out["alerts"]["K1"]["count"] == 2
    assert out["checkpoint"]["last_complete"] == 2.0
    json.dumps(out)


def test_resighted_alert_takes_newest_fields_keeps_first_seen_and_count() -> None:
    first, _ = store.apply_tick(
        store.empty_state(), [_rec()], [_fnd(message="old", since="2026-01-01")], 10.0, True
    )
    second, new = store.apply_tick(
        first, [_rec()], [_fnd(message="new", since="2026-02-02")], 20.0, True
    )
    alert = second["alerts"]["K1"]
    assert new == []
    assert alert["message"] == "new" and alert["since"] == "2026-02-02"
    assert alert["first_seen"] == 10.0 and alert["last_seen"] == 20.0 and alert["count"] == 2
