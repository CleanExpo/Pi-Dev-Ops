"""RA-8100 B6: ONE registry of every place an outside answer enters the delivery code, and the tests it drives.

The registry is ``delivery_collect_fields.IDENTITY`` (one row per outside request) plus one row for the stored
state file. (a) An AST walk over every ``app/server/delivery_*.py`` module finds each call to an outside
transport (the GitHub GET and pager, the Linear GraphQL read, the Vercel fetch, ``store.load``) and fails when
its enclosing function is not a registered reader. (b) For every row, a partial answer and malformed answers
(truncated dict, wrong type, None, empty) go through the real reader and must be rejected with a reason code;
the good answer is the positive control. A row with no rejection case fails ``test_every_row_has_cases``.
"""
from __future__ import annotations

import ast
import copy
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ALLOWED, API_KEY, ATO, REPO_ROOT, SHA_A, SHA_B, compare_answer, good_pr_paths, install_fakes, issue, linear_page,
    open_pull, sweep_path,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_fields as df
from app.server import delivery_collect_github as dg
from app.server import delivery_reconcile_store as store

STATE_ROW = {"state_file": {"reader": ("_locked", "build"), "code": "state_*"}}  # tick and status tile
TRANSPORT_DEFS = {"_get", "_paged", "read_only_gql"}  # the transports themselves, not readers
TRANSPORT_CALLS = {"_get", "_paged", "read_only_gql", "github_get", "_gql", "_vercel_get"}


def registry() -> dict[str, tuple[str, ...]]:
    """Row name to the reader function(s) that make the request: the one registry every test below uses."""
    rows = {name: (row["reader"],) for name, row in df.IDENTITY.items()}
    return {**rows, **{name: row["reader"] for name, row in STATE_ROW.items()}}


def _transport(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in TRANSPORT_CALLS
    if isinstance(func, ast.Attribute):
        owner = func.value.id if isinstance(func.value, ast.Name) else None
        return func.attr in TRANSPORT_CALLS or (func.attr == "load" and owner == "store")
    return False


def entry_points(source: str) -> set[str]:
    """Every function (transports excluded) that calls an outside transport directly."""
    return {fn.name for fn in ast.walk(ast.parse(source)) if isinstance(fn, ast.FunctionDef)
            and fn.name not in TRANSPORT_DEFS and any(_transport(n) for n in ast.walk(fn))}


def unregistered(found: set[str], rows: dict[str, tuple[str, ...]]) -> set[str]:
    return found - {reader for readers in rows.values() for reader in readers}


def _found() -> set[str]:
    out: set[str] = set()
    for path in sorted((REPO_ROOT / "app/server").glob("delivery_*.py")):
        out |= entry_points(path.read_text(encoding="utf-8"))
    return out


def test_every_entry_point_has_a_registry_row() -> None:
    assert unregistered(_found(), registry()) == set()
    assert {reader for readers in registry().values() for reader in readers} == _found()  # no stale row


def test_negative_control_the_walk_catches_an_entry_point_with_no_row() -> None:
    planted = ("def sneaky(p):\n    return store.load(p)\n"
               "def other(r, t):\n    return vercel_monitor._vercel_get('/x'), _paged(r, '/y', t)\n")
    assert entry_points(planted) == {"sneaky", "other"}
    assert unregistered(entry_points(planted), registry()) == {"sneaky", "other"}
    rows = {k: v for k, v in registry().items() if k != "compare"}
    assert unregistered(_found(), rows) == {"compare_status"}


# ── (b) every row: a partial and malformed answers are rejected through the real reader ──
P5, REVIEWS = f"/repos/{ATO}/pulls/5", f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"
CHECKS, STATUS = f"/repos/{ATO}/commits/{SHA_A}/check-runs?per_page=100&page=1", f"/repos/{ATO}/commits/{SHA_A}/status"
COMPARE, ENTRY = f"/repos/{ATO}/compare/{SHA_A}...{SHA_B}", {"id": "ato", "repo": ATO, "linear_project_id": "proj-1",
                                                              "linear_team_id": "team-1", "vercel_project_id": "prj_fake"}
REVIEW = {"id": 1, "user": {"login": "someone", "type": "User"}, "state": "COMMENTED", "commit_id": SHA_A,
          "submitted_at": "2026-11-14T03:00:00Z", "pull_request_url": f"https://api.github.com{P5}"}


def _world(st: SimpleNamespace, tmp: Path) -> None:
    st.name_asked = st.name_project = False  # every answer is built whole here; nothing fills a planted absence
    st.gh.update(good_pr_paths(ATO, 5))
    st.gh[REVIEWS] = [copy.deepcopy(REVIEW)]
    st.gh[f"/repos/{ATO}/commits/{SHA_A}"] = {"node_id": "C_fake", "sha": SHA_A}  # a real answer has more than sha
    st.gh[sweep_path(ATO)] = [{**open_pull(5), "base": {"repo": {"full_name": ATO}}}]
    st.gh[COMPARE] = compare_answer(SHA_A, SHA_B, "ahead")
    st.gql_pages[:] = [{"project": {"id": "proj-1", **linear_page([issue("RA-1")])["project"]}}]
    st.vc["*"] = {"deployments": [{"state": "READY", "created": 2, "target": "production",
                                   "meta": {"githubCommitSha": SHA_A}}]}
    st.state = tmp / "state.json"
    st.state.write_text(json.dumps(store.empty_state()), encoding="utf-8")


def _gh(path: str, *index: object) -> tuple[Callable, Callable]:
    """Where a GitHub answer unit sits: the whole body, or one item inside it."""
    def get(st: SimpleNamespace) -> object:
        unit = st.gh[path]
        for i in index:
            unit = unit[i]
        return unit

    def put(st: SimpleNamespace, value: object) -> None:
        if not index:
            st.gh[path] = value
            return
        parent = st.gh[path]
        for i in index[:-1]:
            parent = parent[i]
        parent[index[-1]] = value
    return get, put


def _pr5(st: SimpleNamespace) -> None:
    dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))


def _missions(st: SimpleNamespace) -> None:
    read = dc.fetch_missions(API_KEY, ENTRY, tick=dc.Tick(allowed=ALLOWED), since="2026-11-01T00:00:00Z")
    if not read.complete:
        raise dc.Unknown(read.reason or "incomplete")  # the reader's own rejection: an incomplete read


def _state_put(st: SimpleNamespace, value: object) -> None:
    st.state.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


def _state_load(st: SimpleNamespace) -> None:
    try:
        store.load(st.state)
    except store.StoreError as exc:
        raise dc.Unknown(str(exc)) from None


# row: (get the good unit, put a unit, call the real reader, the field a partial answer drops)
CASES: dict[str, tuple[Callable, Callable, Callable, tuple]] = {
    "pulls_list": (*_gh(sweep_path(ATO), 0), lambda st: dg.open_prs(ATO, tick=dc.Tick(allowed=ALLOWED)),
                   ("base", "repo", "full_name")),
    "pull": (*_gh(P5), _pr5, ("number",)),
    "commit": (*_gh(f"/repos/{ATO}/commits/{SHA_A}"), _pr5, ("sha",)),
    "check_run": (*_gh(CHECKS, "check_runs", 0), _pr5, ("head_sha",)),
    "status": (*_gh(STATUS), _pr5, ("sha",)),
    "review": (*_gh(REVIEWS, 0), _pr5, ("pull_request_url",)),
    "compare": (*_gh(COMPARE), lambda st: dg.compare_status(ATO, SHA_A, SHA_B, tick=dc.Tick(allowed=ALLOWED)),
                ("total_commits",)),
    "linear_issue": (lambda st: st.gql_pages[0], lambda st, v: st.gql_pages.__setitem__(0, v), _missions,
                     ("project", "id")),
    "vercel": (lambda st: st.vc["*"], lambda st, v: st.vc.__setitem__("*", v),
               lambda st: dc.vercel_latest_ready(ENTRY, tick=dc.Tick(allowed=ALLOWED)), ("deployments", 0, "created")),
    "state_file": (lambda st: json.loads(st.state.read_text(encoding="utf-8")), _state_put, _state_load,
                   ("alerts",)),
}


def _drop(unit: object, path: tuple) -> object:
    out = copy.deepcopy(unit)
    target = out
    for part in path[:-1]:
        target = target[part]
    del target[path[-1]]
    return out


def _truncate(unit: object) -> object:
    """Keep only the first key of each object on the way down: a dict cut short."""
    if isinstance(unit, dict) and unit:
        key = next(iter(unit))
        return {key: _truncate(unit[key])} if len(unit) == 1 else {key: unit[key]}
    if isinstance(unit, list) and unit:
        return [_truncate(unit[0])]
    return unit


VARIANTS: dict[str, Callable[[object, tuple], object]] = {
    "partial": _drop, "truncated_dict": lambda unit, path: _truncate(unit),
    "wrong_type": lambda unit, path: "not-an-object", "wrong_type_list": lambda unit, path: [unit],
    "none": lambda unit, path: None, "empty": lambda unit, path: {},
}


def _reason(st: SimpleNamespace, row: str, variant: str | None) -> str | None:
    get, put, call, path = CASES[row]
    if variant == "truncated_text":
        put(st, st.state.read_text(encoding="utf-8")[:9])
    elif variant is not None:
        put(st, VARIANTS[variant](get(st), path))
    try:
        call(st)
    except dc.Unknown as exc:
        return exc.reason
    return None


def test_every_row_has_cases() -> None:
    assert set(CASES) == set(registry())


def _params() -> list:
    out = []
    for row in registry():
        out.append(pytest.param(row, None, id=f"{row}-control"))
        out += [pytest.param(row, v, id=f"{row}-{v}") for v in VARIANTS]
    return out + [pytest.param("state_file", "truncated_text", id="state_file-truncated_text")]


@pytest.mark.parametrize("row,variant", _params())
def test_partial_or_malformed_answer_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, row: str,
                                                 variant: str | None) -> None:
    st = install_fakes(monkeypatch)
    _world(st, tmp_path)
    reason = _reason(st, row, variant)
    if variant is None:
        assert reason is None  # positive control: the good answer passes, so a rejection is the variant's
    else:
        assert isinstance(reason, str) and reason, (row, variant)
        if row == "state_file":
            assert reason.startswith("state_"), reason
    assert st.net == []


@pytest.mark.parametrize("project,reason", [("proj-1", None), ("proj-other", "linear_project_mismatch"),
                                            ("PROJ-1", "linear_project_mismatch")])
def test_a_linear_page_about_another_project_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                                         project: str, reason: str | None) -> None:
    """Well formed, but names another project: the read is incomplete with the row's reason, never whole."""
    st = install_fakes(monkeypatch)
    _world(st, tmp_path)
    st.gql_pages[0]["project"]["id"] = project
    assert _reason(st, "linear_issue", None) == reason
