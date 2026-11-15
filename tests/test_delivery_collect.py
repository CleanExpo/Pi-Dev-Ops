"""RA-8100 read-only delivery collector: spec rows T1, T3, T5, T8, T10, E4, E5, E6, F1, F2 (collector
parts only). Every network helper is a fake (see _delivery_reconcile_support); no real token."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
from types import SimpleNamespace

from _delivery_reconcile_support import (
    ALLOWED, API_KEY, ATO, HTTP404, PIDEV, REPO_ROOT, SHA_A, good_pr_paths, install_fakes, issue, linear_page,
    open_pull,
)

from app.server import delivery_collect as dc
from app.server import delivery_collect_github as dg
from app.server import ticket_sweeper_io

SINCE = "2026-11-01T00:00:00Z"
ENTRY = {"id": "ato", "repo": ATO, "linear_project_id": "proj-1", "linear_team_id": "team-1"}
CCW_ENTRY = {"id": "client-portal", "linear_project_name": "Portal", "repo": "cleanexpo/CCW-crm",
             "linear_project_id": "proj-9", "linear_team_id": "team-9"}


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    return install_fakes(monkeypatch)


def _tick(**kw: object) -> dc.Tick:
    return dc.Tick(allowed=kw.pop("allowed", ALLOWED), **kw)


def _registry_file(tmp_path: Path, projects: list[dict]) -> str:
    path = tmp_path / "projects.json"
    path.write_text(json.dumps({"projects": projects}), encoding="utf-8")
    return str(path)


# ── T1: missions come from Linear, not in-memory sessions ────────────────────
def test_t1_missions_and_unlinked_pr_are_read_from_sources(fakes: SimpleNamespace) -> None:
    fakes.gql_pages = [linear_page([issue("RA-1", f"https://github.com/{ATO}/pull/7")])]
    fakes.gh[f"/repos/{ATO}/pulls?state=open&per_page=100&page=1"] = [open_pull(7), open_pull(9)]
    read = dc.fetch_missions(API_KEY, ENTRY, tick=_tick(), since=SINCE)
    assert read.complete and [i["identifier"] for i in read.issues] == ["RA-1"]
    assert ticket_sweeper_io.pr_refs(read.issues[0]) == [(ATO, 7)]
    prs = dg.open_prs(ATO, tick=_tick())
    assert [(p["number"], p["author_type"]) for p in prs] == [(7, "User"), (9, "User")]
    assert fakes.net == []


# ── T3: an unavailable read is UNKNOWN, never an empty list ──────────────────
@pytest.mark.parametrize("broken", ["check-runs?per_page=100&page=1", "reviews?per_page=100&page=1", "status"])
def test_t3_failed_ci_or_review_read_is_unknown(fakes: SimpleNamespace, broken: str) -> None:
    fakes.gh.update(good_pr_paths(ATO, 5))
    target = next(p for p in fakes.gh if p.endswith(broken))
    fakes.gh[target] = RuntimeError("upstream unavailable")
    with pytest.raises(dc.Unknown) as err:
        dg.pr_evidence(ATO, 5, tick=_tick())
    assert "upstream" not in str(err.value)  # reason code only, never upstream text


def test_t3_good_reads_return_whole_evidence(fakes: SimpleNamespace) -> None:
    fakes.gh.update(good_pr_paths(ATO, 5))
    ev = dg.pr_evidence(ATO, 5, tick=_tick())
    assert ev["state"] == "open" and ev["head_sha"] == SHA_A and len(ev["check_runs"]) == 1
    assert ev["status"] == {"state": "success", "total_count": 0} and ev["reviews"] == []


# ── T5: missing commit ───────────────────────────────────────────────────────
@pytest.mark.parametrize("case", ["empty_head", "head_404", "merged_no_sha"])
def test_t5_missing_commit(fakes: SimpleNamespace, case: str) -> None:
    paths = good_pr_paths(ATO, 5)
    pull = paths[f"/repos/{ATO}/pulls/5"]
    if case == "empty_head":
        pull["head"]["sha"] = ""
    elif case == "head_404":
        paths[f"/repos/{ATO}/commits/{SHA_A}"] = HTTP404("not found")
    else:
        pull.update(state="closed", merged=True, merge_commit_sha=None, merged_at="2026-11-14T03:00:00Z")
    fakes.gh.update(paths)
    with pytest.raises(dc.MissingCommit):
        dg.pr_evidence(ATO, 5, tick=_tick())


# ── T8: a paging failure is incomplete and stops without retry ───────────────
def test_t8_second_page_failure_is_incomplete_and_not_retried(fakes: SimpleNamespace) -> None:
    fakes.gql_pages = [linear_page([issue("RA-1")], "c1"), RuntimeError("page 2 failed"), linear_page([])]
    read = dc.fetch_missions(API_KEY, ENTRY, tick=_tick(), since=SINCE)
    assert read.complete is False and read.reason
    assert [i["identifier"] for i in read.issues] == ["RA-1"]
    assert len(fakes.gql) == 2 and fakes.gql[1][1]["cursor"] == "c1"


# ── T10: read-only by construction ───────────────────────────────────────────
UNSAFE_QUERIES = {
    "mutation": 'mutation M { issueUpdate(id: "x", input: {}) { success } }',
    "subscription": "subscription S { issueChanged { id } }",
    "two_queries": "query A { viewer { id } } query B { viewer { id } }",
    "comment_hides_mutation": "query Q { viewer { id } }\n# }\nmutation M { issueDelete(id: \"x\") { success } }",
    "comment_first_line": "# query Q {\nmutation M { issueDelete(id: \"x\") { success } }",
    "hash_in_string": 'query Q { issue(id: "#") { id } } mutation M { issueDelete(id: "x") { success } }',
    "escaped_quote": 'query Q { issue(id: "\\"") { id } } mutation M { issueDelete(id: "x") { success } }',
    "block_string": 'query Q { issue(id: """ x """) { id } } mutation M { issueDelete(id: "x") { success } }',
    "anonymous_then_named": "{ viewer { id } } query Q { viewer { id } }",
    "named_then_anonymous": "query Q { viewer { id } } { viewer { id } }",
    "shorthand_only": "{ viewer { id } }",
    "fragment": "query Q { viewer { ...F } } fragment F on User { id }",
    "unbalanced": "query Q { viewer { id }",
    "not_text": b"query Q { viewer { id } }",
}


@pytest.mark.parametrize("name", sorted(UNSAFE_QUERIES))
def test_t10_guard_refuses_before_any_network_call(fakes: SimpleNamespace, name: str) -> None:
    fakes.gql_pages = [{"viewer": {"id": "u"}}]  # an allow-all guard returns, so the failure is DID NOT RAISE
    with pytest.raises(dc.ReadOnlyViolation):
        dc.read_only_gql(API_KEY, UNSAFE_QUERIES[name], {}, tick=_tick())
    assert len(fakes.gql_pages) == 1 and fakes.gql == [] and fakes.net == []


def test_t10_guard_allows_one_query(fakes: SimpleNamespace) -> None:
    fakes.gql_pages = [{"viewer": {"id": "u"}}]
    query = 'query Q($id: String! = "#x") { viewer { id } } # trailing comment'
    assert dc.read_only_gql(API_KEY, query, {"id": "x"}, tick=_tick()) == {"viewer": {"id": "u"}}
    assert len(fakes.gql) == 1


def test_t10_pager_goes_through_the_guard(fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    real = dc.read_only_gql

    def counting(api_key: str, query: str, variables: dict | None, *, tick: dc.Tick) -> dict:
        seen.append(query)
        return real(api_key, query, variables, tick=tick)

    monkeypatch.setattr(dc, "read_only_gql", counting)
    fakes.gql_pages = [linear_page([issue("RA-1")], "c1"), linear_page([issue("RA-2")])]
    read = dc.fetch_missions(API_KEY, ENTRY, tick=_tick(), since=SINCE)
    assert read.complete and len(seen) == len(fakes.gql) == 2


WRITE_MODULES = ("supabase", "ticket_sweeper_write", "session_linear", "ship_gate", "telegram", "slack",
                 "linear_pulse")


@pytest.mark.parametrize("module", ["delivery_collect", "delivery_collect_github", "delivery_collect_fields"])
def test_t10_import_pulls_in_no_write_helper(module: str) -> None:
    code = f"import json, sys, app.server.{module}; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    mods = json.loads(out.stdout.strip().splitlines()[-1])
    assert [m for m in mods if m.startswith("app.") and any(w in m for w in WRITE_MODULES)] == []


ALLOWED_ATTRS = {"autonomy": {"_gql"}, "ticket_sweeper_io": {"github_get"}, "vercel_monitor": {"_vercel_get"},
                 "autonomy_linear_rate": {"linear_rate_limited"}, "config_loader": {"PROJECTS_JSON"}}
STDLIB_OK = {"__future__", "json", "logging", "os", "re", "time", "dataclasses", "pathlib", "typing", "collections.abc", "datetime"}
COLLECT_NAMES = {"_REPO", "MissingCommit", "Tick", "Unknown", "_skipped"}
FIELD_NAMES = set(vars(__import__("app.server.delivery_collect_fields", fromlist=["x"])))


@pytest.mark.parametrize("module", ["delivery_collect", "delivery_collect_github", "delivery_collect_fields"])
def test_t10_collector_source_references_only_read_helpers(module: str) -> None:
    tree = ast.parse((REPO_ROOT / f"app/server/{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert {a.name for a in node.names} <= STDLIB_OK
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.module in ("delivery_collect", "delivery_collect_fields"):  # pure validators only
                assert {a.name for a in node.names} <= (FIELD_NAMES if node.module.endswith("_fields") else
                                                        COLLECT_NAMES if module == "delivery_collect_github" else set())
            elif node.level:
                assert node.module is None and {a.name for a in node.names} <= set(ALLOWED_ATTRS)
            else:
                assert node.module in STDLIB_OK
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ALLOWED_ATTRS:
            assert node.attr in ALLOWED_ATTRS[node.value.id]
        elif isinstance(node, ast.Name):
            assert node.id not in {"urlopen", "Request", "urllib", "requests", "httpx", "subprocess", "socket"}


# ── E4: the registry is read strictly ────────────────────────────────────────
@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"projects": [{"id": "x"}]}),
                                     json.dumps({"projects": "nope"})])
def test_e4_unreadable_registry_raises(tmp_path: Path, content: str | None) -> None:
    path = tmp_path / "projects.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(dc.RegistryError):
        dc.load_registry(str(path))


# ── E5: CCW-CRM is skipped on repo, any case, before any request ─────────────
def test_e5_registry_skips_ccw_by_repo_any_case(tmp_path: Path) -> None:
    reg = dc.load_registry(_registry_file(tmp_path, [ENTRY, CCW_ENTRY]))
    assert [e["id"] for e in reg.queryable] == ["ato"]
    assert reg.allowed == frozenset({"cleanexpo/ato"}) and reg.swept == (ATO,)
    assert all("ccw" not in json.dumps(e).lower() for e in reg.entries)


def test_e5_no_linear_or_github_call_for_ccw(fakes: SimpleNamespace) -> None:
    tick = _tick(allowed=ALLOWED | {"cleanexpo/ccw-crm"})
    fakes.gql_pages = [linear_page([issue("CCW-1")])]
    with pytest.raises(dc.Unknown):
        dc.fetch_missions(API_KEY, CCW_ENTRY, tick=tick, since=SINCE)
    for call in (lambda: dg.open_prs("CLEANEXPO/ccw-CRM", tick=tick), lambda: dg.pr_evidence("CleanExpo/CCW-CRM", 1, tick=tick)):
        with pytest.raises(dc.Unknown):
            call()
    assert dc.vercel_latest_ready({**CCW_ENTRY, "vercel_project_id": "p", "vercel_team_id": "t"}, tick=tick) is None
    assert dc.in_scope([("cleanexpo/Ccw-Crm", 3)], tick.allowed) == ([], 1)
    assert fakes.gql == [] and fakes.github == [] and fakes.vercel == [] and fakes.net == []


# ── E6: budgets, clock and the shared cooldown ───────────────────────────────
def test_e6_the_201st_github_get_is_not_made(fakes: SimpleNamespace) -> None:
    tick = _tick()
    for n in range(1, 42):
        fakes.gh.update(good_pr_paths(ATO, n))
    for n in range(1, 41):
        dg.pr_evidence(ATO, n, tick=tick)
    with pytest.raises(dc.BudgetExhausted):
        dg.pr_evidence(ATO, 41, tick=tick)
    assert len(fakes.github) == 200


def test_e6_the_81st_linear_request_is_not_made(fakes: SimpleNamespace) -> None:
    tick = _tick()
    fakes.gql_pages = [linear_page([issue(f"RA-{i}")], "more") for i in range(200)]  # unique: a repeat fails the read
    reasons = [dc.fetch_missions(API_KEY, ENTRY, tick=tick, since=SINCE).reason for _ in range(6)]
    assert len(fakes.gql) == 80 and reasons[-1] == "budget_linear"


def test_e6_the_5th_vercel_get_is_not_made(fakes: SimpleNamespace) -> None:
    tick = _tick()
    entry = {**ENTRY, "repo": PIDEV, "vercel_project_id": "prj_test", "vercel_team_id": "team_test"}
    for _ in range(4):
        dc.vercel_latest_ready(entry, tick=tick)
    with pytest.raises(dc.BudgetExhausted):
        dc.vercel_latest_ready(entry, tick=tick)
    assert len(fakes.vercel) == 4


def test_e6_clock_past_90s_stops_new_reads(fakes: SimpleNamespace) -> None:
    now = [1000.0]
    tick = _tick(clock=lambda: now[0])
    now[0] += 90.5
    with pytest.raises(dc.BudgetExhausted):
        dg.open_prs(ATO, tick=tick)
    fakes.gql_pages = [linear_page([])]
    assert dc.fetch_missions(API_KEY, ENTRY, tick=tick, since=SINCE).reason == "clock"
    assert fakes.github == [] and fakes.gql == []


def test_e6_cooldown_set_mid_tick_stops_the_pager_without_retry(fakes: SimpleNamespace) -> None:
    fakes.gql_pages = [linear_page([issue(f"RA-{i}")], f"c{i}") for i in range(10)]

    def trip(st: SimpleNamespace) -> None:
        if len(st.gql) == 2:
            st.limited = True

    fakes.after_gql = trip
    read = dc.fetch_missions(API_KEY, ENTRY, tick=_tick(), since=SINCE)
    assert read.complete is False and read.reason == "linear_rate_limited"
    assert len(fakes.gql) == 2


def test_e8_vercel_ready_sha_recorded_and_bad_list_is_unknown(fakes: SimpleNamespace) -> None:
    entry = {**ENTRY, "repo": PIDEV, "vercel_project_id": "prj_test"}
    fakes.vc["*"] = {"deployments": [{"state": "READY", "created": 2, "target": "production", "meta": {"githubCommitSha": SHA_A}},
                                     {"state": "ERROR", "created": 3, "meta": {"githubCommitSha": "b" * 40}}]}
    assert dc.vercel_latest_ready(entry, tick=_tick()) == SHA_A
    fakes.vc["*"] = {"deployments": [{"state": "READY", "meta": {"githubCommitSha": SHA_A}}]}
    with pytest.raises(dc.Unknown):
        dc.vercel_latest_ready(entry, tick=_tick())


# ── F1: the real registry ────────────────────────────────────────────────────
def test_f1_real_registry_scope_sets() -> None:
    reg = dc.load_registry()
    assert "oh-my-codex" in reg.unqueryable_projects
    assert len(reg.allowed) == 12 and "cleanexpo/oh-my-codex" in reg.allowed
    assert len(reg.swept) == 11 and "CleanExpo/oh-my-codex" not in reg.swept
    assert "cleanexpo/ccw-crm" not in reg.allowed and reg.skipped_repos == ("CleanExpo/CCW-CRM",)
    assert all(e["repo"].lower() != "cleanexpo/ccw-crm" for e in reg.entries)


# ── F2: links outside scope are never fetched ────────────────────────────────
def test_f2_out_of_scope_links_are_dropped_before_any_call(fakes: SimpleNamespace) -> None:
    text = "see https://github.com/CleanExpo/CCW-CRM/pull/4 and https://github.com/Other/Unregistered/pull/8"
    refs = ticket_sweeper_io.pr_refs(issue("RA-1", text))
    kept, dropped = dc.in_scope(refs, ALLOWED)
    assert kept == [] and dropped == 2 and isinstance(dropped, int)
    with pytest.raises(dc.Unknown):
        dg.pr_evidence("Other/Unregistered", 8, tick=_tick())
    assert fakes.github == [] and fakes.net == []
