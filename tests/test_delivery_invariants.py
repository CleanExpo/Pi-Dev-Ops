"""RA-8100 D55: relationships BETWEEN fields of the state file (``delivery_invariants.STATE``).

Each field of the state file can be valid alone while two of them contradict each other. The two Codex
round 7 findings come first, each through the real entry point. Then every row of ``STATE``: a state a
REAL tick wrote is changed in one place so that every field stays in its own domain; that state must
break exactly its row, ``save`` must refuse it, ``load`` must refuse it and the tile must be unreadable.
With the one row taken out of the table the same state saves, so each test is known to fail without its
rule. A row with no planted contradiction fails the coverage test.
"""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, NOW, PIDEV, SHA_A, SHA_B, compare_answer, install_fakes, linear_page, open_pull, pr_paths,
    reg_entry, run, setup_tick, sweep_path, tick_issue,
)
from _delivery_stored_support import summary_of

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg
from app.server import delivery_invariants as inv
from app.server import delivery_reconcile_schema as schema
from app.server import delivery_reconcile_status as status
from app.server import delivery_reconcile_store as store

TICK = NOW.timestamp()
ORPHAN, REPO = f"pr:{PIDEV}#9", f"repo:{PIDEV}"


def _state(**summary: object) -> dict:
    """A whole state a tick at ``NOW`` could have written; ``summary`` overrides its summary fields."""
    made = summary_of(tick_at=NOW.isoformat(), **summary)
    return {"version": store.SCHEMA_VERSION, "missions": {}, "alerts": {}, "last_tick": TICK, "summary": made,
            "checkpoint": {"last_complete": TICK if made["complete"] else None}}


def _refused_everywhere(tmp_path: Path, state: dict) -> None:
    """Never written by ``save``; and when it is on disk anyway, ``load`` refuses it and the tile is unreadable."""
    path = tmp_path / "refused.json"
    assert store.save(path, state) is False and not path.exists()
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(store.StoreError):
        store.load(path)
    tile = status.build(path, NOW, True, True)
    assert tile["state"] == "unreadable" and tile["complete"] is False and tile["errors"] == ["state_unreadable"]


# Codex round 7, finding 1: ``identical`` for a base and a head that differ was accepted, and the stage
# counts ``identical`` as contained, so a merge could be verified from an answer about another head.
def test_codex7_identical_for_two_different_commits_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def compare(base: str, head: str) -> str:
        st = install_fakes(monkeypatch)
        st.gh[f"/repos/{ATO}/compare/{base}...{head}"] = compare_answer(SHA_A, SHA_A, "identical")
        try:
            return dg.compare_status(ATO, base, head, tick=dc.Tick(allowed=ALLOWED))
        except dc.Unknown as exc:
            return f"refused:{exc.reason}"

    assert compare(SHA_A, SHA_B) == "refused:compare_mismatch"
    assert compare(SHA_A, SHA_A) == "identical"  # the control: one commit asked, and the answer is about it


# Codex round 7, finding 2: ``complete: true`` beside a cut mission loaded, and the tile showed ok, complete.
def test_codex7_complete_beside_an_incomplete_mission_is_refused(tmp_path: Path) -> None:
    _refused_everywhere(tmp_path, _state(complete=True, incomplete={"RA-8100": "links_incomplete"}))


def test_the_control_state_is_accepted(tmp_path: Path) -> None:
    for name, state in (("complete", _state(complete=True)),
                        ("cut", _state(complete=False, incomplete={"RA-8100": "links_incomplete"}))):
        path = tmp_path / f"{name}.json"
        assert store.save(path, state) is True, name
        assert store.load(path) == state
        assert status.build(path, NOW, True, True)["complete"] is state["summary"]["complete"]


@pytest.fixture
def real(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict:
    """The state ONE real, complete tick wrote: a mission with an open pull, an orphan pull, two repos."""
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV), reg_entry("ato", ATO)])
    st.gh.update({sweep_path(PIDEV): [open_pull(7), open_pull(9)], sweep_path(ATO): [], **pr_paths(PIDEV, 7)})
    st.gql_pages += [linear_page([tick_issue("RA-1", ((PIDEV, 7),))]), linear_page([])]
    out = run(st)
    assert out["persisted"] is True and out["complete"] is True, out
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    assert {"RA-1", ORPHAN, REPO} <= set(state["missions"]) and state["alerts"] and schema.problems(state) == []
    assert state["missions"]["RA-1"]["tests_passed"] is True  # the control the review-fields row relies on
    return state


def _alert(state: dict) -> dict:
    return next(a for a in state["alerts"].values() if a["since"] is not None)


def _set(where: Callable[[dict], dict], **fields: object) -> Callable[[dict], None]:
    return lambda state: where(state).update(fields)


def _never_run(state: dict) -> None:
    state.update(last_tick=None, summary=None)  # "no tick has run", with records and alerts still stored


_SUMMARY = lambda s: s["summary"]  # noqa: E731
_MISSION = lambda s: s["missions"]["RA-1"]  # noqa: E731

# row -> the one change that makes a real state contradict itself (every field stays in its own domain)
PLANTED: dict[str, Callable[[dict], None]] = {
    "never_run_is_empty": _never_run,
    "complete_has_no_reason": _set(_SUMMARY, incomplete={"RA-1": "links_incomplete"}),  # Codex round 7
    "complete_is_checkpointed": _set(lambda s: s["checkpoint"], last_complete=TICK - 900),
    "tick_at_is_last_tick": _set(_SUMMARY, tick_at="2026-11-14T12:00:00+00:00"),
    "held_ids_cover_the_count": _set(_SUMMARY, not_refreshed=3),
    "tallies_agree": _set(_SUMMARY, by_code={}),
    "seen_in_order": _set(_MISSION, first_seen=TICK + 5),
    "alert_counted_once_is_new": lambda s: _alert(s).update(first_seen=TICK - 5),
    "record_names_itself": _set(_MISSION, ref="RA-2"),
    "refused_has_a_reason": _set(_MISSION, reason="http_500"),
    "merge_fields_agree": _set(_MISSION, merge_sha=SHA_B),
    "review_fields_need_an_open_pull": _set(_MISSION, pr_head_sha=None),
    "since_has_its_source": lambda s: _alert(s).update(age_source=None),
    "repo_live_fields_agree": _set(lambda s: s["missions"][REPO], live_unconfirmed=SHA_A),
}
MORE: list[tuple[str, Callable[[dict], None]]] = [  # other faces of the same rows
    ("never_run_is_empty", lambda s: (s.update(last_tick=None, summary=None, missions={}, alerts={}))),  # checkpoint left
    ("complete_has_no_reason", _set(_SUMMARY, complete=False)),  # incomplete, and no reason given
    ("complete_has_no_reason", _set(_SUMMARY, error="gather_failed_KeyError")),  # complete beside an error
    ("complete_is_checkpointed", _set(lambda s: s["checkpoint"], last_complete=None)),
    ("held_ids_cover_the_count", _set(_SUMMARY, not_refreshed_ids=["RA-1", "RA-1"])),
    ("tallies_agree", lambda s: s["summary"].update(  # the top list against the founder and critical count
        founder_or_critical=[] if s["summary"]["founder_or_critical"] else ["RA-1"])),
    ("seen_in_order", _set(_MISSION, refreshed_at=TICK + 5)),
    ("record_names_itself", _set(lambda s: s["missions"][ORPHAN], ref=f"{PIDEV}#8")),
    ("record_names_itself", _set(lambda s: s["missions"][REPO], ref=ATO)),
    ("refused_has_a_reason", _set(_MISSION, stage="unknown")),
    ("merge_fields_agree", _set(_MISSION, verified_sha=SHA_B, deployed_sha=SHA_B)),
    ("merge_fields_agree", _set(_MISSION, deployed_sha=SHA_B)),
    ("review_fields_need_an_open_pull", _set(lambda s: s["missions"][ORPHAN], approval_identity_unverified=True,
                                             pr_head_sha=None)),
    ("since_has_its_source", _set(_MISSION, since=None)),
    ("repo_live_fields_agree", _set(lambda s: s["missions"][REPO], live_source="provable", merged_unverifiable=2)),
]


def _planted(real: dict, change: Callable[[dict], None]) -> dict:
    state = copy.deepcopy(real)
    change(state)
    return state


def test_every_row_has_a_planted_contradiction() -> None:
    names = [name for name, _rule, _holds in inv.STATE]
    assert set(PLANTED) == set(names) and len(set(names)) == len(names)
    assert all(rule for _name, rule, _holds in inv.STATE) and [limit[0] for limit in inv.LIMITS] == list("abcdefghij")


@pytest.mark.parametrize("row", sorted(PLANTED))
def test_a_contradictory_state_breaks_its_row_and_is_refused_everywhere(real: dict, tmp_path: Path, row: str) -> None:
    state = _planted(real, PLANTED[row])
    assert schema.problems(state) == [f"invariant:{row}"]  # every field in its domain; this rule and no other
    _refused_everywhere(tmp_path, state)


@pytest.mark.parametrize("row", sorted(PLANTED))
def test_without_its_row_the_contradiction_is_saved(monkeypatch: pytest.MonkeyPatch, real: dict, tmp_path: Path,
                                                   row: str) -> None:
    """The mutation: this row taken out of the table. The planted state then saves and loads, so the test
    above is known to fail when the rule is missing."""
    state = _planted(real, PLANTED[row])
    monkeypatch.setattr(inv, "STATE", tuple(r for r in inv.STATE if r[0] != row))
    assert store.save(tmp_path / "s.json", state) is True and store.load(tmp_path / "s.json") == state


@pytest.mark.parametrize("row,change", MORE, ids=[f"{m[0]}-{i}" for i, m in enumerate(MORE)])
def test_other_faces_of_a_row_are_refused(real: dict, tmp_path: Path, row: str, change: Callable) -> None:
    state = _planted(real, change)
    assert f"invariant:{row}" in schema.problems(state)
    _refused_everywhere(tmp_path, state)


def test_a_field_outside_its_domain_is_reported_as_the_field_not_as_a_rule(real: dict) -> None:
    state = _planted(real, _set(_SUMMARY, complete="yes"))
    assert schema.problems(state) == ["summary"]  # the rows run only on a state whose fields are all in domain


@pytest.mark.parametrize("field,value", [("stage", "counted"), ("stage", "deploying"), ("authorised_head_sha", SHA_A),
                                         ("acceptance_passed", True)])
def test_a_value_the_reconcile_never_writes_is_refused(real: dict, tmp_path: Path, field: str, value: object) -> None:
    state = _planted(real, _set(_MISSION, **{field: value}))
    assert schema.problems(state) == ["missions[0]"] and list(state["missions"])[0] == "RA-1"
    _refused_everywhere(tmp_path, state)
    alert = _planted(real, lambda s: _alert(s).update(severity="warning"))  # not one of the five severities
    assert [p.split("[")[0] for p in schema.problems(alert)] == ["alerts"]
