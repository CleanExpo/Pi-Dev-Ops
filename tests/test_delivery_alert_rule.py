"""RA-8100 B6 part 2: one written rule for removing a stored alert, one owner (the store).

A stored alert is removed only on a tick that is ``complete``, and only when its own subject was read
whole on that tick and no longer raises it, or its subject left scope on that complete tick. On a tick
that is not complete, no stored alert is removed, whatever was read. The rule is an ALLOW-list: a subject
the tick neither read whole nor held nor saw leave scope keeps its alerts (the forgotten-hold case). The status tile must show every
alert the store kept, checked here through apply_tick -> save -> status_snapshot.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from _delivery_reconcile_support import NOW

from app.server import delivery_reconcile as dr
from app.server import delivery_reconcile_store as store

T1, T2 = NOW.timestamp() - 600, NOW.timestamp()


def _alert(mid: str) -> dict:
    return {"key": f"K-{mid}", "mission_id": mid, "code": "FALSE_DONE", "severity": "critical", "ref": f"RA-{mid}",
            "next_owner": "founder", "message": "m", "since": None, "age_source": None, "url": None}


def _first() -> dict:
    """Mission M stored with a stored critical alert; GHOST is an alert whose subject is no stored mission."""
    state, _ = store.apply_tick(store.empty_state(), [{"id": "M", "stage": "done"}], [_alert("M")], T1, True,
                                whole=["M"], scope=["M"])
    state["alerts"]["K-GHOST"] = {**_alert("GHOST"), "first_seen": T1, "last_seen": T1, "count": 1}
    return state


# subject -> (records emitted on tick 2, ``whole``, ``scope``, the alert key it decides, removed on complete)
SCOPE = ["M", "GHOST"]
SUBJECTS = {
    "read_whole": ([{"id": "M", "stage": "done"}], ["M"], SCOPE, "K-M", True),
    "emitted_not_whole": ([{"id": "M", "stage": "unknown"}], [], SCOPE, "K-M", False),
    "forgotten_with_record": ([], [], SCOPE, "K-M", False),
    "not_seen": ([{"id": "M", "stage": "done"}], ["M"], SCOPE, "K-GHOST", False),
    "left_scope": ([], [], ["GHOST"], "K-M", True),
    "scope_unknown": ([], [], None, "K-M", False),
}


def _tick(tmp_path: Path, subject: str, complete: bool) -> tuple[dict, set]:
    records, whole, scope, *_ = SUBJECTS[subject]
    out, _ = store.apply_tick(_first(), records, [], T2, complete, whole=whole, scope=scope)
    out["summary"] = {"complete": complete, "not_refreshed_ids": []}
    path = tmp_path / "state.json"
    assert store.save(path, out)
    return out, {i["ref"] for i in dr.status_snapshot(path, NOW)["items"]}


@pytest.mark.parametrize("complete", [True, False], ids=["complete", "incomplete"])
@pytest.mark.parametrize("subject", sorted(SUBJECTS))
def test_the_one_rule_over_every_subject(tmp_path: Path, subject: str, complete: bool) -> None:
    out, shown = _tick(tmp_path, subject, complete)
    key, removed = SUBJECTS[subject][3], SUBJECTS[subject][4] and complete  # only a proven reason removes
    assert (key not in out["alerts"]) is removed
    assert ({a["ref"] for a in out["alerts"].values()} == shown)  # the tile shows exactly what is stored


def test_forgotten_hold_with_a_stored_record_keeps_record_and_alert() -> None:
    """Neither emitted nor in ``whole``, still in ``scope``: no absence-based removal."""
    out, _ = store.apply_tick(_first(), [], [], T2, True, whole=[], scope=SCOPE)
    assert "M" in out["missions"] and "K-M" in out["alerts"]


def test_emitted_but_not_in_whole_keeps_its_alerts() -> None:
    out, _ = store.apply_tick(_first(), [{"id": "M", "stage": "unknown"}], [], T2, True, whole=[], scope=SCOPE)
    assert "K-M" in out["alerts"]


def test_absent_from_a_known_scope_on_a_complete_tick_loses_record_and_alerts() -> None:
    out, _ = store.apply_tick(_first(), [], [], T2, True, whole=[], scope=["GHOST"])
    assert "M" not in out["missions"] and "K-M" not in out["alerts"]


def test_scope_none_removes_nothing_even_on_a_complete_tick() -> None:
    """``complete`` and an unknown ``scope`` disagree: fail closed, even for a subject proven whole."""
    out, _ = store.apply_tick(_first(), [{"id": "M", "stage": "done"}], [], T2, True, whole=["M"], scope=None)
    assert "M" in out["missions"] and {"K-M", "K-GHOST"} <= set(out["alerts"])


def test_reviewer_case_read_whole_and_not_raised_on_an_incomplete_tick_keeps_the_alert(tmp_path: Path) -> None:
    out, shown = _tick(tmp_path, "read_whole", False)
    assert "K-M" in out["alerts"] and "RA-M" in shown
    out, shown = _tick(tmp_path, "read_whole", True)
    assert "K-M" not in out["alerts"] and "RA-M" not in shown


def test_a_raised_alert_is_never_removed() -> None:
    for complete in (True, False):
        out, _ = store.apply_tick(_first(), [{"id": "M", "stage": "done"}], [_alert("M")], T2, complete)
        assert out["alerts"]["K-M"]["count"] == 2


def test_forgotten_hold_an_alert_whose_subject_was_neither_read_whole_nor_held_nor_out_of_scope_survives(
        tmp_path: Path) -> None:
    out, _ = store.apply_tick(_first(), [{"id": "M", "stage": "done"}], [], T2, True, whole=["M"], scope=SCOPE)
    assert "K-GHOST" in out["alerts"]
    out["summary"] = {"complete": True, "not_refreshed_ids": []}
    path = tmp_path / "state.json"
    assert store.save(path, out)
    assert "RA-GHOST" in {i["ref"] for i in dr.status_snapshot(path, NOW)["items"]}  # the tile never hides it


@pytest.mark.parametrize("records,whole,scope", [([{"id": "M", "stage": "done"}], ["M"], SCOPE), ([], [], []),
                                                ([], ["M", "GHOST"], None), ([{"id": "M"}], ["M"], ["M"])])
def test_an_alert_survives_every_incomplete_tick_whatever_was_read(records: list, whole: list, scope: list) -> None:
    out, _ = store.apply_tick(_first(), records, [], T2, False, whole=whole, scope=scope)
    assert {"K-M", "K-GHOST"} <= set(out["alerts"])


def test_an_alert_is_removed_on_a_complete_tick_when_its_subject_was_read_whole_and_did_not_raise_it() -> None:
    out, _ = store.apply_tick(_first(), [{"id": "M", "stage": "done"}], [], T2, True, whole=["M"], scope=SCOPE)
    assert "K-M" not in out["alerts"]


def test_an_alert_is_removed_when_its_subject_left_scope_on_a_complete_tick() -> None:
    out, _ = store.apply_tick(_first(), [], [], T2, True, whole=[], scope=["GHOST"])
    assert "K-M" not in out["alerts"] and "M" not in out["missions"]


def test_an_alert_with_no_subject_is_never_retired() -> None:
    state = _first()
    state["alerts"]["K-NONE"] = {**_alert("X"), "key": "K-NONE", "mission_id": None, "first_seen": T1,
                                 "last_seen": T1, "count": 1}
    out, _ = store.apply_tick(state, [{"id": "M", "stage": "done"}], [], T2, True, whole=["M"], scope=SCOPE)
    assert "K-NONE" in out["alerts"]
