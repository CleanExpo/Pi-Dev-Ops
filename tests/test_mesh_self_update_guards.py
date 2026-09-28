"""tests/test_mesh_self_update_guards.py — shapes self-update must never move (RA-7798).

#810 made runtimes follow origin/main. These are the guards ten review rounds on the
parallel RA-7798 branch found necessary and #810 lacks: a runtime on a branch, with
local edits, or with an agent the runner could not stop is left alone, and a
concurrent fetch or checkout during the update cannot redirect it. REAL git repos.
"""
from __future__ import annotations

import subprocess
import sys
import types

import pytest

from test_mesh_self_update import REPO_ROOT, commit_preflight, git, origin_and_runtime, su

sys.path.insert(0, str(REPO_ROOT / "mesh"))
import left_running  # noqa: E402

_REAL_RUN = subprocess.run


@pytest.fixture(autouse=True)
def _private_record(tmp_path, monkeypatch):
    monkeypatch.setattr(left_running, "PATH", tmp_path / "left-running.json")
    monkeypatch.setattr(left_running, "_UNRECORDED", [False])


def _with_new_code(tmp_path):
    origin, runtime, old = origin_and_runtime(tmp_path)
    new = commit_preflight(origin, 0, "ok")
    return origin, runtime, old, new


def _sleeper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def test_a_runtime_on_a_branch_is_never_moved(tmp_path):
    _, runtime, old, _ = _with_new_code(tmp_path)
    git(runtime, "checkout", "-q", "-b", "someones-work", old)
    assert su.Updater(runtime, "claude").try_update().startswith("update refused: runtime is on a branch")
    assert git(runtime, "symbolic-ref", "--short", "HEAD") == "someones-work"


def test_local_edits_block_the_move(tmp_path):
    _, runtime, old, _ = _with_new_code(tmp_path)
    (runtime / "mesh" / "preflight.py").write_text("# edited on this node\n")
    assert su.Updater(runtime, "claude").try_update().startswith("update refused: runtime has local edits")
    assert git(runtime, "rev-parse", "HEAD") == old


def test_an_agent_left_running_blocks_the_move(tmp_path):
    _, runtime, old, _ = _with_new_code(tmp_path)
    child = _sleeper()
    try:
        left_running.track(types.SimpleNamespace(reaped=False, proc=child))
        assert "could not stop" in su.Updater(runtime, "claude").try_update()
        assert git(runtime, "rev-parse", "HEAD") == old
    finally:
        child.kill()
        child.wait()
    assert su.Updater(runtime, "claude").try_update() == "updated"  # gone: the move goes ahead


def _racing(runtime, after_fetch):
    def run(cmd, *a, **k):
        result = _REAL_RUN(cmd, *a, **k)
        if cmd[:1] == ["git"] and "fetch" in cmd:
            after_fetch()
        return result
    return run


def test_a_concurrent_fetch_of_another_branch_cannot_redirect_the_move(tmp_path):
    origin, runtime, old, new = _with_new_code(tmp_path)
    git(origin, "checkout", "-q", "-b", "other", old)
    other = commit_preflight(origin, 0, "ok")
    git(origin, "checkout", "-q", "main")
    run = _racing(runtime, lambda: _REAL_RUN(["git", "-C", str(runtime), "fetch", "-q", "origin", "other"]))
    assert su.Updater(runtime, "claude", run=run).try_update() == "updated"
    assert git(runtime, "rev-parse", "HEAD") == new != other


def test_a_branch_checked_out_during_the_fetch_is_not_detached(tmp_path):
    _, runtime, old, _ = _with_new_code(tmp_path)
    run = _racing(runtime, lambda: _REAL_RUN(["git", "-C", str(runtime), "checkout", "-q", "-b", "operator", old]))
    assert su.Updater(runtime, "claude", run=run).try_update().startswith("update refused")
    assert git(runtime, "symbolic-ref", "--short", "HEAD") == "operator"


def test_the_record_outlives_the_runner_process():
    child = _sleeper()
    try:
        left_running.track(types.SimpleNamespace(reaped=False, proc=child))
        probe = _REAL_RUN(
            [sys.executable, "-c", "import left_running, pathlib, sys; "
             "left_running.PATH = pathlib.Path(sys.argv[1]); print(left_running.any_alive())",
             str(left_running.PATH)], cwd=REPO_ROOT / "mesh", capture_output=True, text=True, check=True)
        assert probe.stdout.strip() == "True"
    finally:
        child.kill()
        child.wait()
    assert left_running.any_alive() is False
    assert left_running.PATH.read_text() == "[]"  # the dead entry is pruned


def test_unknown_counts_as_running(tmp_path, monkeypatch):
    left_running.PATH.write_text("{not json")
    assert left_running.any_alive() is True
    left_running.PATH.write_text('[{"pid": 0}]')  # no handle: cannot prove it exited
    assert left_running.any_alive() is True
    blocker = tmp_path / "a-file"
    blocker.write_text("")
    monkeypatch.setattr(left_running, "PATH", blocker / "left.json")  # unwritable location
    assert left_running.any_alive() is True
    left_running.track(types.SimpleNamespace(reaped=False, proc=None))  # must not raise
    assert left_running._UNRECORDED[0] is True


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


def test_a_plan_agent_left_running_after_a_wait_error_is_tracked(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))
    from mesh_helpers import load_module
    plan_lane = load_module("mesh_plan_lane_guard", "mesh/plan_lane.py")
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


def test_a_detached_head_move_during_the_fetch_is_not_overwritten(tmp_path):
    origin, runtime, old, _ = _with_new_code(tmp_path)
    middle = git(origin, "rev-parse", "HEAD~0")
    newest = commit_preflight(origin, 0, "ok")
    _REAL_RUN(["git", "-C", str(runtime), "fetch", "-q", "origin"], check=True)
    run = _racing(runtime, lambda: _REAL_RUN(["git", "-C", str(runtime), "checkout", "-q", "--detach", middle]))
    assert su.Updater(runtime, "claude", run=run).try_update() == "update refused: HEAD moved during the update"
    assert git(runtime, "rev-parse", "HEAD") == middle != newest != old


def test_a_dangling_or_oversized_record_counts_as_running(tmp_path):
    left_running.PATH.symlink_to(tmp_path / "missing-target.json")  # present, unreadable
    assert left_running.any_alive() is True
    left_running.PATH.unlink()
    left_running.PATH.write_text('[{"pid": 999999999999999999999999999999}]')  # no C long holds it
    assert left_running.any_alive() is True
    assert left_running._alive(999999999999999999999999999999) is True  # itself, not only via any_alive


def test_the_plan_error_handler_never_raises(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(REPO_ROOT / "mesh"))
    from mesh_helpers import load_module
    plan_lane = load_module("mesh_plan_lane_guard_poll", "mesh/plan_lane.py")

    class Proc:
        def poll(self):
            raise OSError("poll failed")

    monkeypatch.setattr(plan_lane.subprocess, "Popen", lambda *a, **k: Proc())
    tracked: list = []

    def wait_fails(proc, plan):
        raise OSError("wait failed")

    rt = types.SimpleNamespace(AGENT_CMD="claude", _wait_for_agent=wait_fails,
                               left_running=types.SimpleNamespace(track=tracked.append))
    assert plan_lane._run_agent({"linear_id": "UNI-P", "title": "t"}, {}, rt) == ""
    assert len(tracked) == 1  # cannot tell whether it runs: recorded as left running
