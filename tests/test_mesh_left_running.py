"""tests/test_mesh_left_running.py — an agent a runner could not stop blocks self-update (RA-7798).

The record lives in a file so it outlives the runner process: a relaunched runner
must still see an agent its predecessor left running. Split from
test_mesh_self_update.py, whose helpers it reuses.
"""
from __future__ import annotations

import subprocess
import sys

from test_mesh_self_update import (  # noqa: F401  (autouse fixture is re-exported for this module)
    REPO_ROOT, _Stop, _fleet, _git, _private_left_running_file, _runner_with, left_running, load_module, su,
)


def test_a_plan_agent_left_running_after_a_wait_error_is_tracked(tmp_path, monkeypatch):
    import types
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))  # plan_lane imports its siblings, as runner.py sets up
    plan_lane = load_module("mesh_plan_lane_under_test", "mesh/plan_lane.py")
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexec sleep 30\n")
    agent.chmod(0o755)
    tracked: list = []

    def wait_fails(proc, plan):
        raise OSError("wait failed")

    rt = types.SimpleNamespace(AGENT_CMD=str(agent), _wait_for_agent=wait_fails,
                               left_running=types.SimpleNamespace(track=tracked.append))
    try:
        assert plan_lane._run_agent({"linear_id": "UNI-P", "title": "t"}, {}, rt) == ""
        assert len(tracked) == 1 and tracked[0].proc.poll() is None
    finally:
        for rec in tracked:
            rec.proc.kill()
            rec.proc.wait()


def test_an_agent_left_running_blocks_update_even_when_the_fleet_reads_zero(monkeypatch, tmp_path):
    """The idle breadcrumb can erase the fleet's view of an unreaped agent, so the
    runner's own record of it must block the restart."""
    runner = _runner_with(monkeypatch, tmp_path, 0)
    skips: list = []
    monkeypatch.setattr(runner.left_running, "any_alive", lambda: True)

    def idle(*a, skip=False, **k):
        skips.append(skip)
        raise _Stop

    monkeypatch.setattr(runner.self_update, "idle_tick", idle)
    monkeypatch.setattr(runner.self_update, "update_now", lambda host, may_move=None: False)
    try:
        runner.main()
    except _Stop:
        pass
    assert skips == [True]


def test_a_tracked_agent_counts_until_its_process_exits():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        left_running.track(type("Rec", (), {"reaped": False, "proc": child})())
        assert left_running.any_alive() is True
    finally:
        child.kill()
        child.wait()
    assert left_running.any_alive() is False
    assert left_running.PATH.read_text() == "[]"  # the dead entry is pruned
    left_running.track(type("Rec", (), {"reaped": True, "proc": None})())  # reaped agents are not tracked
    assert left_running.any_alive() is False


def test_the_record_outlives_the_runner_process(tmp_path):
    """A second process (a relaunched runner) must see an agent the first one left running."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        left_running.track(type("Rec", (), {"reaped": False, "proc": child})())
        probe = subprocess.run(
            [sys.executable, "-c", "import left_running, pathlib, sys; "
             "left_running.PATH = pathlib.Path(sys.argv[1]); print(left_running.any_alive())",
             str(left_running.PATH)],
            cwd=REPO_ROOT / "mesh", capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == "True"
    finally:
        child.kill()
        child.wait()


def test_an_unreadable_or_handle_less_record_blocks(tmp_path):
    left_running.PATH.write_text("{not json")
    assert left_running.any_alive() is True
    left_running.PATH.write_text('[{"pid": 0}]')  # no handle: cannot prove it exited
    assert left_running.any_alive() is True


def test_a_live_record_blocks_the_move_itself(tmp_path):
    _, runtime, old, _ = _fleet(tmp_path)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        left_running.track(type("Rec", (), {"reaped": False, "proc": child})())
        su._last_check[0] = float("-inf")
        orig = su.RUNTIME
        su.RUNTIME = runtime
        try:
            assert su.update_now("node", lambda: True) is False
        finally:
            su.RUNTIME = orig
        assert _git(runtime, "rev-parse", "HEAD") == old
    finally:
        child.kill()
        child.wait()


def test_every_claim_hands_its_run_record_to_the_tracker(monkeypatch, tmp_path):
    from test_mesh_run_record_claim import _runner as _claim_runner

    runner, _calls, _removed, repo = _claim_runner(monkeypatch, tmp_path)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexit 0\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))
    tracked: list = []
    monkeypatch.setattr(runner.left_running, "track", tracked.append)
    runner.run_claim({"linear_id": "UNI-T", "repo_dir": str(repo)}, dry_run=False)
    assert len(tracked) == 1 and tracked[0] is not None
