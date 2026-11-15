"""RA-8100: ONE rule for "out of scope", checked as a table (third internal pre-screen).

A stored subject is removed as out of scope only when the list that would contain it was read whole this
tick and does not contain it: a mission's list is its project's Linear issue list, an orphan pull's list
is its repo's open-pull sweep. Every other way that list can go unread keeps the stored record and its
alert exactly as they were, and names the subject in ``not_refreshed_ids`` (one writer, ``Run.unread``).
Before, the two kinds had two rules: a mission whose project was not read was held, while an orphan
whose repo was not swept was deleted as "gone".

The rows cross both stored kinds with every way the list can go unread. A read cut by the per-mission
budget is the remaining way; tests/test_delivery_retire_rule.py covers it per subject.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ATO, PIDEV, linear_page, reg_entry, run, setup_tick, stored, sweep_path, tick_issue,
)

from app.server import delivery_reconcile_store as store

SKIPPED = "CleanExpo/CCW-CRM"  # skipped by name before any request; fake data only, nothing is read
BOTH = [reg_entry("ato", ATO), reg_entry("pd", PIDEV)]


def _whole(st: SimpleNamespace) -> None:
    st.gql_pages += [linear_page([]), linear_page([])]


def _project_list_failed(st: SimpleNamespace) -> None:
    st.gql_pages += [linear_page([]), RuntimeError("boom")]


def _sweep_failed(st: SimpleNamespace) -> None:
    _whole(st)
    st.gh[sweep_path(PIDEV)] = RuntimeError("boom")


def _link_list_cut(st: SimpleNamespace) -> None:
    st.gql_pages += [linear_page([]), linear_page([tick_issue("RA-2", links_whole=False)])]


def _one_page(st: SimpleNamespace) -> None:
    st.gql_pages += [linear_page([])]


# name: (registry entries, repo of the stored subjects, world, complete, the subjects are kept)
ROWS = {
    "positive-control-read-whole-and-absent": (BOTH, PIDEV, _whole, True, False),
    "project-list-failed": (BOTH, PIDEV, _project_list_failed, False, True),
    "sweep-failed": (BOTH, PIDEV, _sweep_failed, False, True),
    "another-missions-link-list-cut": (BOTH, PIDEV, _link_list_cut, False, True),
    "entry-has-no-linear-project": ([BOTH[0], reg_entry("pd", PIDEV, queryable=False)], PIDEV, _one_page, True, True),
    "entry-left-the-registry": ([BOTH[0]], PIDEV, _one_page, True, True),
    "repo-is-skipped": ([BOTH[0], reg_entry("pd", SKIPPED)], SKIPPED, _one_page, True, True),
}


@pytest.mark.parametrize("name", sorted(ROWS))
def test_a_stored_subject_goes_only_when_its_own_list_was_read_whole(monkeypatch: pytest.MonkeyPatch,
                                                                    tmp_path: Path, name: str) -> None:
    entries, repo, world, complete, kept = ROWS[name]
    st = setup_tick(monkeypatch, tmp_path, entries)
    orphan = f"pr:{repo}#9"
    planted = store.empty_state()
    planted["missions"] = {
        "RA-1": stored({"id": "RA-1", "kind": "mission", "project_id": "pd", "repo": repo}),
        orphan: stored({"id": orphan, "kind": "orphan_pr", "repo": repo})}
    planted["alerts"] = {key: stored({"key": key, "mission_id": rid, "code": "STALE_24H"}, alert=True)
                         for key, rid in (("k-m", "RA-1"), ("k-o", orphan))}
    assert store.save(st.path, planted)
    st.gh.update({sweep_path(ATO): [], sweep_path(PIDEV): []})
    world(st)
    out = run(st)
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    assert "error" not in out and out["persisted"] is True and out["complete"] is complete, out
    for rid, key in (("RA-1", "k-m"), (orphan, "k-o")):
        if kept:
            assert state["missions"][rid] == planted["missions"][rid], rid  # exactly as stored
            assert state["alerts"][key] == planted["alerts"][key], rid
            # a complete tick names every subject it held; an incomplete one says so itself and removes nothing
            assert rid in out["not_refreshed_ids"] or (complete is False and out["incomplete"]), rid
        else:
            assert rid not in state["missions"] and key not in state["alerts"], rid
    assert not [call for call in st.github if SKIPPED.lower() in str(call).lower()]  # the skipped repo is never asked
