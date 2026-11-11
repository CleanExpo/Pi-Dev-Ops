#!/usr/bin/env python3
"""Tests for guardian-watcher.py. Offline: a local http.server on 127.0.0.1, a stub gh script, a temp ops dir,
HOME is a temp dir. Run: python3 test_guardian_watcher.py"""
import datetime, http.server, importlib.util, json, os, shlex, shutil, socket, sys, tempfile, threading, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
sys.dont_write_bytecode = True
_n = [0]
PAGES = {}   # path -> (status, body); anything absent is 200 with a stripe link
SRV = []

GH_STUB = """import json, os, sys, time
a = sys.argv[1:]
log = os.environ.get("GH_STUB_LOG")
if log:
    open(log, "a").write(" ".join(a) + "\\n")
mode = os.environ.get("GH_STUB_MODE", "ok")
if mode == "exit1":
    sys.stderr.write("gh: authentication required\\nrun gh auth login\\n"); sys.exit(1)
if mode == "hang":
    time.sleep(30)
if mode == "garbage":
    print("<html>not json</html>"); sys.exit(0)
repo = a[a.index("--repo") + 1] if "--repo" in a else a[a.index("-R") + 1]
if a[:2] == ["pr", "list"]:
    print(json.dumps(json.loads(os.environ.get("GH_STUB_PRS", "{}")).get(repo, [])))
elif a[:2] == ["pr", "view"]:
    print(json.dumps(json.loads(os.environ.get("GH_STUB_VIEW", "{}")).get(repo + "#" + a[2], {"state": "OPEN", "statusCheckRollup": []})))
else:
    sys.exit(2)
"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        s, body = PAGES.get(self.path, (200, "<a href='https://buy.stripe.com/x'>buy</a>"))
        self.send_response(s); self.end_headers(); self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


def server():
    if not SRV:
        s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=s.serve_forever, daemon=True).start()
        SRV.append(s)
    return "http://127.0.0.1:%d" % SRV[0].server_address[1]


def dead_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return "http://127.0.0.1:%d" % p


def silent_server():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(5)
    return s, "http://127.0.0.1:%d" % s.getsockname()[1]


def load(tmp, **over):
    ops = os.path.join(tmp, "ops")
    os.makedirs(ops, exist_ok=True)
    if not os.path.exists(os.path.join(ops, "jobs.json")):
        json.dump({"jobs": [], "updated": ""}, open(os.path.join(ops, "jobs.json"), "w"))
    stub = os.path.join(tmp, "gh-stub")
    if not os.path.exists(stub):
        # A shell wrapper, not a `#!<python>` line: a shebang cannot hold a path with a space, and the
        # CI mirror's venv lives under "/Volumes/Mini Mini 2T Storage" (every stub call failed there).
        open(stub + ".py", "w").write(GH_STUB)
        open(stub, "w").write('#!/bin/sh\nexec %s %s "$@"\n' % (shlex.quote(sys.executable), shlex.quote(stub + ".py")))
        os.chmod(stub, 0o755)
    env = {"HOME": os.path.join(tmp, "home"), "GUARDIAN_OPS": ops, "GUARDIAN_GH": stub,
           "GUARDIAN_HEARTBEAT": os.path.join(tmp, "hb"), "GUARDIAN_STATE": os.path.join(tmp, "gstate.json"),
           "GUARDIAN_HTTP_TIMEOUT": "2", "GUARDIAN_GH_TIMEOUT": "5",
           "GUARDIAN_UG_BASE": server() + "/ug", "GUARDIAN_SYNTHEX_BASE": server() + "/sx",
           "GUARDIAN_REPOS": "CleanExpo/Unite-Group,CleanExpo/Synthex", "GH_STUB_MODE": "ok",
           "GH_STUB_LOG": os.path.join(tmp, "gh.log")}
    env.update({k: str(v) for k, v in over.items()})
    os.environ.update(env)
    _n[0] += 1
    spec = importlib.util.spec_from_file_location("guardian_%d" % _n[0], os.path.join(SCRIPTS, "guardian-watcher.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.OPS == ops, "env seam GUARDIAN_OPS not honoured - refusing to run against the real board"
    return mod


def rows(tmp):
    return {j["id"]: j for j in json.load(open(os.path.join(tmp, "ops", "jobs.json")))["jobs"]}


def test_all_ok_raises_nothing_and_writes_heartbeat(tmp):
    PAGES.clear()
    mod = load(tmp)
    mod.main()
    assert rows(tmp) == {}
    assert open(os.path.join(tmp, "hb")).read().strip()


def test_http_500_is_fail(tmp):
    PAGES.clear(); PAGES["/ug/"] = (500, "boom")
    mod = load(tmp)
    mod.main()
    r = rows(tmp)["W-SITE-UG"]
    assert r["status"] == "open" and r["check_state"] == "FAIL", r
    assert "/ug/" in r["blocker"] and "HTTP 500" in r["blocker"], r["blocker"]


def test_missing_expected_content_is_fail(tmp):
    PAGES.clear(); PAGES["/ug/grow"] = (200, "no links here")
    mod = load(tmp)
    mod.main()
    assert rows(tmp)["W-STRIPE-GROW-LINKS"]["check_state"] == "FAIL"


def test_an_unreadable_page_makes_its_stripe_row_unknown_not_a_stale_ok(tmp):
    # review 26/10 r9: a timeout or non-2xx on /grow or /cards emitted no W-STRIPE row, so a
    # done/OK row stayed OK while nobody could see the page. Seed OK, then each unreadable case.
    for stripe, path in (("W-STRIPE-GROW-LINKS", "/ug/grow"), ("W-STRIPE-CARD-LINKS", "/ug/cards")):
        for unreadable in ({"page": (503, "")}, {"dead": True}):
            PAGES.clear(); PAGES[path] = (200, "no links here")
            load(tmp).main()
            PAGES.clear()
            load(tmp).main()
            assert rows(tmp)[stripe]["status"] == "done", rows(tmp)[stripe]
            if "page" in unreadable:
                PAGES[path] = unreadable["page"]
                load(tmp).main()
            else:
                load(tmp, GUARDIAN_UG_BASE=dead_port()).main()
            row = rows(tmp)[stripe]
            assert row["check_state"] == "UNKNOWN", (stripe, unreadable, row)


def test_an_unreadable_page_keeps_an_open_stripe_fail(tmp):
    PAGES.clear(); PAGES["/ug/grow"] = (200, "no links here")
    load(tmp).main()
    PAGES["/ug/grow"] = (503, "")
    load(tmp).main()
    row = rows(tmp)["W-STRIPE-GROW-LINKS"]
    assert row["status"] == "open" and row["check_state"] == "FAIL", row


def test_connection_refused_is_unknown_not_site_down(tmp):
    PAGES.clear()
    mod = load(tmp, GUARDIAN_UG_BASE=dead_port())
    mod.main()
    r = rows(tmp)["W-SITE-UG"]
    assert r["check_state"] == "UNKNOWN" and r["unknown_since"], r
    assert "HTTP" not in r["blocker"] and "refused" in r["blocker"].lower(), r["blocker"]


def test_timeout_is_unknown(tmp):
    PAGES.clear()
    s, base = silent_server()
    try:
        mod = load(tmp, GUARDIAN_UG_BASE=base, GUARDIAN_HTTP_TIMEOUT="1")
        mod.main()
    finally:
        s.close()
    r = rows(tmp)["W-SITE-UG"]
    assert r["check_state"] == "UNKNOWN" and base in r["blocker"], r


def test_unknown_after_fail_keeps_the_fail_row(tmp):
    PAGES.clear(); PAGES["/ug/"] = (500, "boom")
    load(tmp).main()
    before = rows(tmp)["W-SITE-UG"]
    assert before["check_state"] == "FAIL"
    load(tmp, GUARDIAN_UG_BASE=dead_port()).main()
    after = rows(tmp)["W-SITE-UG"]
    assert after["status"] == "open" and after["check_state"] == "FAIL", after
    assert "HTTP 500" in after["blocker"], after["blocker"]


def test_recovery_resets_a_fail_row_to_done(tmp):
    PAGES.clear(); PAGES["/ug/"] = (500, "boom")
    load(tmp).main()
    PAGES.clear()
    load(tmp).main()
    r = rows(tmp)["W-SITE-UG"]
    assert r["status"] == "done" and r["last_known_good_at"], r


def test_unknown_older_than_30_minutes_escalates_message(tmp):
    PAGES.clear()
    dead = dead_port()
    load(tmp, GUARDIAN_UG_BASE=dead).main()
    fresh = rows(tmp)["W-SITE-UG"]
    assert not fresh["blocker"].startswith("check could not run"), fresh["blocker"]
    path = os.path.join(tmp, "ops", "jobs.json")
    d = json.load(open(path))
    old = (datetime.datetime.now().astimezone() - datetime.timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M%z")
    for j in d["jobs"]:
        if j["id"] == "W-SITE-UG":
            j["unknown_since"] = old
    json.dump(d, open(path, "w"))
    load(tmp, GUARDIAN_UG_BASE=dead).main()
    r = rows(tmp)["W-SITE-UG"]
    assert r["blocker"].startswith("check could not run:") and dead in r["blocker"], r["blocker"]
    assert r["unknown_since"] == old and r["priority"] == "P1", r


def test_unknown_row_remembers_last_known_good(tmp):
    PAGES.clear()
    load(tmp).main()
    load(tmp, GUARDIAN_UG_BASE=dead_port()).main()
    assert rows(tmp)["W-SITE-UG"]["last_known_good_at"], rows(tmp)["W-SITE-UG"]


def test_pr_list_comes_from_gh_not_hard_coded_numbers(tmp):
    PAGES.clear()
    prs = {"CleanExpo/Unite-Group": [{"number": 4242, "headRefOid": "a" * 40}],
           "CleanExpo/Synthex": [{"number": 7, "headRefOid": "b" * 40}]}
    view = {"CleanExpo/Unite-Group#4242": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]},
            "CleanExpo/Synthex#7": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "ok", "conclusion": "SUCCESS", "status": "COMPLETED"}]}}
    mod = load(tmp, GH_STUB_PRS=json.dumps(prs), GH_STUB_VIEW=json.dumps(view))
    mod.main()
    r = rows(tmp)
    bad = [j for j in r.values() if "4242" in j["id"]]
    assert len(bad) == 1 and bad[0]["check_state"] == "FAIL" and "unit" in bad[0]["blocker"], r
    assert not [j for j in r.values() if j["id"].endswith("-7")], r
    log = open(os.path.join(tmp, "gh.log")).read()
    assert "1271" not in log and "1086" not in log and "4242" in log, log


def test_closed_pr_row_is_marked_done_when_list_succeeds(tmp):
    PAGES.clear()
    prs = {"CleanExpo/Unite-Group": [{"number": 4242, "headRefOid": "a" * 40}]}
    view = {"CleanExpo/Unite-Group#4242": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]}}
    load(tmp, GH_STUB_PRS=json.dumps(prs), GH_STUB_VIEW=json.dumps(view)).main()
    load(tmp, GH_STUB_PRS="{}").main()
    assert [j["status"] for j in rows(tmp).values() if "4242" in j["id"]] == ["done"]


def _open_fail_4242(tmp):
    prs = {"CleanExpo/Unite-Group": [{"number": 4242, "headRefOid": "a" * 40}]}
    view = {"CleanExpo/Unite-Group#4242": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]}}
    load(tmp, GH_STUB_PRS=json.dumps(prs), GH_STUB_VIEW=json.dumps(view)).main()
    assert [j["check_state"] for j in rows(tmp).values() if "4242" in j["id"]] == ["FAIL"]


def test_partially_unparsable_pr_list_does_not_close_open_rows(tmp):
    PAGES.clear()
    _open_fail_4242(tmp)
    load(tmp, GH_STUB_PRS=json.dumps({"CleanExpo/Unite-Group": [{"number": "unparseable"}]})).main()
    r = rows(tmp)
    row = r["W-PR-Unite-Group-4242"]
    assert row["status"] == "open" and row["check_state"] == "FAIL", row
    assert r["W-PR-LIST-Unite-Group"]["check_state"] == "UNKNOWN", r


def test_a_list_that_reaches_the_limit_does_not_close_open_rows(tmp):
    # review 26/10: gh pr list returns at most --limit rows (30 by default). A full page is not
    # proof that a missing PR closed, so it must not sweep.
    PAGES.clear()
    _open_fail_4242(tmp)
    prs = {"CleanExpo/Unite-Group": [{"number": n, "headRefOid": "d" * 40} for n in (1, 2, 3)]}
    m = load(tmp, GH_STUB_PRS=json.dumps(prs))
    m.PR_LIMIT = 3
    m.main()
    r = rows(tmp)
    row = r["W-PR-Unite-Group-4242"]
    assert row["status"] == "open" and row["check_state"] == "FAIL", row
    assert r["W-PR-LIST-Unite-Group"]["check_state"] == "UNKNOWN", r
    log = open(os.path.join(tmp, "gh.log")).read()
    assert "--limit 3" in log, log


def test_mixed_good_and_unparsable_entries_do_not_sweep(tmp):
    PAGES.clear()
    _open_fail_4242(tmp)
    prs = {"CleanExpo/Unite-Group": [{"number": 9, "headRefOid": "c" * 40}, "garbage", {"number": True}]}
    load(tmp, GH_STUB_PRS=json.dumps(prs)).main()
    assert rows(tmp)["W-PR-Unite-Group-4242"]["status"] == "open"


def test_a_non_positive_or_repeated_pr_number_does_not_close_open_rows(tmp):
    # review 26/10 r8: number 0 or -1 passed the int check, so a list holding only that entry
    # swept and closed the open FAIL row for 4242. A PR number is a positive int, listed once.
    for bad in ([{"number": 0, "headRefOid": "e" * 40}], [{"number": -1, "headRefOid": "e" * 40}],
                [{"number": 9, "headRefOid": "e" * 40}, {"number": 9, "headRefOid": "e" * 40}]):
        PAGES.clear()
        _open_fail_4242(tmp)
        load(tmp, GH_STUB_PRS=json.dumps({"CleanExpo/Unite-Group": bad})).main()
        r = rows(tmp)
        row = r["W-PR-Unite-Group-4242"]
        assert row["status"] == "open" and row["check_state"] == "FAIL", (bad, row)
        assert r["W-PR-LIST-Unite-Group"]["check_state"] == "UNKNOWN", (bad, r)


def test_gh_exit_1_is_unknown_with_stderr_line(tmp):
    PAGES.clear()
    load(tmp, GH_STUB_MODE="exit1").main()
    unk = [j for j in rows(tmp).values() if j["id"].startswith("W-PR")]
    assert unk and all(j["check_state"] == "UNKNOWN" for j in unk), rows(tmp)
    assert all("authentication required" in j["blocker"] and "run gh auth login" not in j["blocker"] for j in unk)


def test_gh_timeout_is_unknown(tmp):
    PAGES.clear()
    load(tmp, GH_STUB_MODE="hang", GUARDIAN_GH_TIMEOUT="1").main()
    unk = [j for j in rows(tmp).values() if j["id"].startswith("W-PR")]
    assert unk and all(j["check_state"] == "UNKNOWN" and "timed out" in j["blocker"] for j in unk), rows(tmp)


def test_gh_unparsable_output_is_unknown(tmp):
    PAGES.clear()
    load(tmp, GH_STUB_MODE="garbage").main()
    unk = [j for j in rows(tmp).values() if j["id"].startswith("W-PR")]
    assert unk and all(j["check_state"] == "UNKNOWN" for j in unk), rows(tmp)


def test_missing_gh_binary_is_unknown(tmp):
    PAGES.clear()
    load(tmp, GUARDIAN_GH=os.path.join(tmp, "no-such-gh")).main()
    unk = [j for j in rows(tmp).values() if j["id"].startswith("W-PR")]
    assert unk and all(j["check_state"] == "UNKNOWN" for j in unk), rows(tmp)


def _one_pr_views(tmp, rollup_a, **over):
    """Unite-Group#11 gets `rollup_a`; Synthex#7 is a valid failing PR that must still be evaluated."""
    prs = {"CleanExpo/Unite-Group": [{"number": 11, "headRefOid": "a" * 40}],
           "CleanExpo/Synthex": [{"number": 7, "headRefOid": "b" * 40}]}
    view = {"CleanExpo/Unite-Group#11": {"state": "OPEN", "statusCheckRollup": rollup_a},
            "CleanExpo/Synthex#7": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]}}
    return load(tmp, GH_STUB_PRS=json.dumps(prs), GH_STUB_VIEW=json.dumps(view), **over)


def _assert_malformed_isolated(tmp):
    r = rows(tmp)
    assert r["W-PR-Unite-Group-11"]["check_state"] == "UNKNOWN", r
    assert "statusCheckRollup" in r["W-PR-Unite-Group-11"]["blocker"], r["W-PR-Unite-Group-11"]
    assert r["W-PR-Synthex-7"]["check_state"] == "FAIL", r
    assert open(os.path.join(tmp, "hb")).read().strip()


def test_malformed_rollup_entry_is_unknown_and_run_continues(tmp):
    PAGES.clear()
    _one_pr_views(tmp, ["malformed"]).main()
    _assert_malformed_isolated(tmp)


def test_rollup_dict_or_non_list_is_unknown(tmp):
    for bad in ({"name": "x", "conclusion": "FAILURE"}, "text", 5):
        PAGES.clear()
        d = tempfile.mkdtemp(prefix="guardian-test-", dir=tmp)
        _one_pr_views(d, bad).main()
        _assert_malformed_isolated(d)


def test_rollup_entry_missing_keys_is_unknown(tmp):
    # review 26/10 r4: an entry with no recognisable check fields used to read as "no failures",
    # which could close an existing FAIL row. A check we cannot read proves nothing.
    for bad in ([{}], [{"name": "x"}], [{"conclusion": "SUCCESS"}], [{"name": "x", "conclusion": "WEIRD"}],
                [{"context": "ci"}], [{"context": "ci", "state": "MAYBE"}],
                # review r5: no type tag, or a tag that does not match the fields, is unreadable
                [{"name": "x", "conclusion": "SUCCESS"}],
                [{"__typename": "StatusContext", "name": "x", "conclusion": "SUCCESS"}],
                [{"__typename": "Thing", "context": "ci", "state": "SUCCESS"}],
                # review r6: a completed run with no conclusion, a running one with a conclusion, an
                # unknown status, and a row carrying the other type's fields
                [{"__typename": "CheckRun", "name": "x", "status": "COMPLETED", "conclusion": None}],
                [{"__typename": "CheckRun", "name": "x", "status": "IN_PROGRESS", "conclusion": "SUCCESS"}],
                [{"__typename": "CheckRun", "name": "x", "status": "DONE", "conclusion": "SUCCESS"}],
                [{"__typename": "CheckRun", "name": "x", "status": "COMPLETED", "conclusion": "SUCCESS",
                  "context": "Vercel", "state": "FAILURE"}],
                [{"__typename": "StatusContext", "context": "Vercel", "state": "SUCCESS", "conclusion": "FAILURE"}]):
        PAGES.clear()
        d = tempfile.mkdtemp(prefix="guardian-test-", dir=tmp)
        _one_pr_views(d, bad).main()
        _assert_malformed_isolated(d)


def test_a_hybrid_failing_status_row_never_closes_a_fail(tmp):
    # review r5: a StatusContext whose state is FAILURE but which also carries a passing CheckRun
    # name/conclusion read as a pass and closed an open FAIL row.
    PAGES.clear()
    _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]).main()
    first = rows(tmp)["W-PR-Unite-Group-11"]
    assert first["check_state"] == "FAIL" and first["status"] != "done", first
    PAGES.clear()
    _one_pr_views(tmp, [{"__typename": "StatusContext", "context": "Vercel", "state": "FAILURE",
                         "name": "unit", "conclusion": "SUCCESS"}]).main()
    row = rows(tmp)["W-PR-Unite-Group-11"]
    assert row["check_state"] == "FAIL" and row["status"] != "done", row
    for bad in ({"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": None},
                {"__typename": "CheckRun", "name": "unit", "status": "COMPLETED", "conclusion": "SUCCESS",
                 "context": "Vercel", "state": "FAILURE"}):
        PAGES.clear()
        _one_pr_views(tmp, [bad]).main()
        row = rows(tmp)["W-PR-Unite-Group-11"]
        assert row["status"] != "done" and row["check_state"] != "OK", (bad, row)


def test_a_failing_status_context_is_a_fail(tmp):
    # gh reports commit statuses (Vercel, CodeRabbit, nexus/release-receipt) as StatusContext with
    # `context` and `state`, not `name` and `conclusion`. A failed one must raise the PR row.
    PAGES.clear()
    _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "SUCCESS", "status": "COMPLETED"},
                        {"__typename": "StatusContext", "context": "Vercel", "state": "FAILURE"}]).main()
    r = rows(tmp)
    assert r["W-PR-Unite-Group-11"]["check_state"] == "FAIL" and "Vercel" in r["W-PR-Unite-Group-11"]["title"], r


def test_passing_checks_are_ok(tmp):
    PAGES.clear()
    _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "SUCCESS", "status": "COMPLETED"},
                        {"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS"}]).main()
    r = rows(tmp)
    assert "W-PR-Unite-Group-11" not in r or r["W-PR-Unite-Group-11"]["check_state"] == "OK", r
    assert r["W-PR-Synthex-7"]["check_state"] == "FAIL", r


def test_unfinished_checks_never_close_an_open_fail(tmp):
    # review 26/10 r10: a running check (CheckRun IN_PROGRESS with no conclusion, or a PENDING
    # status) read as OK and closed the open FAIL row before anything had passed.
    passing = {"__typename": "CheckRun", "name": "unit", "conclusion": "SUCCESS", "status": "COMPLETED"}
    for running in ({"__typename": "CheckRun", "name": "e2e", "conclusion": None, "status": "IN_PROGRESS"},
                    {"__typename": "CheckRun", "name": "e2e", "conclusion": None, "status": "QUEUED"},
                    {"__typename": "StatusContext", "context": "nexus/release-receipt", "state": "PENDING"},
                    {"__typename": "StatusContext", "context": "nexus/release-receipt", "state": "EXPECTED"},
                    # review 26/10 r12: STALE is a final conclusion but not a pass
                    {"__typename": "CheckRun", "name": "e2e", "conclusion": "STALE", "status": "COMPLETED"}):
        PAGES.clear()
        _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]).main()
        assert rows(tmp)["W-PR-Unite-Group-11"]["check_state"] == "FAIL"
        _one_pr_views(tmp, [passing, running]).main()
        row = rows(tmp)["W-PR-Unite-Group-11"]
        assert row["status"] == "open" and row["check_state"] == "FAIL", (running, row)
        _one_pr_views(tmp, [passing]).main()
        assert rows(tmp)["W-PR-Unite-Group-11"]["status"] == "done", running
    # review 26/10 r11: a PR with no checks reported (statusCheckRollup null or empty) proves nothing either
    for nothing in (None, []):
        PAGES.clear()
        _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"}]).main()
        _one_pr_views(tmp, nothing).main()
        row = rows(tmp)["W-PR-Unite-Group-11"]
        assert row["status"] == "open" and row["check_state"] == "FAIL", (nothing, row)
        _one_pr_views(tmp, [passing]).main()
        assert rows(tmp)["W-PR-Unite-Group-11"]["status"] == "done", nothing
    # a running check next to a completed failure is still a FAIL
    _one_pr_views(tmp, [{"__typename": "CheckRun", "name": "unit", "conclusion": "FAILURE", "status": "COMPLETED"},
                        {"__typename": "CheckRun", "name": "e2e", "conclusion": None, "status": "IN_PROGRESS"}]).main()
    assert rows(tmp)["W-PR-Unite-Group-11"]["check_state"] == "FAIL"


def test_missing_head_ref_oid_is_handled(tmp):
    PAGES.clear()
    prs = {"CleanExpo/Unite-Group": [{"number": 11}]}
    view = {"CleanExpo/Unite-Group#11": {"state": "OPEN", "statusCheckRollup": [{"__typename": "CheckRun", "name": "u", "conclusion": "FAILURE", "status": "COMPLETED"}]}}
    load(tmp, GH_STUB_PRS=json.dumps(prs), GH_STUB_VIEW=json.dumps(view)).main()
    assert rows(tmp)["W-PR-Unite-Group-11"]["check_state"] == "FAIL"
    assert open(os.path.join(tmp, "hb")).read().strip()


def test_raising_repo_family_does_not_close_open_rows(tmp):
    PAGES.clear()
    _open_fail_4242(tmp)
    mod = load(tmp, GH_STUB_PRS=json.dumps({"CleanExpo/Unite-Group": [{"number": 9}]}))
    real = mod.cli_json
    def boom(*a):
        if a[:2] == ("pr", "view"):
            raise RuntimeError("kaboom")
        return real(*a)
    mod.cli_json = boom
    mod.main()
    assert rows(tmp)["W-PR-Unite-Group-4242"]["status"] == "open", rows(tmp)


def test_a_raising_check_family_is_unknown_and_the_rest_completes(tmp):
    PAGES.clear()
    mod = _one_pr_views(tmp, [])
    real = mod.cli_json
    def boom(*a):
        if "CleanExpo/Unite-Group" in a:
            raise RuntimeError("kaboom")
        return real(*a)
    mod.cli_json = boom
    mod.main()
    r = rows(tmp)
    assert r["W-PR-LIST-Unite-Group"]["check_state"] == "UNKNOWN" and "kaboom" in r["W-PR-LIST-Unite-Group"]["blocker"], r
    assert r["W-PR-Synthex-7"]["check_state"] == "FAIL", r
    assert open(os.path.join(tmp, "hb")).read().strip()


def test_a_raising_site_family_is_unknown_and_the_rest_completes(tmp):
    PAGES.clear()
    mod = _one_pr_views(tmp, [])
    real = mod.get
    def boom(url):
        if url.endswith("/ug/grow"):
            raise RuntimeError("kaboom")
        return real(url)
    mod.get = boom
    mod.main()
    r = rows(tmp)
    assert r["W-SITE-GROW"]["check_state"] == "UNKNOWN" and "kaboom" in r["W-SITE-GROW"]["blocker"], r
    assert r["W-PR-Synthex-7"]["check_state"] == "FAIL", r
    assert open(os.path.join(tmp, "hb")).read().strip()


def main():
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    env, failed = dict(os.environ), 0
    for name, fn in tests:
        tmp = tempfile.mkdtemp(prefix="guardian-test-")
        try:
            fn(tmp)
            print("PASS " + name)
        except BaseException:  # noqa: BLE001
            failed += 1
            print("FAIL %s\n%s" % (name, traceback.format_exc()))
        finally:
            os.environ.clear(); os.environ.update(env)
            shutil.rmtree(tmp, ignore_errors=True)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
