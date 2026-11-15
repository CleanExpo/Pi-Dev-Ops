"""RA-8100 B5g: a Linear read that was not whole holds its project's unseen missions; one pull is one
pull whatever the letter case of its link; the UNOWNED_24H source time has one guarded owner."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, NOW, PIDEV, linear_page, mission, open_facts, open_pull, pr_paths, reg_entry, run, setup_tick,
    sweep_path, tick_issue,
)

from app.server import delivery_collect as collect
from app.server import delivery_reconcile as dr
from app.server import delivery_stage

LATER = NOW + timedelta(minutes=10)
LOWER = PIDEV.lower()


def _state(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))


def _shown(st: SimpleNamespace, now) -> set[tuple]:  # type: ignore[no-untyped-def]
    return {(i["ref"], i["code"]) for i in dr.status_snapshot(st.path, now)["items"]}


def _two_projects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    """RA-1 (pi-dev-ops, FALSE_DONE) and RA-2 (ato) are stored by a whole tick 1."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)])
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(ATO, 5)})
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    st.gh[sweep_path(ATO)] = [open_pull(5)]
    st.gql_pages += [linear_page([tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=0.5)]),
                     linear_page([tick_issue("RA-2", ((ATO, 5),))])]
    run(st)
    assert ("RA-1", "FALSE_DONE") in _shown(st, NOW)
    return st


@pytest.mark.parametrize("how", ["linear_fails", "partial_page_then_fails"])
def test_a_linear_read_not_whole_holds_the_unseen_missions_of_that_project(monkeypatch: pytest.MonkeyPatch,
                                                                         tmp_path: Path, how: str) -> None:
    st = _two_projects(monkeypatch, tmp_path)
    stored = _state(st)["missions"]["RA-1"]
    first = [RuntimeError("down")] if how == "linear_fails" else [linear_page([], next_cursor="c1"),
                                                                  RuntimeError("down")]
    st.gql_pages += [*first, linear_page([tick_issue("RA-2", ((ATO, 5),))])]
    out = run(st, LATER)
    state, tile = _state(st), dr.status_snapshot(st.path, LATER)
    assert out["complete"] is False
    assert "RA-1" in out["not_refreshed_ids"] and "RA-2" not in out["not_refreshed_ids"]
    assert state["missions"]["RA-1"] == stored  # never read, so its record is exactly as it was
    assert ("RA-1", "FALSE_DONE") in _shown(st, LATER)
    assert tile["counts"]["not_refreshed"] >= 1


def test_control_a_mission_of_a_project_read_whole_is_not_held(monkeypatch: pytest.MonkeyPatch,
                                                               tmp_path: Path) -> None:
    """RA-2's project was read whole and RA-2 was not in it: it is simply not seen, never held."""
    st = _two_projects(monkeypatch, tmp_path)
    st.gql_pages += [RuntimeError("down"), linear_page([])]
    out = run(st, LATER)
    assert "RA-1" in out["not_refreshed_ids"] and "RA-2" not in out["not_refreshed_ids"]


def test_the_same_pull_linked_in_two_letter_cases_is_one_pull(monkeypatch: pytest.MonkeyPatch,
                                                             tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update({**pr_paths(PIDEV, 7), **pr_paths(LOWER, 7)})
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    node = tick_issue("RA-1", ((PIDEV, 7),), state="completed", completed=0.5)
    st.gql_pages.append(linear_page([node]))
    run(st)
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((PIDEV, 7), (LOWER, 7)), state="completed",
                                                completed=0.5)]))
    out = run(st, LATER)
    rec = _state(st)["missions"]["RA-1"]
    assert rec["reason"] != "multiple_prs" and rec["stage"] == "done"
    assert [p["repo"] for p in rec["prs"]] == [PIDEV]  # the first spelling is kept
    assert ("RA-1", "FALSE_DONE") in _shown(st, LATER) and out["refs_outside_scope"] == 0


def test_in_scope_collapses_links_on_lower_case_repo_and_number() -> None:
    refs = [(PIDEV, 7), (LOWER, 7), ("Other/Repo", 1), (PIDEV, 8), ("CLEANEXPO/PI-DEV-OPS", 7)]
    assert collect.in_scope(refs, ALLOWED) == ([(PIDEV, 7), (PIDEV, 8)], 1)


@pytest.mark.parametrize("started", ["2099-01-01T00:00:00Z", None])
def test_unowned_24h_uses_the_guarded_source_time(started: str | None) -> None:
    """A future startedAt is an invalid clock, not a source: the pull's created time is used instead."""
    issue = mission("RA-2", owner=None)
    issue["startedAt"] = started
    record, found = delivery_stage.classify(issue, [open_facts(7, created=80)], {}, NOW, repo=PIDEV,
                                            project_id="p")
    codes = {f["code"]: f for f in found}
    assert "UNOWNED_24H" in codes, (record, sorted(codes))
    assert codes["UNOWNED_24H"]["age_source"] == "pr_created_at"


def test_unowned_24h_tick_with_a_future_started_at(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    st.gh.update(pr_paths(PIDEV, 7, created=80))
    st.gh[sweep_path(PIDEV)] = [open_pull(7)]
    node = tick_issue("RA-2", ((PIDEV, 7),), owner=None)
    node["startedAt"] = "2099-01-01T00:00:00Z"
    st.gql_pages.append(linear_page([node]))
    run(st)
    assert "UNOWNED_24H" in {a["code"] for a in _state(st)["alerts"].values()}
