"""RA-8100 D55: the writer keeps every rule it is now held to, on its failure paths too.

``save`` refuses a state that breaks a row of ``delivery_invariants.STATE``. If a real tick could build
such a state, nothing would ever be saved again. So every way a tick can end is driven here through the
public entry, on top of a state an earlier real tick stored (so held records and alerts are present):
each must be saved, and the saved file must load. The tile's own rule (a state written after the time of
reading) is tested here as well.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, NOW, PIDEV, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile_gather as gather
from app.server import delivery_reconcile_schema as schema
from app.server import delivery_reconcile_status as status
from app.server import delivery_reconcile_store as store
from app.server import delivery_reconcile_tick as tick

LATER = NOW + timedelta(minutes=15)


def _pages(st: SimpleNamespace) -> None:
    st.gql_pages[:] = [linear_page([tick_issue("RA-1", ((PIDEV, 7),))]), linear_page([])]


def _first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """One real, complete tick at ``NOW``: a mission with an open pull, an orphan pull, two repos."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)])
    st.gh.update({sweep_path(PIDEV): [open_pull(7), open_pull(9)], sweep_path(ATO): [], **pr_paths(PIDEV, 7)})
    _pages(st)
    out = run(st)
    assert out["persisted"] is True and out["complete"] is True, out
    _pages(st)
    return st


def _no_key(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    mp.setattr(tick, "_api_key", lambda: "")


def _no_registry(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    def boom(path: str | None = None) -> None:
        raise collect.RegistryError("registry_malformed")

    mp.setattr(collect, "load_registry", boom)


def _gather_dies_half_way(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    def half(state: dict, registry: object, key: str, now: datetime, summary: dict, proof: dict) -> None:
        summary["not_refreshed"] += 2  # counted, cut and held, then the gather dies before it tallies
        summary["incomplete"]["RA-1"] = "links_incomplete"
        summary["not_refreshed_ids"].append("RA-1")
        raise KeyError("boom")

    mp.setattr(gather, "gather", half)


def _merge_refuses(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    real = gather.gather

    def bad(state: dict, registry: object, key: str, now: datetime, summary: dict, proof: dict) -> tuple:
        records, findings = real(state, registry, key, now, summary, proof)
        return [*records, {"no": "id"}], findings  # the store raises ``record_missing_id``

    mp.setattr(gather, "gather", bad)


def _linear_down(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    st.gql_pages[:] = [RuntimeError("down"), linear_page([])]


def _sweep_down(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    st.gh[sweep_path(PIDEV)] = RuntimeError("down")


def _pull_down(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    st.gh[f"/repos/{PIDEV}/pulls/7"] = RuntimeError("down")


def _links_cut(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    st.gql_pages[:] = [linear_page([tick_issue("RA-1", ((PIDEV, 7),), links_whole=False)]), linear_page([])]


def _budget_spent(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    mp.setitem(collect.BUDGETS, "github", 3)


def _nothing(mp: pytest.MonkeyPatch, st: SimpleNamespace) -> None:
    return None


# how the second tick ends -> (what goes wrong, the error its summary carries, complete)
ENDINGS: dict[str, tuple[Callable, str | None, bool]] = {
    "good": (_nothing, None, True),
    "no_linear_key": (_no_key, "no_linear_key", False),
    "registry_unreadable": (_no_registry, "registry_unreadable", False),
    "gather_dies_half_way": (_gather_dies_half_way, "gather_failed_KeyError", False),
    "merge_refuses": (_merge_refuses, "merge_failed_record_missing_id", False),
    "linear_down": (_linear_down, None, False),
    "sweep_down": (_sweep_down, None, False),
    "pull_down": (_pull_down, None, True),
    "links_cut": (_links_cut, None, False),
    "budget_spent": (_budget_spent, None, True),  # the scope is still known; the cut mission is held
}


@pytest.mark.parametrize("when", ["later", "same_instant", "clock_went_back"])
@pytest.mark.parametrize("ending", sorted(ENDINGS))
def test_every_way_a_tick_ends_is_saved_and_loads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ending: str,
                                                  when: str) -> None:
    st = _first(monkeypatch, tmp_path)
    before = json.loads(Path(st.path).read_text(encoding="utf-8"))
    breaks, error, complete = ENDINGS[ending]
    breaks(monkeypatch, st)
    now = {"later": LATER, "same_instant": NOW, "clock_went_back": NOW - timedelta(hours=1)}[when]
    out = run(st, now)
    assert out["persisted"] is True, out  # the writer never builds a state its own rules refuse
    assert out.get("error") == error and out["complete"] is complete, out
    state = store.load(st.path)
    assert schema.problems(state) == [] and state["last_tick"] == now.timestamp()
    assert set(before["missions"]) <= set(state["missions"]) or complete  # an incomplete tick removes nothing
    tile = status.build(st.path, now, True, True)
    assert tile["state"] == "ok" and tile["complete"] is complete


def test_the_control_a_broken_rule_does_stop_the_save(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The check above can fail: a tick made to store a contradiction is not saved, and says so."""
    st = _first(monkeypatch, tmp_path)
    before = Path(st.path).read_bytes()
    real = store.apply_tick

    def contradict(*args: object, **kwargs: object) -> tuple:
        state, keys = real(*args, **kwargs)
        state["summary"]["incomplete"] = {"RA-1": "links_incomplete"}  # complete, beside a cut mission
        return state, keys

    monkeypatch.setattr(store, "apply_tick", contradict)
    out = run(st, LATER)
    assert out["persisted"] is False and Path(st.path).read_bytes() == before
    tile = status.build(st.path, LATER, True, False)
    assert tile["complete"] is False and "state_write_failed" in tile["errors"]


def test_a_state_written_after_the_time_of_reading_is_never_shown_as_current(monkeypatch: pytest.MonkeyPatch,
                                                                             tmp_path: Path) -> None:
    st = _first(monkeypatch, tmp_path)
    assert status.build(st.path, NOW, True, True)["complete"] is True  # the control: read at the tick's own time
    tile = status.build(st.path, NOW - timedelta(seconds=1), True, True)
    assert tile["state"] == "stale" and tile["complete"] is False and tile["errors"] == ["state_from_future"]
