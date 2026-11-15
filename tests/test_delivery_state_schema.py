"""RA-8100 D48 part 2: ONE schema for the state file, used by the writer and the loader.

``store.save`` and ``store.load`` call the same validator (``delivery_reconcile_schema.problems``). The
cases below are not a hand-kept list of fields: they walk a state that a REAL tick wrote (a mission, an
orphan pull, a repo record, their alerts and the summary) and, for every key of every stored dict, remove
it, replace it with a wrong-shaped value, and add a key nobody named. Each must be refused on load and on
save. The producers' real output is compared with the schema key for key, so a field cannot be added to
a record, an alert or the summary without being named and checked.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, NOW, PIDEV, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick, stored, sweep_path, tick_issue,
)

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_gather as gather
from app.server import delivery_reconcile_schema as schema
from app.server import delivery_reconcile_status as status
from app.server import delivery_reconcile_store as store
from app.server import delivery_stage

ENTRIES = [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)]
WRONG = [["wrong-shape"]]  # a list holding a list: no field of the state file accepts it
NAMES = {"id", "key", "mission_id"}  # identifiers: text, and never empty


def _real_tick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """One real tick through the public entry: a mission with an open pull, an orphan pull, two repos."""
    st = setup_tick(monkeypatch, tmp_path, ENTRIES)
    st.gh.update({sweep_path(PIDEV): [open_pull(7), open_pull(9)], sweep_path(ATO): [], **pr_paths(PIDEV, 7)})
    st.gql_pages += [linear_page([tick_issue("RA-1", ((PIDEV, 7),))]), linear_page([])]
    st.out = run(st)
    assert st.out["persisted"] is True and st.out["complete"] is True, st.out
    st.state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    return st


def _dicts(state: dict) -> Iterator[tuple[str, dict, frozenset[str]]]:
    """(name, stored dict, keys it may lack) for every dict whose keys are FIELDS (not ids)."""
    yield "state", state, frozenset()
    yield "checkpoint", state["checkpoint"], frozenset()
    yield "summary", state["summary"], frozenset({"error"})
    for rid, record in state["missions"].items():
        yield f"record {rid}", record, frozenset()
        for i, pull in enumerate(record.get("prs", [])):
            yield f"record {rid} pull {i}", pull, frozenset()
    for key, alert in state["alerts"].items():
        yield f"alert {key}", alert, frozenset()


def _mutations(state: dict) -> Iterator[tuple[str, dict]]:
    """Every single-field fault: each key of each stored dict removed and wrong-shaped (an identifier also
    emptied), plus an unnamed key."""
    for index, (name, entry, optional) in enumerate(list(_dicts(state))):
        for key in list(entry):
            for label, change in (("absent", None), ("wrong", WRONG), ("empty", "")):
                if (label == "absent" and key in optional) or (label == "empty" and key not in NAMES):
                    continue
                bad = copy.deepcopy(state)
                target = list(_dicts(bad))[index][1]
                if label == "absent":
                    del target[key]
                else:
                    target[key] = copy.deepcopy(change)
                yield f"{name}: {key} {label}", bad
        bad = copy.deepcopy(state)
        list(_dicts(bad))[index][1]["zz_not_in_the_schema"] = "x"
        yield f"{name}: unnamed key", bad


def _refused(path: Path, bad: dict) -> bool:
    """Refused by the loader (and the tile says unreadable) AND by the writer, which leaves the file alone."""
    body = json.dumps(bad).encode("utf-8")
    path.write_bytes(body)
    try:
        store.load(path)
        return False
    except store.StoreError:
        pass
    tile = dr.status_snapshot(path, NOW)
    return tile["state"] == "unreadable" and tile["complete"] is False \
        and store.save(path, bad) is False and path.read_bytes() == body


def test_every_field_of_a_real_state_is_checked_on_load_and_on_save(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    st = _real_tick(monkeypatch, tmp_path)
    kinds = {record["kind"] for record in st.state["missions"].values()}
    assert kinds == {"mission", "orphan_pr", "repo"} and st.state["alerts"]  # the walk covers every record kind
    assert any(record["prs"] for record in st.state["missions"].values() if "prs" in record)
    cases = list(_mutations(st.state))
    assert len(cases) > 150  # the walk really found the fields
    scratch = tmp_path / "bad.json"
    accepted = [name for name, bad in cases if not _refused(scratch, bad)]
    assert accepted == []


def test_positive_control_the_real_state_loads_and_saves_unchanged(monkeypatch: pytest.MonkeyPatch,
                                                                  tmp_path: Path) -> None:
    st = _real_tick(monkeypatch, tmp_path)
    assert schema.problems(st.state) == [] and store.load(st.path) == st.state
    again = tmp_path / "again.json"
    assert store.save(again, st.state) is True and store.load(again) == st.state
    tile = dr.status_snapshot(st.path, NOW + timedelta(minutes=1))
    assert tile["state"] == "ok" and tile["complete"] is True and tile["counts"]["missions"] == 1


@pytest.mark.parametrize("summary", [{"complete": True}, {}, {"complete": True, "not_refreshed_ids": []}],
                         ids=["only-complete", "empty", "two-keys"])
def test_a_summary_with_missing_fields_is_unreadable_never_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                             summary: dict) -> None:
    """Codex round 6 finding 2, by its reproduction: the file loaded and the tile showed ok and complete."""
    st = _real_tick(monkeypatch, tmp_path)
    bad = {**st.state, "summary": summary}
    Path(st.path).write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(store.StoreError):
        store.load(st.path)
    tile = dr.status_snapshot(st.path, NOW + timedelta(minutes=1))
    assert tile["state"] == "unreadable" and tile["complete"] is False and tile["counts"] is None


@pytest.mark.parametrize("change", [{"summary": None}, {"last_tick": None}, {"version": 2}, {"version": True}],
                         ids=["ran-but-no-summary", "summary-but-never-ran", "other-version", "version-true"])
def test_tick_and_summary_must_agree_and_the_version_is_checked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                                change: dict) -> None:
    st = _real_tick(monkeypatch, tmp_path)
    Path(st.path).write_text(json.dumps({**st.state, **change}), encoding="utf-8")
    with pytest.raises(store.StoreError):
        store.load(st.path)
    assert dr.status_snapshot(st.path, NOW)["state"] == "unreadable"


def test_the_empty_state_is_whole_and_shows_never_run(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    assert schema.problems(store.empty_state()) == [] and store.save(path, store.empty_state()) is True
    assert store.load(path) == store.empty_state() == store.load(tmp_path / "missing.json")
    assert dr.status_snapshot(path, NOW)["state"] == "never_run"


def test_real_producer_output_matches_the_schema_key_for_key(monkeypatch: pytest.MonkeyPatch,
                                                            tmp_path: Path) -> None:
    st = _real_tick(monkeypatch, tmp_path)
    for record in st.state["missions"].values():
        assert set(record) == set(schema.RECORDS[record["kind"]]), record["id"]
    for alert in st.state["alerts"].values():
        assert set(alert) == set(schema.ALERT), alert["key"]
    assert set(st.state["summary"]) == set(schema.SUMMARY) - {"error"}
    assert set(st.state) == set(schema.STATE) and set(st.state["checkpoint"]) == set(schema.CHECKPOINT)


def test_negative_control_a_field_the_schema_does_not_name_fails_the_save(monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path) -> None:
    """A producer that starts emitting a new field cannot get it into the file unchecked."""
    real = delivery_stage._record
    monkeypatch.setattr(delivery_stage, "_record", lambda ctx, stage, **kw: {**real(ctx, stage, **kw), "new_field": 1})
    st = setup_tick(monkeypatch, tmp_path, ENTRIES[:1])
    st.gh.update({sweep_path(PIDEV): [open_pull(7)], **pr_paths(PIDEV, 7)})
    st.gql_pages += [linear_page([tick_issue("RA-1", ((PIDEV, 7),))])]
    out = run(st)
    assert out["persisted"] is False and not Path(st.path).exists()
    tile = dr.status_snapshot(st.path, NOW)
    assert tile["complete"] is False and "state_write_failed" in tile["errors"]


def test_the_summary_and_the_tile_counters_come_from_the_schema() -> None:
    fresh = gather.new_summary(NOW)
    assert set(fresh) == set(schema.SUMMARY) - schema.OPTIONAL and schema.shape(schema.SUMMARY, schema.OPTIONAL)(fresh)
    assert status.COUNTERS is schema.TILE_COUNTERS and set(status.COUNTERS) < set(schema.SUMMARY)
    assert {"missions", "not_refreshed", "incomplete", "vercel_unreadable"} <= set(status.COUNTERS)


def test_the_test_helper_plants_what_the_producers_really_write(monkeypatch: pytest.MonkeyPatch,
                                                              tmp_path: Path) -> None:
    """``stored`` (the planted-entry helper every tick test uses) fills the full typed record: same keys
    as a real tick's output, so a planted state is a state the store could have written."""
    st = _real_tick(monkeypatch, tmp_path)
    by_kind = {record["kind"]: record for record in st.state["missions"].values()}
    for kind, real in by_kind.items():
        assert set(stored({"id": "X", "kind": kind})) == set(real), kind
    assert set(stored({"key": "K", "mission_id": "X"}, alert=True)) == set(next(iter(st.state["alerts"].values())))
