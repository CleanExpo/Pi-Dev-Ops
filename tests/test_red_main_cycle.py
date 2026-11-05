"""RA-8174 red-main watcher: whole cycles and the owner+age annotator.

Plants the Nov 4 failures (second lane for one red main, a pushed fix with no PR,
lanes that end with main still red, an UNKNOWN read that closes or resumes, an
AMBER line nobody owns) and checks each one is caught.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import pytest

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from red_main_support import RED, REPO, T0, jobs, make_ops  # noqa: E402
from red_main import actions, annotate, board, detect, lanes, store, watch  # noqa: E402
from red_main.common import OK, TS, UNKNOWN  # noqa: E402


@pytest.fixture
def ops(tmp_path, monkeypatch):
    return make_ops(tmp_path, monkeypatch)


# -- one cycle end to end (GitHub and hosts stubbed) ---------------------------

@pytest.fixture
def world(ops, monkeypatch):
    """A red CARSI, two hosts (Mini busier), a lane that can be killed, and a fix branch."""
    w = {"state": RED, "busy": {"local": 2, "macbook": 0}, "launched": [], "lane": "running", "pushed": None}
    monkeypatch.setenv("RED_MAIN_LAUNCH", "1")
    monkeypatch.setenv("RED_MAIN_HOSTS", "mini=local,macbook=macbook")
    monkeypatch.setattr(detect, "list_repos", lambda at: ([(REPO, "main")], ""))
    monkeypatch.setattr(detect, "repo_state", lambda repo, branch, *rest: w["state"])
    monkeypatch.setattr(lanes, "busy", lambda via: w["busy"][via])
    monkeypatch.setattr(lanes, "lane_state", lambda via, d: w["lane"])
    monkeypatch.setattr(actions, "pushed_without_pr", lambda repo, fix, at: (w["pushed"], ""))

    def launch(via, name, text):
        w["launched"].append((via, name, text))
        return True, f"/home/agent-work/{name}"
    monkeypatch.setattr(lanes, "launch", launch)
    return w


def at(minutes):
    return (T0 + datetime.timedelta(minutes=minutes)).strftime(TS)


def test_cycle_one_owner_one_lane_on_least_busy(world, ops, monkeypatch):
    monkeypatch.setenv("RED_MAIN_NOW", at(0))
    watch.cycle()
    card = jobs(ops)["W-MAIN-RED-CARSI"]
    assert [v for v, _, _ in world["launched"]] == ["macbook"]
    assert card["owner"].startswith("red-main lane on macbook") and card["launches"] == 1
    assert "CleanExpo/CARSI" in world["launched"][0][2] and "NEVER" in world["launched"][0][2]
    monkeypatch.setenv("RED_MAIN_NOW", at(5))
    watch.cycle()
    assert len(world["launched"]) == 1                     # lane alive: no second lane


def test_pushed_fix_without_pr(world, ops, monkeypatch):
    monkeypatch.setenv("RED_MAIN_NOW", at(0))
    watch.cycle()
    world["pushed"] = 11
    monkeypatch.setenv("RED_MAIN_NOW", at(20))
    watch.cycle()
    assert "no PR" in jobs(ops)["W-MAIN-RED-CARSI"]["pr_overdue"] and len(world["launched"]) == 1
    world["lane"] = "finished"
    monkeypatch.setenv("RED_MAIN_NOW", at(25))
    watch.cycle()
    assert len(world["launched"]) == 2 and "has no PR" in world["launched"][1][2]
    assert "pr_overdue" not in jobs(ops)["W-MAIN-RED-CARSI"]


def test_exhausted_lanes_go_unowned_then_escalate(world, ops, monkeypatch):
    world["lane"] = "finished"
    for minute in (0, 5, 10):
        monkeypatch.setenv("RED_MAIN_NOW", at(minute))
        watch.cycle()
    card = jobs(ops)["W-MAIN-RED-CARSI"]
    assert len(world["launched"]) == 2 and card["owner"] is None and not card.get("escalated")
    monkeypatch.setenv("RED_MAIN_NOW", at(40))
    watch.cycle()
    card = jobs(ops)["W-MAIN-RED-CARSI"]
    assert card["escalated"] and card["priority"] == "P0" and "UNOWNED" in card["blocker"]


def test_unknown_read_neither_closes_nor_resumes(world, ops, monkeypatch):
    monkeypatch.setenv("RED_MAIN_NOW", at(0))
    watch.cycle()
    store.update_jobs(lambda d: d["jobs"].append({"id": "GP-677", "status": "todo"}) or True)
    store.update_jobs(lambda d: board.park(d, "GP-677", REPO, T0))
    world["state"] = (UNKNOWN, {"reason": "gh exit 1: HTTP 502"})
    watch.cycle()
    assert jobs(ops)["W-MAIN-RED-CARSI"]["status"] != "done" and jobs(ops)["GP-677"]["status"] == "parked"
    world["state"] = (OK, {})
    watch.cycle()
    assert jobs(ops)["W-MAIN-RED-CARSI"]["status"] == "done" and jobs(ops)["GP-677"]["status"] == "todo"


def test_launch_off_by_default(world, ops, monkeypatch):
    monkeypatch.delenv("RED_MAIN_LAUNCH")
    monkeypatch.setenv("RED_MAIN_NOW", at(0))
    watch.cycle()
    assert world["launched"] == [] and "RED_MAIN_LAUNCH is off" in jobs(ops)["W-MAIN-RED-CARSI"]["note"]


# -- annotate: owner + age, 30 min escalation -----------------------------------

def test_annotate_owner_age_and_escalation(ops):
    d = json.loads(ops.read_text())
    board.reconcile(d, {REPO: RED}, T0)
    lines = ["# Facts", "OK Mini runner", "AMBER queue: runners idle for 40 min"]
    out, seen, changed = annotate.annotate(lines, d, {}, T0)
    assert out[0].startswith("RED CleanExpo/CARSI main") and "[owner: NONE; age:" in out[0]
    assert out[-1].endswith("[owner: NONE; age: 0m]") and not changed
    later = T0 + datetime.timedelta(minutes=31)
    out, seen, changed = annotate.annotate(["AMBER queue: runners idle for 71 min"], d, seen, later)
    assert changed and "age: 31m" in out[-1] and "escalated to board W-WATCH-" in out[-1]
    card = next(j for j in d["jobs"] if j["id"].startswith("W-WATCH-"))
    card["claimed_by"] = "codex on MacBook"
    out, seen, _ = annotate.annotate(["AMBER queue: runners idle for 80 min"], d, seen, later)
    assert "[owner: codex on MacBook; age: 31m]" in out[-1]
    annotate.annotate([], d, seen, later)
    assert card["status"] == "open"                         # an empty read never closes
    annotate.annotate(["OK all good"], d, seen, later)
    assert card["status"] == "open"                         # no end marker: a partial read never closes
    annotate.annotate(["OK all good", annotate.END_MARKER], d, seen, later)
    assert card["status"] == "done"


def test_partial_read_keeps_other_watch_cards_and_their_age(ops):
    """Review r1 P1: a truncated stream with only line A closed B's card."""
    d = {"jobs": []}
    a, b = "RED runner A down", "AMBER runner B idle"
    _, seen, _ = annotate.annotate([a, b], d, {}, T0)
    later = T0 + datetime.timedelta(minutes=31)
    _, seen, _ = annotate.annotate([a, b, annotate.END_MARKER], d, seen, later)
    assert sum(1 for j in d["jobs"] if j["status"] == "open") == 2
    _, seen2, _ = annotate.annotate([a], d, seen, later)
    assert sum(1 for j in d["jobs"] if j["status"] == "open") == 2
    assert seen2[annotate.key(b)] == seen[annotate.key(b)]


def test_retry_with_annotated_output_keeps_cards(ops):
    """Review r3 P1: feeding annotated output back in closed the line's live W-WATCH card."""
    d = json.loads(ops.read_text())
    board.reconcile(d, {REPO: RED}, T0)
    later = T0 + datetime.timedelta(minutes=31)
    first = ["AMBER runner idle", annotate.END_MARKER]
    out, seen, _ = annotate.annotate(first, d, {annotate.key("AMBER runner idle"): annotate.stamp(T0)}, later)
    card = next(j for j in d["jobs"] if j["id"].startswith("W-WATCH-"))
    again, seen2, _ = annotate.annotate(out, d, seen, later)
    assert card["status"] == "open" and seen2 == seen
    assert sum(1 for x in again if x.startswith("RED CleanExpo/CARSI")) == 1   # own line not doubled
    assert sum(1 for x in again if x.startswith("AMBER runner idle [owner:")) == 1
    assert not any(j["id"].startswith("W-WATCH-") and j is not card for j in d["jobs"])


def test_cli_annotate_park_claim(ops, monkeypatch, capsys):
    import red_main_watch as cli
    store.update_jobs(lambda d: d["jobs"].append({"id": "GP-675", "status": "doing"}) or True)
    store.update_jobs(lambda d: board.reconcile(d, {REPO: RED}, T0))
    assert cli.main(["x", "park", "GP-675", REPO]) == 0
    assert cli.main(["x", "claim", REPO, "GP-687", "claude on Mini"]) == 0
    assert jobs(ops)["GP-675"]["waits_for_main"] == REPO
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("RED PC runner down\n"))
    assert cli.main(["x", "annotate"]) == 0
    out = capsys.readouterr().out
    assert "[owner: claude on Mini" in out and "RED PC runner down [owner: NONE; age: 0m]" in out
    assert cli.main(["x", "nope"]) == 2
    assert os.path.exists(os.path.join(os.environ["RED_MAIN_STATE_DIR"], "red-main-annotate.json"))


def test_new_lanes_per_cycle_are_capped_newest_red_first(world, ops, monkeypatch):
    reds = {f"CleanExpo/R{i}": (RED[0], {**RED[1], "since": f"2026-11-0{i}T00:00:00Z"}) for i in (1, 2, 3)}
    monkeypatch.setattr(detect, "list_repos", lambda at: ([(r, "main") for r in reds], ""))
    monkeypatch.setattr(detect, "repo_state", lambda repo, branch, *rest: reds[repo])
    monkeypatch.setenv("RED_MAIN_NOW", at(0))
    watch.cycle()
    assert [n.split("-")[2] for _, n, _ in world["launched"]] == ["r3", "r2"]
    assert jobs(ops)["W-MAIN-RED-R1"]["owner"] is None
    monkeypatch.setenv("RED_MAIN_NOW", at(5))
    watch.cycle()
    assert [n.split("-")[2] for _, n, _ in world["launched"]] == ["r3", "r2", "r1"]
