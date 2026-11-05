"""RA-8174 red-main auto-owner watcher: detection, board, lanes, annotate.

The Nov 4 scorecard: CARSI main sat red 2 h 35 min with a pushed fix and no PR, five
jobs parked, and an AMBER line unowned for 8 hours. Each test below plants one of
those failures and checks the watcher catches it.
"""
from __future__ import annotations

import datetime
import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from red_main_support import REPO, RED, T0, make_ops, run  # noqa: E402
from red_main import actions, board, detect, lanes  # noqa: E402
from red_main.common import FAIL, OK, UNKNOWN  # noqa: E402

@pytest.fixture
def ops(tmp_path, monkeypatch):
    return make_ops(tmp_path, monkeypatch)


# -- detection ---------------------------------------------------------------

def test_latest_completed_run_per_workflow_decides_red():
    runs = [run(1, "CI", None, "2026-11-04T07:30:00Z", status="in_progress"),
            run(1, "CI", "failure", "2026-11-04T07:10:00Z"),
            run(1, "CI", "failure", "2026-11-04T07:00:00Z"),
            run(1, "CI", "success", "2026-11-04T06:00:00Z"),
            run(2, "Heartbeat", "failure", "2026-11-04T05:00:00Z", event="schedule"),
            run(3, "Lint", "success", "2026-11-04T07:20:00Z"),
            run(3, "Lint", "failure", "2026-11-04T06:00:00Z"),
            run(4, "PR only", "failure", "2026-11-04T07:25:00Z", event="pull_request")]
    red, why = detect.latest_failures(runs)
    assert why == ""
    assert {r["name"]: r["since"] for r in red} == {"CI": "2026-11-04T07:00:00Z", "Heartbeat": "2026-11-04T05:00:00Z"}


def test_green_after_failure_is_not_red_and_unreadable_is_unknown():
    assert detect.latest_failures([run(1, "CI", "success", "b"), run(1, "CI", "failure", "a")]) == ([], "")
    red, why = detect.latest_failures([{"workflowName": "CI"}])
    assert red is None and "not readable" in why
    red, why = detect.latest_failures([run(1, "CI", "weird", "a")])
    assert red is None and "unreadable conclusion" in why


def fake_gh(tmp_path, monkeypatch, table: dict):
    """A gh stand-in: the first table key found in the joined args selects the reply (None = empty output)."""
    data = tmp_path / "gh.json"
    data.write_text(json.dumps(table))
    script = tmp_path / "gh"
    script.write_text(f"""#!{sys.executable}
import json, sys
args = " ".join(sys.argv[1:])
for k, v in json.load(open({str(data)!r})).items():
    if k in args:
        if v is None:   # gh exits 0 and prints nothing (e.g. a repo with no workflows)
            sys.exit(0)
        if isinstance(v, dict) and "__exit" in v:
            sys.stderr.write(v.get("err", "boom") + "\\n"); sys.exit(v["__exit"])
        print(json.dumps(v)); sys.exit(0)
sys.stderr.write("HTTP 404: Not Found\\n"); sys.exit(1)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("RED_MAIN_GH", str(script))


def test_repo_state_via_gh(tmp_path, monkeypatch):
    fake_gh(tmp_path, monkeypatch, {"run list": [run(7, "CI", "failure", "2026-11-04T07:00:00Z")],
                                    "workflow list": [{"id": 7, "state": "active"}]})
    state, info = detect.repo_state(REPO, "main", {}, T0)
    assert state == FAIL and info["failing"][0]["name"] == "CI"
    fake_gh(tmp_path, monkeypatch, {"run list": [run(7, "CI", "failure", "2026-11-04T07:00:00Z")],
                                    "workflow list": [{"id": 7, "state": "disabled_manually"}]})
    assert detect.repo_state(REPO, "main", {}, T0)[0] == OK
    fake_gh(tmp_path, monkeypatch, {"run list": [run(7, "CI", "failure", "2026-11-04T07:00:00Z")],
                                    "workflow list": [{"state": "active"}]})   # review r1 P1: id missing
    state, info = detect.repo_state(REPO, "main", {}, T0)
    assert state == UNKNOWN and "not readable" in info["reason"]
    fake_gh(tmp_path, monkeypatch, {"run list": {"__exit": 1, "err": "HTTP 502"}})
    state, info = detect.repo_state(REPO, "main", {}, T0)
    assert state == UNKNOWN and "HTTP 502" in info["reason"]


def test_failing_workflow_hidden_behind_a_full_page_is_red(tmp_path, monkeypatch):
    """Review r2 P1: 100 green runs of a busy workflow hid a failing daily job and read as green."""
    page = [run(1, "CI", "success", f"2026-11-04T06:{i % 60:02d}:00Z") for i in range(100)]
    table = {"--workflow 2": [run(2, "Heartbeat", "failure", "2026-11-03T05:00:00Z", event="schedule")],
             "run list": page, "workflow list": [{"id": 1, "state": "active"}, {"id": 2, "state": "active"}]}
    fake_gh(tmp_path, monkeypatch, table)
    cache = {}
    state, info = detect.repo_state(REPO, "main", cache, T0)
    assert state == FAIL and [r["name"] for r in info["failing"]] == ["Heartbeat"]
    fake_gh(tmp_path, monkeypatch, {**table, "--workflow 2": {"__exit": 1, "err": "HTTP 502"}})
    assert detect.repo_state(REPO, "main", cache, T0)[0] == FAIL          # fresh cache answers
    later = T0 + datetime.timedelta(hours=7)
    state, info = detect.repo_state(REPO, "main", cache, later)          # stale cache, read fails
    assert state == UNKNOWN and "workflow 2" in info["reason"]


def test_stale_failures_empty_lists_and_short_pages(tmp_path, monkeypatch):
    """Review r2 follow-up: a one-shot that last failed weeks ago is history, not a red main;
    a repo with no workflows is green, not unreadable; a short run page needs no extra reads."""
    old = [run(7, "Emergency Rollback", "failure", "2026-10-01T00:00:00Z", event="workflow_dispatch")]
    fake_gh(tmp_path, monkeypatch, {"run list": old, "workflow list": [{"id": 7, "state": "active"}]})
    assert detect.repo_state(REPO, "main", {}, T0)[0] == OK
    monkeypatch.setenv("RED_MAIN_STALE_DAYS", "60")
    assert detect.repo_state(REPO, "main", {}, T0)[0] == FAIL
    fake_gh(tmp_path, monkeypatch, {"run list": [], "workflow list": None})
    assert detect.repo_state(REPO, "main", {}, T0) == (OK, {})
    fake_gh(tmp_path, monkeypatch, {"--workflow": {"__exit": 1, "err": "should not be called"},
                                    "run list": [run(1, "CI", "success", "2026-11-04T06:00:00Z")],
                                    "workflow list": [{"id": 1, "state": "active"}, {"id": 2, "state": "active"}]})
    assert detect.repo_state(REPO, "main", {}, T0)[0] == OK


def test_repo_list_filters_stale_and_archived(tmp_path, monkeypatch):
    fake_gh(tmp_path, monkeypatch, {"repo list": [
        {"nameWithOwner": "CleanExpo/A", "defaultBranchRef": {"name": "main"}, "pushedAt": "2026-11-01T00:00:00Z"},
        {"nameWithOwner": "CleanExpo/Old", "defaultBranchRef": {"name": "main"}, "pushedAt": "2026-01-01T00:00:00Z"},
        {"nameWithOwner": "CleanExpo/Empty", "defaultBranchRef": None, "pushedAt": "2026-11-01T00:00:00Z"}]})
    monkeypatch.delenv("RED_MAIN_REPOS", raising=False)
    assert detect.list_repos(T0) == ([("CleanExpo/A", "main")], "")


# -- board -------------------------------------------------------------------

def test_red_opens_one_card_green_closes_and_resumes_parked():
    d = {"jobs": [{"id": "GP-629", "status": "doing"}, {"id": "GP-634", "status": "todo"}]}
    assert board.reconcile(d, {REPO: RED}, T0)
    assert board.park(d, "GP-629", REPO, T0) and board.park(d, "GP-634", "CARSI", T0)
    assert not board.reconcile(d, {REPO: RED}, T0)          # same episode: no second card
    assert len([j for j in d["jobs"] if j["id"] == "W-MAIN-RED-CARSI"]) == 1
    board.reconcile(d, {REPO: (UNKNOWN, {"reason": "502"})}, T0)
    by = {j["id"]: j for j in d["jobs"]}
    assert by["W-MAIN-RED-CARSI"]["status"] == "open" and by["GP-629"]["status"] == "parked"
    assert board.reconcile(d, {REPO: (OK, {})}, T0)
    assert by["W-MAIN-RED-CARSI"]["status"] == "done"
    assert by["GP-629"]["status"] == "doing" and by["GP-634"]["status"] == "todo"
    assert "waits_for_main" not in by["GP-629"]


def test_claim_needs_linear_id_and_a_live_card():
    d = {"jobs": []}
    assert not board.claim(d, REPO, "GP-687", "claude on Mini", T0)
    board.reconcile(d, {REPO: RED}, T0)
    assert not board.claim(d, REPO, " ", "claude on Mini", T0)
    assert board.claim(d, REPO, "GP-687", "claude on Mini", T0)
    card = d["jobs"][0]
    assert card["status"] == "doing" and card["linear"] == "GP-687" and card["owner"] == "claude on Mini"


# -- lanes -------------------------------------------------------------------

def test_pick_least_busy_eligible_host():
    assert lanes.pick([("mini", "local", 3), ("macbook", "macbook", 1)]) == ("macbook", "macbook")
    assert lanes.pick([("mini", "local", 1), ("macbook", "macbook", 1)]) == ("mini", "local")
    assert lanes.pick([("mini", "local", None), ("macbook", "macbook", 5)]) == ("macbook", "macbook")
    assert lanes.pick([("mini", "local", None)]) is None


@pytest.mark.parametrize("lane,launches,alive,pushed,want", [
    (None, 0, False, None, "launch"),
    (None, 2, False, None, "exhausted"),
    ({"dir": "x"}, 1, True, None, "wait"),
    ({"dir": "x"}, 1, True, 9, "wait"),
    ({"dir": "x"}, 1, True, 10, "flag-no-pr"),
    ({"dir": "x"}, 1, False, 3, "relaunch-pr"),
    ({"dir": "x"}, 1, False, None, "relaunch"),
    ({"dir": "x"}, 2, False, 30, "exhausted"),
])
def test_decide(lane, launches, alive, pushed, want):
    assert actions.decide({"lane": lane, "launches": launches}, alive, pushed, 10) == want


def test_launch_writes_lane_and_starts_template(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "agent-work" / "lib").mkdir(parents=True)
    tpl = home / "agent-work" / "lib" / "run-template.sh"
    tpl.write_text('#!/bin/bash\nJ="$(cd "$(dirname "$0")" && pwd)"\nmkdir -p "$HOME/agent-work/status"\n'
                   'echo started > "$J/started"\n'
                   'printf "state=finished\\n" > "$HOME/agent-work/status/$(basename "$J").status"\n')
    tpl.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    assert lanes.busy("local") is not None
    ok, where = lanes.launch("local", "red-main-carsi-202611041700-1", "fix the red main brief text")
    assert ok and where.endswith("red-main-carsi-202611041700-1")
    assert (Path(where) / "brief.md").read_text() == "fix the red main brief text"
    for _ in range(100):
        if (Path(where) / "started").exists() and lanes.lane_state("local", where) == "finished":
            break
        import time
        time.sleep(0.05)
    assert lanes.lane_state("local", where) == "finished"
    assert lanes.launch("local", "red-main-carsi-202611041700-1", "again")[0] is False   # never twice
    assert lanes.launch("local", "bad name;rm", "x")[0] is False


def test_brief_carries_gates_and_reaches_board_from_any_host():
    from red_main import brief
    card = {"id": "W-MAIN-RED-CARSI", "repo": REPO, "fix_branch": "fix/red-main-1", "failing": []}
    local, remote = brief.build(card), brief.build(card, pr_only=True, on_board_host=False)
    for text in (local, remote):
        assert "NEVER" in text and "CodeRabbit is rate-limited" in text and "Codex review" in text
        assert "fix/red-main-1" in text and "10 minutes" in text
    assert "ssh mini" not in local and 'ssh mini "python3' in remote and remote.startswith("Red-main follow-up")
