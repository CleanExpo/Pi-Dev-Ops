"""AAA check 11: nothing documented broken.

The rules that stop the grade flattering itself: a CONFLICTING or
STRUCTURAL_ONLY row fails, a missing row fails, an open mc-defect ticket fails
the surfaces it names (all of them if it names none), and Linear not being
read is "not measured", never a pass.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import mission_control_register as mr
from scripts import mission_control_scorecard as sc

ROW = "| {sid} | Page | Journey | — | {state} | evidence | EXTEND |"


def _register(states: dict[str, str]) -> str:
    head = "| ID | Surface | User journey | Write action | Evidence state | Evidence | Treatment |\n|---|---|---|---|---|---|---|\n"
    return head + "\n".join(ROW.format(sid=s, state=v) for s, v in states.items())


ALL_PARTIAL = {s: "PARTIAL — live check owed" for s in mr.SURFACES}


def _fetch(nodes: list[dict]):
    return lambda q, v: {"data": {"issues": {"nodes": nodes}}}


def _by_surface(tmp_path: Path, register: str, fetch) -> dict[str, dict[str, dict]]:
    written = mr.write_receipts(tmp_path, register, fetch)
    return {s: {c["check"]: c for c in checks} for s, checks in written.items()}


def test_the_real_register_parses_every_surface() -> None:
    states = mr.register_states(mr.REGISTER.read_text(encoding="utf-8"))
    assert sorted(states) == mr.SURFACES
    assert "UNKNOWN" not in states.values()


def test_a_clean_register_and_no_tickets_pass(tmp_path: Path) -> None:
    got = _by_surface(tmp_path, _register(ALL_PARTIAL), _fetch([]))
    assert all(c["11-register"]["result"] == "PASS" and c["11-tickets"]["result"] == "PASS" for c in got.values())


def test_conflicting_and_structural_only_rows_fail(tmp_path: Path) -> None:
    reg = _register({**ALL_PARTIAL, "MC-13": "STRUCTURAL_ONLY", "MC-18": "CONFLICTING"})
    got = _by_surface(tmp_path, reg, _fetch([]))
    assert got["MC-13"]["11-register"]["result"] == "FAIL"
    assert got["MC-18"]["11-register"]["result"] == "FAIL"
    assert got["MC-04"]["11-register"]["result"] == "PASS"


def test_a_surface_missing_from_the_register_fails(tmp_path: Path) -> None:
    reg = _register({s: v for s, v in ALL_PARTIAL.items() if s != "MC-09"})
    assert _by_surface(tmp_path, reg, _fetch([]))["MC-09"]["11-register"]["result"] == "FAIL"


def test_an_open_ticket_fails_only_the_surfaces_it_names(tmp_path: Path) -> None:
    nodes = [{"identifier": "RA-1", "title": "Fleet wall 503", "description": "MC-17 and MC-01 read no source"}]
    got = _by_surface(tmp_path, _register(ALL_PARTIAL), _fetch(nodes))
    assert got["MC-17"]["11-tickets"]["result"] == "FAIL"
    assert "RA-1" in got["MC-01"]["11-tickets"]["detail"]
    assert got["MC-04"]["11-tickets"]["result"] == "PASS"


def test_a_ticket_naming_no_surface_counts_against_every_surface(tmp_path: Path) -> None:
    nodes = [{"identifier": "RA-2", "title": "Dashboard theme wrong", "description": None}]
    got = _by_surface(tmp_path, _register(ALL_PARTIAL), _fetch(nodes))
    assert all(c["11-tickets"]["result"] == "FAIL" for c in got.values())


def test_linear_unread_is_unknown_not_pass(tmp_path: Path) -> None:
    def broken(q, v):
        raise OSError("no route")
    for fetch in (None, broken):
        got = _by_surface(tmp_path, _register(ALL_PARTIAL), fetch)
        assert all(c["11-tickets"]["result"] == "UNKNOWN" for c in got.values())


def test_the_query_asks_only_for_open_labelled_issues() -> None:
    seen: dict = {}

    def spy(q, v):
        seen.update(q=q, v=v)
        return {"data": {"issues": {"nodes": []}}}
    mr.open_defects(spy)
    assert seen["v"] == {"label": "mc-defect"}
    assert '"completed", "canceled"' in seen["q"] and "nin" in seen["q"]


def _score(tmp_path: Path, checks: list[dict]) -> dict:
    (tmp_path / "MC-04-C11.json").write_text(json.dumps({"checks": checks}), encoding="utf-8")
    return sc.score_surface("MC-04", sc.load_receipts(tmp_path))["checks"]["11"]


def test_scorer_meets_check_eleven_only_on_two_passes(tmp_path: Path) -> None:
    ok = [{"check": "11-register", "result": "PASS"}, {"check": "11-tickets", "result": "PASS"}]
    assert _score(tmp_path, ok)["met"] is True
    assert _score(tmp_path, ok[:1])["reason"].startswith("not measured")


def test_scorer_reports_unknown_as_not_measured_but_a_fail_as_measured(tmp_path: Path) -> None:
    unknown = [{"check": "11-register", "result": "PASS"},
               {"check": "11-tickets", "result": "UNKNOWN", "detail": "LINEAR_API_KEY not set"}]
    v = _score(tmp_path, unknown)
    assert v["met"] is False and v["reason"] == "not measured: LINEAR_API_KEY not set"
    failed = [{"check": "11-register", "result": "FAIL", "detail": "register row is CONFLICTING"},
              {"check": "11-tickets", "result": "UNKNOWN", "detail": "x"}]
    assert _score(tmp_path, failed)["reason"].startswith("11-register FAIL")


def test_scorer_without_a_register_receipt_is_not_measured(tmp_path: Path) -> None:
    row = sc.score_surface("MC-04", sc.load_receipts(tmp_path))
    assert row["checks"]["11"]["reason"].startswith("not measured")
