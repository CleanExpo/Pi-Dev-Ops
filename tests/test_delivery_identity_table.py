"""RA-8100 B6 part 1: one request-to-answer table owns every identity check.

Every function in the collector that makes an outside request has one row per request in
``delivery_collect_fields.IDENTITY``. A row names what was asked and which answer field must equal it,
or gives a written reason why the answer carries no identity. The completeness walk parses the source,
so a new reader with no row fails here. For every row with a check, an answer whose identity names
something else, is absent, null or the wrong type fails the read with that row's reason code.
"""
from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import pytest
from _delivery_reconcile_support import (
    ALLOWED, ATO, PIDEV, REPO_ROOT, SHA_A, SHA_B, SHA_C, compare_answer, good_pr_paths, install_fakes, linear_page,
    merged_paths, open_pull, reg_entry, run, setup_tick, sweep_path, tick_issue,
)
from test_delivery_field_inventory import INVENTORY

from app.server import delivery_collect as dc
from app.server import delivery_collect_fields as df
from app.server import delivery_collect_github as dg

IDENTITY: dict = getattr(df, "IDENTITY", {})
TRANSPORTS = {"_get", "_paged", "read_only_gql"}  # the counted GET, the pager, the GraphQL read
OUTSIDE = TRANSPORTS | {"github_get", "_gql", "_vercel_get"}
BASE = f"/repos/{ATO}"
CHECKS = f"{BASE}/commits/{SHA_A}/check-runs?per_page=100&page=1"
_ABSENT = object()


def _called(node: ast.AST) -> str | None:
    func = node.func if isinstance(node, ast.Call) else None
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None


def requests(source: str) -> Counter:
    """Per function (transports excluded): how many outside requests it makes directly."""
    out: Counter = Counter()
    for fn in [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)]:
        if fn.name not in TRANSPORTS:
            out[fn.name] += sum(1 for node in ast.walk(fn) if _called(node) in OUTSIDE)
    return +out


def unlisted(found: Counter) -> dict:
    """Readers whose requests outnumber their rows (a reader with no row at all included)."""
    rows = Counter(row["reader"] for row in IDENTITY.values())
    return {fn: n for fn, n in found.items() if n > rows.get(fn, 0)}


def _collector() -> Counter:
    return sum((requests((REPO_ROOT / f"app/server/{m}.py").read_text(encoding="utf-8"))
                for m in ("delivery_collect", "delivery_collect_github")), Counter())


def test_every_outside_request_has_exactly_one_row() -> None:
    assert unlisted(_collector()) == {}
    assert Counter(row["reader"] for row in IDENTITY.values()) == _collector()


def test_negative_control_the_walk_catches_a_reader_with_no_row() -> None:
    planted = "def sneaky(repo, tick):\n    return _get(repo, '/x', tick), vercel_monitor._vercel_get('/y')\n"
    assert unlisted(requests(planted)) == {"sneaky": 2}
    assert unlisted(_collector() + Counter({"compare_status": 1})) == {"compare_status": 2}


def test_rows_are_well_formed_and_every_check_is_applied() -> None:
    assert len(IDENTITY) == 9
    for name, row in IDENTITY.items():
        assert row["asked"] and isinstance(row["checks"], tuple), name
        if not row["checks"]:
            assert isinstance(row.get("why"), str) and len(row["why"]) > 20 and row.get("code") is None, name
        for path, asked, kind in row["checks"]:
            assert asked in row["asked"] and kind in df._KINDS and isinstance(row["code"], str), name
    applied = set()
    for module in ("delivery_collect", "delivery_collect_github"):
        tree = ast.parse((REPO_ROOT / f"app/server/{module}.py").read_text(encoding="utf-8"))
        applied |= {n.args[0].value for n in ast.walk(tree) if _called(n) in ("_same", "identity_mismatch")
                    and n.args and isinstance(n.args[0], ast.Constant)}
    assert applied == {name for name, row in IDENTITY.items() if row["checks"]}


def test_every_identity_field_has_an_inventory_row() -> None:
    fields = {(src, fld) for src, fld, *_ in INVENTORY}
    source = {"linear_issue": "linear_page"}  # the project id is on the page, not on an issue node
    for name, row in IDENTITY.items():
        for path, _, kind in row["checks"]:
            assert (source.get(name, name), ".".join(path)) in fields, name
            if kind == "tail":
                assert (name, ".".join(path) + ".sha") in fields, name


def _plant(monkeypatch: pytest.MonkeyPatch, row: str, value: object) -> str | None:
    """Plant ``value`` at the row's identity field in an otherwise good answer; the read's reason or None."""
    st = install_fakes(monkeypatch)
    st.name_asked = st.name_project = False  # answers below are built whole; nothing fills a planted absence
    st.gh.update(good_pr_paths(ATO, 5))
    st.gh[f"{BASE}/compare/{SHA_A}...{SHA_B}"] = compare_answer(SHA_A, SHA_B, "ahead")
    st.gh[sweep_path(ATO)] = [{**open_pull(5), "base": {"repo": {"full_name": ATO.lower()}}}]
    st.gh[f"{BASE}/pulls/5/reviews?per_page=100&page=1"] = [
        {"id": 1, "user": {"login": "someone", "type": "User"}, "state": "COMMENTED", "commit_id": SHA_A,
         "submitted_at": "2026-11-14T03:00:00Z", "pull_request_url": f"https://api.github.com{BASE}/pulls/5"}]
    target = {"pull": st.gh[f"{BASE}/pulls/5"], "commit": st.gh[f"{BASE}/commits/{SHA_A}"],
              "check_run": st.gh[CHECKS]["check_runs"][0], "status": st.gh[f"{BASE}/commits/{SHA_A}/status"],
              "compare": st.gh[f"{BASE}/compare/{SHA_A}...{SHA_B}"], "pulls_list": st.gh[sweep_path(ATO)][0],
              "review": st.gh[f"{BASE}/pulls/5/reviews?per_page=100&page=1"][0]}[row]
    path = IDENTITY[row]["checks"][0][0]
    for part in path[:-1]:
        target = target[part]
    if value is _ABSENT:
        target.pop(path[-1], None)
    elif value is not KEEP:
        target[path[-1]] = value
    try:
        if row == "compare":
            dg.compare_status(ATO, SHA_A, SHA_B, tick=dc.Tick(allowed=ALLOWED))
        elif row == "pulls_list":
            dg.open_prs(ATO, tick=dc.Tick(allowed=ALLOWED))
        else:
            dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))
    except dc.Unknown as exc:
        return exc.reason
    return None


KEEP = object()
OTHER = {"sha": SHA_C, "int": 6, "repo": "CleanExpo/Other", "suffix": f"https://api.github.com{BASE}/pulls/6"}
WRONG_TYPE = {"sha": [SHA_A], "int": "5", "repo": [ATO], "suffix": 5}
PLANTED = {"pull", "commit", "check_run", "status", "compare", "pulls_list", "review"}  # linear: registry test


def _generated() -> list:
    rows = []
    for name, row in IDENTITY.items():
        if not row["checks"] or name not in PLANTED:
            continue
        kind = row["checks"][0][2]
        for label, value in (("other", OTHER[kind]), ("absent", _ABSENT), ("null", None),
                             ("wrong_type", WRONG_TYPE[kind]), ("empty", "")):
            rows.append(pytest.param(name, value, row["code"], id=f"{name}-{label}"))
        rows.append(pytest.param(name, KEEP, None, id=f"{name}-control"))
    return rows


@pytest.mark.parametrize("row,value,reason", _generated())
def test_an_answer_naming_something_else_fails_with_its_reason(monkeypatch: pytest.MonkeyPatch, row: str,
                                                               value: object, reason: str | None) -> None:
    assert _plant(monkeypatch, row, value) == reason


def test_generated_rows_cover_every_checked_row() -> None:
    assert {p.values[0] for p in _generated()} == PLANTED
    assert {name for name, row in IDENTITY.items() if row["checks"]} == PLANTED | {"linear_issue"}


def _compare(monkeypatch: pytest.MonkeyPatch, body: object) -> str | None:
    st = install_fakes(monkeypatch)
    st.gh[f"{BASE}/compare/{SHA_A}...{SHA_B}"] = body
    try:
        dg.compare_status(ATO, SHA_A, SHA_B, tick=dc.Tick(allowed=ALLOWED))
    except dc.Unknown as exc:
        return exc.reason
    return None


# The head side of compare: ``commits`` is always present and every entry is a SHA; when the base is behind
# the head (``ahead`` or ``diverged``) the list is non-empty and ends on the head asked.
@pytest.mark.parametrize("status,commits,reason", [
    ("ahead", [{"sha": SHA_C}], "compare_mismatch"), ("diverged", [{"sha": SHA_B}, {"sha": SHA_C}], "compare_mismatch"),
    ("ahead", [{"sha": "nope"}], "compare_mismatch"), ("ahead", [5], "compare_mismatch"), ("ahead", "x", "compare_mismatch"),
    ("ahead", [{}], "compare_mismatch"), ("behind", [{"sha": "nope"}], "compare_mismatch"),
    ("ahead", [{"sha": SHA_B}], None), ("diverged", [{"sha": SHA_C}, {"sha": SHA_B.upper()}], None),
    ("ahead", [], "compare_mismatch"), ("diverged", [], "compare_mismatch"), ("ahead", None, "compare_mismatch"),
    ("ahead", _ABSENT, "compare_mismatch"), ("identical", [], "compare_mismatch"), ("identical", None, "compare_mismatch"),
    ("behind", _ABSENT, "compare_mismatch"), ("behind", [{"sha": SHA_C}], "compare_mismatch"), ("behind", [], None),
])
def test_compare_head_side(monkeypatch: pytest.MonkeyPatch, status: str, commits: object, reason: str | None) -> None:
    body = compare_answer(SHA_A, SHA_B, status)
    if commits is _ABSENT:
        body.pop("commits")
    else:
        body["commits"] = commits
        body["total_commits"] = len(commits) if isinstance(commits, (list, str)) else 0  # whole, as GitHub counts
        body["ahead_by"] = body["total_commits"]
    assert _compare(monkeypatch, body) == reason


def test_compare_base_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _compare(monkeypatch, compare_answer(SHA_A.upper(), SHA_B, "ahead")) is None
    assert _compare(monkeypatch, {**compare_answer(SHA_A, SHA_B, "ahead"), "base_commit": SHA_A}) == "compare_mismatch"


def test_reviewer_case_a_compare_about_another_base_never_verifies_the_merge(monkeypatch: pytest.MonkeyPatch,
                                                                             tmp_path: Path) -> None:
    own = "d" * 40
    st = setup_tick(monkeypatch, tmp_path, [reg_entry("pi-dev-ops", PIDEV)])
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", own)
    st.gh[sweep_path(PIDEV)] = []
    st.gh.update(merged_paths(PIDEV, 4, SHA_B))
    st.gh[f"/repos/{PIDEV}/compare/{SHA_B}...{own}"] = {"status": "ahead", "base_commit": {"sha": "e" * 40},
                                                        "commits": [{"sha": own}], "total_commits": 1}
    st.gql_pages.append(linear_page([tick_issue("RA-4", ((PIDEV, 4),))]))
    out = run(st)
    state = json.loads(Path(st.path).read_text(encoding="utf-8"))
    record = state["missions"]["RA-4"]
    assert record["verified_sha"] is None and record["reason"] == "compare_compare_mismatch", record
    assert "CHECK_ACCEPTANCE" not in {a.get("code") for a in state["alerts"].values()}
    assert "RA-4" in out["not_refreshed_ids"]


@pytest.mark.parametrize("total,reason", [(1, None), (0, "compare_mismatch"), (251, "compare_mismatch"), (2, "compare_mismatch"),
                                          (None, "compare_mismatch"), ("1", "compare_mismatch"), (-1, "compare_mismatch")])
def test_compare_head_cannot_be_confirmed_from_a_paged_list(monkeypatch: pytest.MonkeyPatch, total: object,
                                                             reason: str | None) -> None:
    """GitHub lists at most 250 compare commits: more in ``total_commits`` than in the list leaves the head unseen."""
    assert _compare(monkeypatch, {**compare_answer(SHA_A, SHA_B, "ahead"), "total_commits": total}) == reason
