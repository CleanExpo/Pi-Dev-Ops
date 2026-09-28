"""tests/test_mesh_runner_ship_wiring.py — how `run_claim` drives `mesh/ship_run.py`
(RA-7780).

The shipping itself is proven against real git in
tests/test_mesh_runner_ships_own_work.py. This file pins the runner's side: a run
lands `done` only after a ship, the start commit is read once and BEFORE the agent,
and a failure to read it can never strand the claim in `working`. Split out when the
real-git file reached the 300-line convention.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import ImmediateProc  # noqa: E402
from mesh_helpers import load_module  # noqa: E402


@pytest.fixture
def runner(monkeypatch, tmp_path):
    """The runner with side effects neutralised; each test decides what ship returns."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    mod = load_module("mesh_runner_ships", "mesh/runner.py")
    monkeypatch.setattr(mod, "HOST", "TESTNODE")
    monkeypatch.setattr(mod, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(mod, "HARD_STOP", tmp_path / "HARD_STOP")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: None)
    return mod


def _claim(runner, tmp_path):
    repo = tmp_path / "checkout"
    (repo / ".git").mkdir(parents=True)
    return runner.run_claim({"linear_id": "UNI-A", "repo_dir": str(repo)}, dry_run=False)


def _run(runner, monkeypatch, tmp_path, ship_result):
    """Run one claim with the agent stubbed to exit 0. Every start_point() read gets a
    fresh value and every step lands in `events`, so a re-read after the agent shows."""
    reported, events = [], []

    def _read_start(repo_dir):
        events.append(f"start-read-{sum(e.startswith('start-read') for e in events) + 1}")
        return events[-1]

    def _agent(*a, **k):
        events.append("agent")
        return ImmediateProc()

    runner._api = lambda m, p, b=None: reported.append((b or {}).get("state")) or {}
    monkeypatch.setattr(runner.subprocess, "Popen", _agent)
    monkeypatch.setattr(runner.ship_run, "start_point", _read_start)
    monkeypatch.setattr(runner.ship_run, "ship",
                        lambda start, *a: events.append(f"ship:{start}") or ship_result)
    plan = _claim(runner, tmp_path)
    return plan, [s for s in reported if s], events


def test_run_claim_reports_failed_when_nothing_shipped(runner, monkeypatch, tmp_path):
    plan, reported, _ = _run(runner, monkeypatch, tmp_path, "no commits: agent changed nothing")

    assert plan["state"] == "failed"
    assert "no commits" in plan["error"]
    assert reported == ["working", "failed"]


def test_run_claim_reports_done_only_after_a_ship(runner, monkeypatch, tmp_path):
    """GREEN CONTROL: a fix that failed every run would pass the test above."""
    plan, reported, _ = _run(runner, monkeypatch, tmp_path, None)

    assert plan["state"] == "done", plan
    assert reported == ["working", "done"]


def test_run_claim_ships_from_the_start_it_read_before_the_agent(runner, monkeypatch, tmp_path):
    """Codex review round 4, P0: a constant stub let a re-read AFTER the agent pass.
    The start must be read exactly once, before the agent, and that read is shipped."""
    _plan, _reported, events = _run(runner, monkeypatch, tmp_path, None)

    assert events == ["start-read-1", "agent", "ship:start-read-1"]


def test_a_hung_start_read_reports_failed_instead_of_stranding_the_claim(runner, monkeypatch,
                                                                       tmp_path):
    """Codex review round 5, P1: start_point() runs before run_claim's try/finally, so
    a git timeout there escaped with the claim left `working`, which locks the ticket
    away from every other node. It must degrade to an unproven start, which ships
    nothing and reports `failed`."""
    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=120)

    reported = []
    runner._api = lambda m, p, b=None: reported.append((b or {}).get("state")) or {}
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: ImmediateProc())
    monkeypatch.setattr(runner.ship_run, "_git", _hang)

    plan = _claim(runner, tmp_path)

    assert plan["state"] == "failed"
    assert [s for s in reported if s] == ["working", "failed"]
