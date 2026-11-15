"""RA-8100 B5d class guard: the GitHub pager owns "this paged list is whole" for every list.

Every paged list (open pulls, check runs, reviews) must name how an item is identified; the pager
refuses a missing or malformed identity, an identity seen twice on one page or across pages, and,
where the answer carries ``total_count``, any distinct count that is not exactly that total.
Pulls and reviews carry no ``total_count``, so their count rows do not exist (see the B5d report).
"""
from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, REPO_ROOT, SHA_A, SHA_B, ago, install_fakes, linear_page, merged_paths, open_pull, pr_paths,
    reg_entry, run, setup_tick, sweep_path, tick_issue,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg

CHECKS = f"/repos/{ATO}/commits/{SHA_A}/check-runs?per_page=100&page=1"
REVIEWS = f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"


def _run(i: int) -> dict:
    return {"id": i, "status": "completed", "conclusion": "success", "completed_at": ago(72), "head_sha": SHA_A}


def _rev(i: int) -> dict:
    return {"id": i, "user": {"login": f"r{i}", "type": "User"}, "state": "COMMENTED", "commit_id": SHA_A,
            "submitted_at": ago(5)}


# list name -> (page-1 path, item builder, identity field, item code, carries total_count)
LISTS = {
    "pulls": (sweep_path(ATO), open_pull, "number", "pull", False),
    "check_runs": (CHECKS, _run, "id", "check_run", True),
    "reviews": (REVIEWS, _rev, "id", "review", False),
}


def _answer(name: str, items: list[dict], total: object) -> object:
    return {"total_count": total, "check_runs": items} if name == "check_runs" else items


def _serve(st: SimpleNamespace, name: str, pages: list[list[dict]], totals: list[object]) -> None:
    """Serve ``pages`` for one list, page ``n`` carrying ``totals[n-1]`` where the list has a count."""
    path = LISTS[name][0]
    for n, items in enumerate(pages, start=1):
        st.gh[path.removesuffix("page=1") + f"page={n}"] = _answer(name, items, totals[n - 1])


def _read(st: SimpleNamespace, name: str) -> list[dict]:
    tick = dc.Tick(allowed=ALLOWED)
    if name == "pulls":
        return dg.open_prs(ATO, tick=tick)
    return dg.pr_evidence(ATO, 5, tick=tick)[name]


def _base(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    st = install_fakes(monkeypatch)
    st.gh.update(pr_paths(ATO, 5))
    return st


def _strip(item: dict, field: str, value: object) -> dict:
    out = dict(item)
    if value == "missing":
        out.pop(field)
    else:
        out[field] = value
    return out


def _cases(name: str) -> list[tuple[str, list[list[dict]], list[object] | None, str]]:
    """(case id, pages, totals per page, expected reason) for one list."""
    _, make, field, code, counted = LISTS[name]
    full = [make(i) for i in range(1, 101)]
    rows = [
        ("dup_one_page", [[make(1), make(1)]], [2], f"duplicate_{code}"),
        ("dup_two_pages", [full, [make(100)]], [101, 101], f"duplicate_{code}"),
    ]
    for bad in ("missing", None, True, "7", 0, -3):
        rows.append((f"identity_{bad}", [[make(1), _strip(make(2), field, bad)]], [2], f"malformed_{code}"))
    if counted:
        rows += [("total_larger", [[make(1), make(2)]], [3], "list_short"),
                 ("total_smaller", [[make(1), make(2)]], [1], "list_over"),
                 ("total_smaller_two_pages", [full, [make(101)]], [100, 100], "list_over"),
                 ("total_changed", [full, [make(101)]], [101, 102], "total_changed"),
                 ("total_bool", [[make(1)]], [True], "malformed_list"),
                 ("total_negative", [[]], [-1], "malformed_list")]
    return [(f"{name}-{cid}", pages, totals, reason) for cid, pages, totals, reason in rows]


CASES = [c for name in LISTS for c in _cases(name)]


@pytest.mark.parametrize("cid,pages,totals,reason", CASES, ids=[c[0] for c in CASES])
def test_pager_refuses_a_list_that_is_not_whole(monkeypatch: pytest.MonkeyPatch, cid: str, pages: list,
                                                totals: list | None, reason: str) -> None:
    st = _base(monkeypatch)
    _serve(st, cid.split("-")[0], pages, totals)
    with pytest.raises(dc.Unknown) as err:
        _read(st, cid.split("-")[0])
    assert err.value.reason == reason


@pytest.mark.parametrize("name", list(LISTS))
@pytest.mark.parametrize("two_pages", [False, True], ids=["one_page", "two_pages"])
def test_positive_control_distinct_items_with_the_right_count(monkeypatch: pytest.MonkeyPatch, name: str,
                                                              two_pages: bool) -> None:
    _, make, field, _, _ = LISTS[name]
    st = _base(monkeypatch)
    pages = [[make(i) for i in range(1, 101)], [make(101)]] if two_pages else [[make(1), make(2)]]
    count = 101 if two_pages else 2
    _serve(st, name, pages, [count] * len(pages))
    got = _read(st, name)
    assert len(got) == count
    if name == "pulls":
        assert sorted(p["number"] for p in got) == list(range(1, count + 1))


def test_reviewer_case_two_copies_of_run_11_with_total_two(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact finding: total_count=2 and run 11 twice must not read as two passing runs."""
    st = _base(monkeypatch)
    st.gh[CHECKS] = {"total_count": 2, "check_runs": [_run(11), _run(11)]}
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "duplicate_check_run"


# ── Tick level: the affected mission is UNKNOWN, or the tick is incomplete ──
def _tick_world(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> SimpleNamespace:
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("ato", ATO)])
    st.gql_pages.append(linear_page([tick_issue("RA-1", ((ATO, 5),))]))
    st.gh[sweep_path(ATO)] = [open_pull(5)]
    st.gh.update(pr_paths(ATO, 5))
    return st


def _missions(st: SimpleNamespace) -> dict:
    return json.loads(Path(st.path).read_text(encoding="utf-8"))["missions"]


@pytest.mark.parametrize("cid,pages,totals,reason", CASES, ids=[c[0] for c in CASES])
def test_tick_never_reports_health_from_a_list_that_is_not_whole(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cid: str, pages: list, totals: list | None,
        reason: str) -> None:
    st = _tick_world(monkeypatch, tmp_path)
    name = cid.split("-")[0]
    _serve(st, name, pages, totals)
    out = run(st)
    assert "error" not in out, out
    assert set(st.github) <= set(st.gh)  # failed on the planted break, never on an unserved fake path
    if name == "pulls":
        assert out["complete"] is False and out["incomplete"].get(ATO) == reason
        return
    record = _missions(st)["RA-1"]
    assert record["stage"] == "unknown" and record.get("tests_passed") is not True
    assert record["reason"] == reason  # unknown for the planted break, not for another cause


def test_tick_reviewer_case_mission_unknown_not_tests_passed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = _tick_world(monkeypatch, tmp_path)
    st.gh[CHECKS] = {"total_count": 2, "check_runs": [_run(11), _run(11)]}
    run(st)
    record = _missions(st)["RA-1"]
    assert set(st.github) <= set(st.gh)
    assert record["stage"] == "unknown" and record.get("tests_passed") is not True
    assert record["reason"] == "duplicate_check_run"


def test_tick_positive_control_two_distinct_runs_pass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    st = _tick_world(monkeypatch, tmp_path)
    st.gh[CHECKS] = {"total_count": 2, "check_runs": [_run(11), _run(12)]}
    out = run(st)
    record = _missions(st)["RA-1"]
    assert set(st.github) <= set(st.gh)
    assert out["complete"] is True and record["stage"] == "review_wait" and record["tests_passed"] is True


# ── Structural: a new paged read cannot be written without naming its identity ──
def _paged_calls(source: str) -> list[tuple[int, bool]]:
    """(line, passes identity) for every call to ``_paged`` in ``source``."""
    return [(node.lineno, any(k.arg == "identity" for k in node.keywords)) for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "_paged"]


def test_paged_identity_is_required_and_every_call_passes_it() -> None:
    param = inspect.signature(dg._paged).parameters["identity"]
    assert param.default is inspect.Parameter.empty and param.kind is inspect.Parameter.KEYWORD_ONLY
    calls = [c for m in ("delivery_collect", "delivery_collect_github")
             for c in _paged_calls((REPO_ROOT / f"app/server/{m}.py").read_text(encoding="utf-8"))]
    assert len(calls) >= 3 and all(ok for _, ok in calls), calls  # never passes on zero calls


def test_paged_call_walk_catches_an_unguarded_call() -> None:
    """Negative control: the walk above must see a call that names no identity."""
    calls = _paged_calls("x = _paged(r, p, t)\ny = dg._paged(r, p, t, identity='id', item='i')\n")
    assert calls == [(1, False), (2, True)]


# ── Extra fixes from the B5d audit ──
def test_single_pull_answer_for_another_number_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    st = _base(monkeypatch)
    st.gh[f"/repos/{ATO}/pulls/5"] = open_pull(6)
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "pull_mismatch"


@pytest.mark.parametrize("answer", [{"sha": SHA_B}, {}, [], "ok"], ids=["other_sha", "no_sha", "list", "text"])
def test_head_commit_answer_must_name_the_commit_asked(monkeypatch: pytest.MonkeyPatch, answer: object) -> None:
    st = _base(monkeypatch)
    st.gh[f"/repos/{ATO}/commits/{SHA_A}"] = answer
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "commit_mismatch"


def test_merge_commit_answer_must_name_the_commit_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    st = install_fakes(monkeypatch)
    st.gh.update(merged_paths(ATO, 5))
    st.gh[f"/repos/{ATO}/commits/{SHA_B}"] = {"sha": SHA_A}
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "commit_mismatch"


@pytest.mark.parametrize("status", [{"state": "success", "total_count": True},
                                    {"state": "success", "total_count": -1},
                                    {"state": "succes", "total_count": 1}],
                         ids=["total_bool", "total_negative", "state_unknown"])
def test_combined_status_must_be_a_known_state_and_count(monkeypatch: pytest.MonkeyPatch, status: dict) -> None:
    st = _base(monkeypatch)
    st.gh[f"/repos/{ATO}/commits/{SHA_A}/status"] = status
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    assert err.value.reason == "malformed_status"
