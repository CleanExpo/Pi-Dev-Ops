"""tests/test_mesh_quota_hold.py — a node out of Claude quota holds, and costs no ticket (RA-7930).

On 06/10 the Mini's account hit its weekly limit: `claude -p` printed `You've hit your
weekly limit · resets Oct 9 at 1am (Australia/Brisbane)` and exited 1, and the runner kept
claiming tickets it could not build. These pin:
  * `quota_reset` reads the limit wordings and their reset times; an unreadable reset
    holds for the default and checks again; anything else is not a quota message;
  * preflight and a build run both turn the message into a `quota` hold;
  * while held the node claims nothing; at the reset preflight runs again;
  * a claim lost to quota is released, never counted toward FAILURE_LIMIT;
  * the breadcrumb, the heartbeat and the server watchdog all say `quota`.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "mesh"))

from mesh_helpers import Break, load_module  # noqa: E402

import heartbeat  # noqa: E402
import node_health  # noqa: E402
import quota  # noqa: E402
from app.server import cron_watchdog_mesh as wd  # noqa: E402

BNE = ZoneInfo("Australia/Brisbane")
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=BNE).timestamp()
WEEKLY = "You've hit your weekly limit · resets Oct 9 at 1am (Australia/Brisbane)"


def _at(*args) -> float:
    return datetime(*args, tzinfo=BNE).timestamp()


# ── the parser ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected", [
    (WEEKLY, _at(2026, 10, 9, 1, 0)),
    ("Claude usage limit reached. Your limit will reset at 5pm (Australia/Brisbane).", _at(2026, 10, 6, 17, 0)),
    ("5-hour limit reached ∙ resets 3:30pm (Australia/Brisbane)", _at(2026, 10, 6, 15, 30)),
    ("You've hit your usage limit · resets 11am (Australia/Brisbane)", _at(2026, 10, 7, 11, 0)),  # 11am passed
    ("You've hit your session limit · resets 13:45 (Australia/Brisbane)", _at(2026, 10, 6, 13, 45)),
    ("Claude AI usage limit reached|1791000000", 1791000000.0),
])
def test_the_limit_wordings_and_their_reset_times_are_read(text, expected):
    assert quota.quota_reset(text, NOW) == expected


@pytest.mark.parametrize("text", [
    "You've hit your weekly limit",                                    # no reset at all
    "You've hit your weekly limit · resets Feb 30 at 1am (Australia/Brisbane)",  # no such day
    "Claude usage limit reached. Your limit will reset at 25pm",        # no such hour
    "You've hit your weekly limit · resets Oct 1 at 1am (Australia/Brisbane)",  # misread: >8 days away
])
def test_an_unreadable_reset_holds_for_the_default_and_checks_again(text):
    assert quota.quota_reset(text, NOW) == NOW + quota.DEFAULT_HOLD_S


def test_a_reset_after_new_year_rolls_into_next_year():
    now = _at(2026, 12, 30, 9, 0)
    assert quota.quota_reset("weekly limit reached · resets Jan 2 at 1am (Australia/Brisbane)", now) \
        == datetime(2027, 1, 2, 1, 0, tzinfo=BNE).timestamp()


@pytest.mark.parametrize("text", ["", "All 41 tests passed", "agent exited 1: no commits", None])
def test_other_output_is_not_a_quota_message(text):
    assert quota.quota_reset(text, NOW) is None


def test_the_hold_reason_names_the_reset_and_reads_back():
    until = _at(2026, 10, 9, 1, 0)
    reason = quota.problem(until)
    assert reason.startswith("Claude quota exhausted until 2026-10-")
    assert quota.held_until(reason) == until
    assert quota.held_until("agent could not write a file") is None


# ── preflight ────────────────────────────────────────────────────────────────

def _agent_says(stdout: str, code: int = 1):
    def run(cmd, cwd=None, **kwargs):
        if cmd[0] == "git" and cmd[4] == "add":
            Path(cmd[6]).mkdir(parents=True)
        elif cmd[0] == "claude":
            return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return run


def test_preflight_names_an_exhausted_quota_and_its_reset(monkeypatch):
    pf = load_module("mesh_preflight_quota", "mesh/preflight.py")
    # The sample reset is 9 Oct 2026 01:00 Brisbane. After that moment a live
    # clock no longer parses it as that reset, so the test keeps the 6 Oct clock.
    monkeypatch.setattr(pf.time, "time", lambda: NOW)
    problem = pf.agent_writes(Path("/repo"), "claude", run=_agent_says(WEEKLY))
    assert quota.held_until(problem) == _at(2026, 10, 9, 1, 0), problem
    # control: any other non-zero exit is still the plain exit
    assert pf.agent_writes(Path("/repo"), "claude", run=_agent_says("boom")) == "agent exited 1"


# ── NodeHealth ───────────────────────────────────────────────────────────────

class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_a_quota_preflight_holds_until_the_reset_then_preflight_runs_again():
    wall, until, calls = Clock(NOW), NOW + 7200, []
    answers = [quota.problem(until), ""]

    def preflight():
        calls.append(1)
        return answers[len(calls) - 1]

    health = node_health.NodeHealth(preflight, clock=Clock(), recheck=600, wall=wall)
    assert health.may_claim() is False
    assert (health.state, health.quota_until) == ("quota", until)
    wall.now = until - 1
    assert health.may_claim() is False and len(calls) == 1   # held: preflight not re-run
    wall.now = until
    assert health.may_claim() is True and health.state == "healthy" and len(calls) == 2


def test_a_claim_lost_to_quota_holds_and_never_counts_as_a_failure():
    health = node_health.NodeHealth(lambda: "", clock=Clock(), limit=2, wall=Clock(NOW))
    assert health.may_claim()
    health.record([{"state": "failed", "error_code": "agent_exit"}])
    for _ in range(3):
        health.record([{"state": "released", "error_code": "agent_quota", "quota_until": NOW + 60}])
    assert (health.state, health.failures) == ("quota", 1)
    assert health.reason == quota.problem(NOW + 60)


def test_a_quota_hold_hands_back_the_rest_of_the_batch():
    health = node_health.NodeHealth(lambda: "", clock=Clock(), wall=Clock(NOW))
    health.may_claim()
    released = []
    results = health.run_batch([{"linear_id": "RA-1"}, {"linear_id": "RA-2"}],
                               lambda c: {"state": "released", "quota_until": NOW + 60}, released.append)
    assert len(results) == 1 and released == [{"linear_id": "RA-2"}]


# ── a build run ──────────────────────────────────────────────────────────────

def _rec(tmp_path, transcript: str, code: int):
    log = tmp_path / "run.log"
    log.write_text(transcript)
    return types.SimpleNamespace(path=log, proc=types.SimpleNamespace(returncode=code))


def test_a_build_that_failed_on_quota_is_released_not_failed(tmp_path):
    rr = load_module("mesh_run_record_quota", "mesh/run_record.py")
    plan = {"state": "failed", "error": "agent exited 1"}
    quota.release_if_quota([_rec(tmp_path, "working...\n" + WEEKLY + "\n", 1)], plan, NOW)
    assert plan["quota_until"] == _at(2026, 10, 9, 1, 0)
    assert rr.terminal(None, plan) == {"state": "released", "error_code": "agent_quota"}


@pytest.mark.parametrize("transcript, code, state", [
    ("Error: tests failed", 1, "failed"),   # an ordinary failure stays one
    (WEEKLY, 0, "done"),                    # a run that succeeded is left alone
])
def test_other_runs_are_left_as_they_ended(tmp_path, transcript, code, state):
    plan = {"state": state}
    quota.release_if_quota([_rec(tmp_path, transcript, code)], plan, NOW)
    assert plan == {"state": state}


# ── the runner loop ──────────────────────────────────────────────────────────

@pytest.fixture
def runner(monkeypatch, tmp_path):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = load_module("mesh_runner_quota", "mesh/runner.py")
    monkeypatch.setattr(mod, "PREFLIGHT_ENABLED", True)
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "active_agent_count", lambda *a, **k: 0)
    mod.claims = []
    monkeypatch.setattr(mod, "get_work", lambda: mod.claims.append(1) or [{"linear_id": "RA-1"}])

    def sleep(secs):
        if secs == mod.POLL_INTERVAL:
            raise Break()
    monkeypatch.setattr(mod.time, "sleep", sleep)
    monkeypatch.setattr(sys, "argv", ["runner"])
    return mod


def test_a_node_out_of_quota_claims_nothing_and_its_breadcrumb_says_why(runner, monkeypatch, capsys):
    reason = quota.problem(NOW + 3600 * 24 * 365)
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: reason)
    with pytest.raises(Break):
        runner.main()
    assert runner.claims == []
    crumb = json.loads(runner.STATE_FILE.read_text())
    assert (crumb["state"], crumb["hold_reason"]) == ("quota", reason)
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (line["status"], line["hold_reason"]) == ("QUOTA", reason)
    assert heartbeat.node_status([], crumb) == "quota"


def test_quota_lost_claims_never_quarantine_the_node(runner, monkeypatch):
    monkeypatch.setattr(runner.preflight, "check", lambda repo, agent: "")
    monkeypatch.setattr(runner, "run_claim", lambda claim, dry_run: {
        "linear_id": claim["linear_id"], "state": "released", "error_code": "agent_quota",
        "quota_until": NOW + 3600 * 24 * 365})
    with pytest.raises(Break):
        runner.main()
    assert runner.claims == [1]       # one claim, then held: not FAILURE_LIMIT, not 25
    assert json.loads(runner.STATE_FILE.read_text())["state"] == "quota"


# ── the server watchdog ──────────────────────────────────────────────────────

def test_the_watchdog_pages_a_node_out_of_quota(monkeypatch):
    wd._filed.clear()
    wd._active.clear()
    paged = []
    monkeypatch.setattr(wd, "_telegram", lambda k, m, lg, severity="high": paged.append((k, m)))
    monkeypatch.setattr(wd, "_ticket", lambda k, m, lg: wd._filed.add(k))
    seen = datetime.fromtimestamp(NOW - 20, tz=timezone.utc).isoformat()
    rows = [{"host": "Phills-Mac-mini", "status": "quota", "last_seen": seen}]
    found = wd.run(lambda path: (200, json.dumps(rows)), NOW, logging.getLogger("test"))
    assert list(found) == ["quota:Phills-Mac-mini"]
    assert paged[0][1].startswith("Phills-Mac-mini: Claude quota exhausted")
