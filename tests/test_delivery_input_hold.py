"""RA-8100 B5g round 2: the hold fails closed.

Gap A: a mission the classifier refused for bad INPUT (its own issue fields bad or self-contradictory) is
held; only a named verdict from valid, whole reads counts as whole. Gap B: a stored mission whose own
project was not read WHOLE this tick, for any reason (unqueryable, removed from the registry), is held
with its record byte-identical; a project read whole that no longer lists the mission retires it.
"""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, NOW, PIDEV, linear_page, open_pull, pr_paths, reg_entry, run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_reconcile as dr

LATER = NOW + timedelta(minutes=10)


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _shown(st: SimpleNamespace, now) -> set[tuple]:  # type: ignore[no-untyped-def]
    return {(i["ref"], i["code"]) for i in dr.status_snapshot(st.path, now)["items"]}


def _world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: list[dict]) -> SimpleNamespace:
    """Tick 1 stores RA-1 (project pi-dev-ops) with a critical FALSE_DONE."""
    st = setup_tick(monkeypatch, tmp_path, entries)
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(ATO, 5)})
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gh[sweep_path(ATO)] = []
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=0.5)]))
    st.gql_pages += [linear_page([]) for e in entries[1:] if "linear_project_id" in e]
    run(st)
    assert ("RA-1", "FALSE_DONE") in _shown(st, NOW)  # positive control: the alert exists
    return st


# (state type, field, bad value): every way the issue's own time fields can be bad or self-contradictory.
BAD_ISSUE = [("completed", "completedAt", None), ("completed", "completedAt", "yesterday"),
             ("completed", "completedAt", "2026-11-14T01:00:00"), ("completed", "completedAt", 5),
             ("completed", "startedAt", "yesterday"), ("completed", "startedAt", "2026-11-14T01:00:00"),
             ("completed", "startedAt", 5), ("started", "startedAt", "yesterday"),
             ("started", "startedAt", "2026-11-14T01:00:00"), ("started", "startedAt", 5),
             ("started", "completedAt", "yesterday"), ("started", "completedAt", "2026-11-14T01:00:00"),
             ("started", "completedAt", 5)]


@pytest.mark.parametrize("state,field,value", BAD_ISSUE, ids=[f"{s}-{f}-{v!r}" for s, f, v in BAD_ISSUE])
def test_a_mission_refused_for_bad_input_is_held(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, state: str,
                                                 field: str, value: object) -> None:
    st = _world(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    node = tick_issue("RA-1", ((PIDEV, 7),), state=state, completed=0.5 if state == "completed" else None)
    node[field] = value
    st.gql_pages.append(linear_page([node]))
    out = run(st, LATER)
    state_, rec = _state(st), _state(st)["missions"]["RA-1"]
    assert rec["stage"] in ("unknown", "missing_commit")  # the classifier refused it
    assert "RA-1" in out["not_refreshed_ids"]
    assert any(a["code"] == "FALSE_DONE" for a in state_["alerts"].values())
    assert ("RA-1", "FALSE_DONE") in _shown(st, LATER)


def test_control_a_valid_state_the_classifier_does_not_place_is_whole(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7),), state="unstarted", started=None)]))
    out = run(st, LATER)
    assert _state(st)["missions"]["RA-1"]["reason"] == "bad_issue_state"
    assert "RA-1" not in out["not_refreshed_ids"] and out["complete"] is True


def _registry(tmp_path: Path, entries: list[dict]) -> None:
    (tmp_path / "projects.json").write_text(json.dumps({"projects": entries}), encoding="utf-8")


@pytest.mark.parametrize("how", ["unqueryable", "removed_from_registry"])
def test_a_mission_whose_project_was_not_read_is_held(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                      how: str) -> None:
    st = _world(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)])
    stored = _state(st)["missions"]["RA-1"]
    pidev = [reg_entry("pi-dev-ops", PIDEV, queryable=False)] if how == "unqueryable" else []
    _registry(tmp_path, [*pidev, reg_entry("ato", ATO)])
    st.gql_pages.append(linear_page([]))  # the ato project, read whole and empty
    out = run(st, LATER)
    state = _state(st)
    assert "RA-1" in out["not_refreshed_ids"]
    assert state["missions"]["RA-1"] == stored  # never read: byte-identical
    assert any(a["code"] == "FALSE_DONE" for a in state["alerts"].values())
    assert ("RA-1", "FALSE_DONE") in _shown(st, LATER)


def test_control_a_project_read_whole_without_the_mission_retires_it(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    st = _world(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh[sweep_path(PIDEV)] = []
    st.gql_pages.append(linear_page([]))
    out = run(st, LATER)
    assert out["complete"] is True and out["not_refreshed_ids"] == []
    assert "RA-1" not in _state(st)["missions"] and ("RA-1", "FALSE_DONE") not in _shown(st, LATER)
