"""RA-8100 B5e: generated negative rows for every outside field, planted through its collector function.

For each inventory row the domain's negative values are generated (wrong type, wrong format, empty,
null, absent, and for a closed list an unknown value and a wrong-case value). Each is planted into an
otherwise good answer and the collector function for that source is called; the outcome must be the
one the inventory documents. No network: every outside call is a fake from the support module.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from _delivery_reconcile_support import (
    ALLOWED, API_KEY, ATO, NOW, SHA_A, SHA_B, compare_answer, good_pr_paths, install_fakes, issue, linear_page, merged_pull,
    open_facts, open_pull,
)
from test_delivery_field_inventory import INVENTORY, PRESENT_REQUIRED

from app.server import delivery_collect as dc
from app.server import delivery_collect_fields as df
from app.server import delivery_collect_github as dg
from app.server import delivery_reconcile_links as links
from app.server import delivery_stage as ds

_ABSENT = object()
_KEEP = object()
NEGATIVES: dict[str, list[tuple[str, object]]] = {
    "sha": [("int", 5), ("list", [SHA_A]), ("dict", {}), ("bool", True), ("not_hex", "not-a-sha"),
            ("short", "a" * 39), ("long", "a" * 41), ("non_hex", "g" * 40)],
    "timestamp": [("int", 5), ("list", []), ("dict", {}), ("bool", True), ("garbage", "yesterday"),
                  ("no_tz", "2026-11-14T01:00:00"), ("date_only", "2026-11-14"), ("bad_day", "2026-02-30T01:00:00Z"),
                  ("before_year_1", "0001-01-01T00:00:00+14:00"), ("after_year_9999", "9999-12-31T23:59:59-14:00")],
    "enum": [("int", 5), ("list", ["x"]), ("dict", {}), ("bool", True), ("unknown", "zz_unlisted")],
    "posint": [("text", "7"), ("zero", 0), ("negative", -1), ("bool", True), ("float", 1.5), ("list", []),
               ("dict", {})],
    "count": [("text", "1"), ("negative", -1), ("bool", True), ("float", 1.0), ("list", [])],
    "bool": [("text", "true"), ("int", 1), ("zero", 0), ("list", []), ("dict", {})],
    "login": [("int", 5), ("list", []), ("dict", {}), ("bool", True), ("space", "has space"),
              ("too_long", "x" * 40), ("leading_dash", "-x")],
    "linear_id": [("int", 42), ("list", []), ("bool", True), ("no_number", "RA"), ("space", "RA 1"),
                  ("too_long", "R" * 20 + "-1")],
    "node_id": [("int", 5), ("list", []), ("bool", True), ("space", "a b"), ("too_long", "x" * 65)],
    "text": [("int", 5), ("list", []), ("dict", {}), ("bool", True), ("blank", "   "), ("too_long", "x" * 300)],
    "text_any": [("int", 5), ("zero", 0), ("list", []), ("dict", {"text": "x"}), ("bool", True), ("false", False)],
    "object": [("text", "x"), ("int", 5), ("list", []), ("bool", True)],
    "list": [("dict", {}), ("text", "x"), ("int", 5)],
}


def _set(target: dict, path: str, value: object) -> None:
    *parents, last = path.split(".")
    if value is _KEEP:
        return
    for part in parents:
        target = target[part][0] if isinstance(target[part], list) else target[part]
    if value is _ABSENT:
        target.pop(last, None)
    else:
        target[last] = value


def _tick() -> dc.Tick:
    return dc.Tick(allowed=ALLOWED)


def _outcome(call) -> tuple[str, str | None]:  # type: ignore[no-untyped-def]
    try:
        value = call()
    except dc.MissingCommit as exc:
        return "missing", exc.reason
    except dc.Unknown as exc:
        return "unknown", exc.reason
    if isinstance(value, dc.MissionRead):
        return ("ok", None) if value.complete else ("unknown", value.reason)
    return "ok", None


def _github(st: SimpleNamespace, path: str, payload: dict, field: str, value: object, call) -> tuple:  # type: ignore[no-untyped-def]
    body = copy.deepcopy(payload)
    _set(body, field, value)
    st.gh[path] = body if not isinstance(st.gh.get(path), list) else [body]
    return _outcome(call)


def _plant(st: SimpleNamespace, source: str, field: str, value: object, mp: pytest.MonkeyPatch) -> tuple:
    """Plant ``value`` at ``field`` of one good answer and call that source's collector function."""
    st.name_asked = st.name_project = False  # every answer below is built whole; the fake must not fill a planted absence
    st.gh.update(good_pr_paths(ATO, 5))
    pr5 = lambda: dg.pr_evidence(ATO, 5, tick=_tick())  # noqa: E731
    base = f"/repos/{ATO}"
    if source == "pulls_list":
        named = {"base": {"repo": {"full_name": ATO}}}
        item = copy.deepcopy({**open_pull(7), **named})
        _set(item, field, value)
        st.gh[f"{base}/pulls?state=open&per_page=100&page=1"] = [{**open_pull(5), **named}, item]
        return _outcome(lambda: dg.open_prs(ATO, tick=_tick()))
    if source in ("pull", "pull_merged"):
        good = open_pull(5) if source == "pull" else merged_pull(5)
        st.gh[f"{base}/commits/{SHA_B}"] = {"sha": SHA_B}
        return _github(st, f"{base}/pulls/5", good, field, value, pr5)
    if source == "commit":
        return _github(st, f"{base}/commits/{SHA_A}", {"sha": SHA_A}, field, value, pr5)
    if source in ("check_runs", "check_run"):
        path = f"{base}/commits/{SHA_A}/check-runs?per_page=100&page=1"
        good = st.gh[path] if source == "check_runs" else st.gh[path]["check_runs"][0]
        if source == "check_runs":
            return _github(st, path, good, field, value, pr5)
        run = copy.deepcopy(good)
        _set(run, field, value)
        st.gh[path] = {"total_count": 1, "check_runs": [run]}
        return _outcome(pr5)
    if source == "status":
        return _github(st, f"{base}/commits/{SHA_A}/status", {"state": "pending", "total_count": 0, "sha": SHA_A}, field, value, pr5)
    if source == "review":
        good = {"id": 1, "user": {"login": "someone", "type": "User"}, "state": "COMMENTED", "commit_id": SHA_A,
                "submitted_at": "2026-11-14T03:00:00Z", "pull_request_url": f"https://api.github.com{base}/pulls/5"}
        st.gh[f"{base}/pulls/5/reviews?per_page=100&page=1"] = []
        return _github(st, f"{base}/pulls/5/reviews?per_page=100&page=1", good, field, value, pr5)
    if source == "compare":
        body = compare_answer(SHA_A, SHA_B, "ahead")
        _set(body, field, value)
        st.gh[f"{base}/compare/{SHA_A}...{SHA_B}"] = body
        return _outcome(lambda: dg.compare_status(ATO, SHA_A, SHA_B, tick=_tick()))
    return _plant_other(st, source, field, value, mp)


def _plant_other(st: SimpleNamespace, source: str, field: str, value: object, mp: pytest.MonkeyPatch) -> tuple:
    entry = {"id": "ato", "repo": ATO, "linear_project_id": "proj-1", "linear_team_id": "team-1",
             "vercel_project_id": "prj_fake"}
    if source in ("linear_page", "linear_issue"):
        page = linear_page([issue("RA-1")], "c1")
        page["project"]["id"] = "proj-1"
        _set(page if source == "linear_page" else page["project"]["issues"]["nodes"][0], field, value)
        st.gql_pages = [page, {"project": {"id": "proj-1", **linear_page([issue("RA-2")])["project"]}}]
        read = _outcome(lambda: dc.fetch_missions(API_KEY, entry, tick=_tick(), since="2026-11-01T00:00:00Z"))
        if read != ("ok", None) or source == "linear_page":
            return read
        node = page["project"]["issues"]["nodes"][0]  # whole page: the classifier judges the mission itself
        record = ds.classify(node, [open_facts(5, repo=ATO)], {}, NOW, repo=ATO, project_id="ato")[0]
        return ("unknown", record["reason"]) if record["stage"] in ("unknown", "missing_commit") else ("ok", None)
    if source == "linear_links":
        node = issue("RA-1")
        node["attachments"]["nodes"] = [{"url": "https://example.invalid/x"}]
        _set(node, field, value)
        cuts: list[tuple] = []  # what the run's one writer, ``cut``, is told: (source, subject, reason)
        run = SimpleNamespace(registry=SimpleNamespace(allowed=ALLOWED), summary={"refs_outside_scope": 0},
                              linked=set(), tick=_tick(), sweep={}, cut=lambda *args: cuts.append(args))
        read = links._refs(run, node)
        assert cuts == ([] if read is not None else [("links", "RA-1", "links_incomplete")])  # D48
        return ("ok", None) if read is not None else ("unknown", "links_incomplete")
    if source == "vercel":
        good = {"deployments": [{"state": "READY", "created": 2, "target": "production",
                                 "meta": {"githubCommitSha": SHA_A}}]}
        _set(good if field == "deployments" else good["deployments"][0], field, value)
        st.vc["*"] = good
        return _outcome(lambda: dc.vercel_latest_ready(entry, tick=_tick()))
    for name in ("RAILWAY_GIT_COMMIT_SHA", "BUILD_REVISION"):
        mp.delenv(name, raising=False)  # one variable at a time
    if value is _KEEP:
        mp.setenv(field, SHA_A)
    elif value is not _ABSENT:
        mp.setenv(field, value if isinstance(value, str) else repr(value))
    return ("ok", None) if dc.own_revision() is not None else ("unknown", "no_revision")


def _expected(text: str, reason: str) -> tuple[str, str | None]:
    if text == "ok":
        return "ok", None
    if text.startswith("missing:"):
        return "missing", text.split(":", 1)[1]
    return "unknown", reason


def _rows() -> list:
    rows = []
    for source, field, domain, null, empty, reason, _ in INVENTORY:
        for label, value in NEGATIVES[domain]:
            if source == "env" and not isinstance(value, str):
                continue  # the environment only holds text
            rows.append(pytest.param(source, field, value, ("unknown", reason), id=f"{source}.{field}-{label}"))
        if domain == "enum":
            rows.append(pytest.param(source, field, "CASE", ("unknown", reason), id=f"{source}.{field}-wrong_case"))
        empty_out = _expected(null if empty == "null" else empty, reason)
        rows.append(pytest.param(source, field, "", empty_out, id=f"{source}.{field}-empty"))
        if source != "env":
            rows.append(pytest.param(source, field, None, _expected(null, reason), id=f"{source}.{field}-null"))
        absent = ("unknown", reason) if (source, field) in PRESENT_REQUIRED else _expected(null, reason)
        if source == "linear_issue" and field in df.ISSUE_FIELDS:  # a field the query asks for: absent is a cut page
            absent = ("unknown", "malformed_page")
        rows.append(pytest.param(source, field, _ABSENT, absent, id=f"{source}.{field}-absent"))
    return rows


GOOD_ENUM = {("pulls_list", "user.type"): "User", ("pulls_list", "state"): "open",
             ("pull", "state"): "open", ("pull", "user.type"): "User",
             ("check_run", "status"): "completed", ("check_run", "conclusion"): "success",
             ("status", "state"): "success", ("review", "state"): "COMMENTED", ("review", "user.type"): "User",
             ("compare", "status"): "ahead", ("linear_issue", "state.type"): "started", ("vercel", "state"): "READY"}


@pytest.mark.parametrize("source,field,value,expected", _rows())
def test_out_of_domain_value_has_its_documented_outcome(monkeypatch: pytest.MonkeyPatch, source: str, field: str,
                                                        value: object, expected: tuple) -> None:
    st = install_fakes(monkeypatch)
    if value == "CASE":
        value = GOOD_ENUM[(source, field)].swapcase()
    assert _plant(st, source, field, value, monkeypatch) == expected
    assert st.net == []


@pytest.mark.parametrize("source,field", sorted({(s, f) for s, f, *_ in INVENTORY}))
def test_positive_control_the_unchanged_answer_is_accepted(monkeypatch: pytest.MonkeyPatch, source: str,
                                                          field: str) -> None:
    """Each planter's base answer is good: with nothing planted the collector accepts it."""
    st = install_fakes(monkeypatch)
    assert _plant(st, source, field, _KEEP, monkeypatch) == ("ok", None)


# Real-shaped values that must stay IN the domain: an over-strict validator would make a read never whole.
ACCEPTED = [("pulls_list", "user.login", "dependabot[bot]"), ("review", "user.login", "fake-reviewer-one"),
            ("pulls_list", "created_at", "2026-11-14T01:00:00.123Z"), ("pull", "created_at", "2026-11-14T11:00:00+10:00"),
            ("check_run", "completed_at", "2026-11-14T02:00:00.5+00:00"), ("pull", "head.sha", SHA_A.upper()),
            ("linear_issue", "identifier", "RA-8100"), ("linear_issue", "id", "0b6f3c1e-1d2a-4c5b-9e8f-123456789abc"),
            ("check_run", "conclusion", "action_required"), ("vercel", "state", "ERROR")]


@pytest.mark.parametrize("source,field,value", ACCEPTED, ids=[f"{s}.{f}-{v}" for s, f, v in ACCEPTED])
def test_real_shaped_value_is_accepted(monkeypatch: pytest.MonkeyPatch, source: str, field: str, value: str) -> None:
    assert _plant(install_fakes(monkeypatch), source, field, value, monkeypatch) == ("ok", None)


def test_pending_review_with_no_submitted_time_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    st = install_fakes(monkeypatch)
    st.gh.update(good_pr_paths(ATO, 5))
    st.gh[f"/repos/{ATO}/pulls/5/reviews?per_page=100&page=1"] = [
        {"id": 1, "user": {"login": "someone", "type": "User"}, "state": "PENDING", "commit_id": SHA_A,
         "submitted_at": None}]
    assert dg.pr_evidence(ATO, 5, tick=dc.Tick(allowed=ALLOWED))["reviews"][0]["submitted_at"] is None


def test_every_enum_row_has_a_good_value_for_the_case_row() -> None:
    assert {(s, f) for s, f, d, *_ in INVENTORY if d == "enum"} == set(GOOD_ENUM)


# P1-3: a pull answer that contradicts itself is not a read of either state, in both directions.
CONTRADICTORY = [
    pytest.param({"state": "closed", "merged": False, "merged_at": "2026-11-14T03:00:00Z"}, id="unmerged_with_time"),
    pytest.param({"state": "open", "merged": False, "merged_at": "2026-11-14T03:00:00Z"}, id="open_with_time"),
    pytest.param({"state": "open", "merged": True, "merged_at": "2026-11-14T03:00:00Z",
                  "merge_commit_sha": SHA_B}, id="merged_but_open"),
    pytest.param({"state": "closed", "merged": True, "merged_at": None, "merge_commit_sha": SHA_B},
                 id="merged_without_time"),
]


@pytest.mark.parametrize("change", CONTRADICTORY)
def test_contradictory_pull_answer_is_malformed(monkeypatch: pytest.MonkeyPatch, change: dict) -> None:
    st = install_fakes(monkeypatch)
    st.gh.update(good_pr_paths(ATO, 5))
    st.gh[f"/repos/{ATO}/commits/{SHA_B}"] = {"sha": SHA_B}
    st.gh[f"/repos/{ATO}/pulls/5"] = {**open_pull(5), **change}
    assert _outcome(lambda: dg.pr_evidence(ATO, 5, tick=_tick())) == ("unknown", "malformed_pull")
