"""RA-8100 D61 (review round 9): one Linear issue listed twice is a cut list, whichever of its two names repeats.

A Linear node has two names, ``id`` and ``identifier``. A mission list in which either name appears twice (on
one page or across pages) may have skipped an issue, so it is not whole: the tick is incomplete and names the
project. A list where every node has its own id and its own identifier is the control.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from _delivery_reconcile_support import ATO, NOW, linear_page, reg_entry, run, setup_tick, sweep_path, tick_issue

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_status as status


def _node(identifier: str, node_id: str) -> dict:
    return {**tick_issue(identifier), "id": node_id}


def _tick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pages: list[list[dict]]) -> tuple[dict, dict]:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", ATO)])
    for index, nodes in enumerate(pages):
        st.gql_pages.append(linear_page(nodes, None if index == len(pages) - 1 else f"cursor-{index}"))
    st.gh[sweep_path(ATO)] = []
    out = run(st)
    return out, status.build(st.path, NOW, True, dr._last_save_ok)


CASES = [
    pytest.param([[_node("RA-1", "id-1"), _node("RA-2", "id-1")]], id="one id, two identifiers, one page"),
    pytest.param([[_node("RA-1", "id-1")], [_node("RA-2", "id-1")]], id="one id, two identifiers, two pages"),
    pytest.param([[_node("RA-1", "id-1"), _node("RA-1", "id-2")]], id="one identifier, two ids, one page"),
    pytest.param([[_node("RA-1", "id-1")], [_node("RA-1", "id-2")]], id="one identifier, two ids, two pages"),
]


@pytest.mark.parametrize("pages", CASES)
def test_an_issue_listed_twice_makes_the_tick_incomplete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                         pages: list[list[dict]]) -> None:
    out, tile = _tick(monkeypatch, tmp_path, pages)
    assert out["complete"] is False and out["incomplete"] == {"ato": "duplicate_issue"}
    assert tile["complete"] is False


def test_control_two_different_issues_are_a_whole_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out, tile = _tick(monkeypatch, tmp_path, [[_node("RA-1", "id-1")], [_node("RA-2", "id-2")]])
    assert out["complete"] is True and out["incomplete"] == {} and out["missions"] == 2
    assert tile["complete"] is True


# ---- the same rule across the lists of one tick (internal screen of e9bc9cf9) ----

OTHER = "CleanExpo/Pi-Dev-Ops"


def _two_lists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, first: list[dict], second: list[dict], *,
               one_project: bool = False) -> tuple[dict, dict]:
    b = reg_entry("b", OTHER)
    if one_project:
        b["linear_project_id"] = "proj-a"
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("a", ATO), b])
    st.gql_pages += [linear_page(first), linear_page(second)]
    st.gh[sweep_path(ATO)] = []
    st.gh[sweep_path(OTHER)] = []
    out = run(st)
    return out, status.build(st.path, NOW, True, dr._last_save_ok)


@pytest.mark.parametrize("second", [
    pytest.param(_node("SYN-2", "id-1"), id="same id under another identifier"),
    pytest.param(_node("RA-1", "id-9"), id="same identifier under another id"),
    pytest.param(_node("RA-1", "id-1"), id="the same issue in a second project"),
])
def test_an_issue_in_the_lists_of_two_projects_cuts_the_second(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                               second: dict) -> None:
    out, tile = _two_lists(monkeypatch, tmp_path, [_node("RA-1", "id-1")], [second])
    assert out["complete"] is False and out["incomplete"] == {"b": "duplicate_issue"}
    assert tile["complete"] is False and out["missions"] == 1


def test_control_two_registry_entries_on_one_project_share_its_issues(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    out, tile = _two_lists(monkeypatch, tmp_path, [_node("RA-1", "id-1")], [_node("RA-1", "id-1")], one_project=True)
    assert out["complete"] is True and out["incomplete"] == {} and out["missions"] == 1 and tile["complete"] is True


def test_one_project_read_twice_with_an_issue_renamed_between_is_cut(monkeypatch: pytest.MonkeyPatch,
                                                                     tmp_path: Path) -> None:
    out, _ = _two_lists(monkeypatch, tmp_path, [_node("RA-1", "id-1")], [_node("RA-7", "id-1")], one_project=True)
    assert out["complete"] is False and out["incomplete"] == {"b": "duplicate_issue"} and out["missions"] == 1


def test_a_duplicate_two_pages_apart_is_still_a_duplicate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    out, _ = _tick(monkeypatch, tmp_path, [[_node("RA-1", "id-1")], [_node("RA-2", "id-2")], [_node("RA-3", "id-1")]])
    assert out["complete"] is False and out["incomplete"] == {"ato": "duplicate_issue"}


def test_control_an_id_spelled_like_another_issues_identifier_is_not_a_duplicate(monkeypatch: pytest.MonkeyPatch,
                                                                                 tmp_path: Path) -> None:
    out, _ = _tick(monkeypatch, tmp_path, [[_node("RA-1", "RA-2"), _node("RA-2", "RA-1")]])
    assert out["complete"] is True and out["missions"] == 2
