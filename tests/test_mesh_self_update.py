"""tests/test_mesh_self_update.py — a node's runtime follows origin/main (RA-7798).

After #800 merged, all three runners kept running older code until each was
moved by hand. `fast_forward` moves a clean, detached runtime to origin/main and
refuses every other shape; `idle_tick` turns a move into a restart.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mesh_helpers import load_module  # noqa: E402

su = load_module("mesh_self_update_under_test", "mesh/self_update.py")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    _git(repo, "add", name)
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", name)
    return _git(repo, "rev-parse", "HEAD")


def _fleet(tmp_path: Path):
    """origin with two commits on main; a runtime clone detached at the first."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    old = _commit(origin, "a")
    runtime = tmp_path / "runtime"
    subprocess.run(["git", "clone", "-q", str(origin), str(runtime)], check=True)
    _git(runtime, "checkout", "-q", "--detach", old)
    new = _commit(origin, "b")
    return origin, runtime, old, new


def test_clean_detached_runtime_moves_to_origin_main(tmp_path):
    _, runtime, _, new = _fleet(tmp_path)
    assert su.fast_forward(runtime) == new
    assert _git(runtime, "rev-parse", "HEAD") == new


def test_up_to_date_runtime_does_not_move(tmp_path):
    _, runtime, _, new = _fleet(tmp_path)
    _git(runtime, "fetch", "-q", "origin")
    _git(runtime, "checkout", "-q", "--detach", new)
    assert su.fast_forward(runtime) is None


def test_checkout_on_a_branch_is_never_moved(tmp_path):
    _, runtime, old, _ = _fleet(tmp_path)
    _git(runtime, "checkout", "-q", "-b", "someones-work", old)
    assert su.fast_forward(runtime) is None
    assert _git(runtime, "rev-parse", "HEAD") == old


def test_local_edits_block_the_move(tmp_path):
    _, runtime, old, _ = _fleet(tmp_path)
    (runtime / "a").write_text("edited")
    assert su.fast_forward(runtime) is None
    assert _git(runtime, "rev-parse", "HEAD") == old


_REAL_GIT = su._git


def _failing(command: str):
    def git(root, *args):
        if args[:1] == (command,):
            return subprocess.CompletedProcess(args, 128, "", "fatal: injected")
        return _REAL_GIT(root, *args)
    return git


def test_a_failed_guard_check_blocks_the_move(tmp_path, monkeypatch):
    """A guard that errored proved nothing, so the runtime stays put."""
    _, runtime, old, _ = _fleet(tmp_path)
    for command in ("status", "symbolic-ref"):
        monkeypatch.setattr(su, "_git", _failing(command))
        assert su.fast_forward(runtime) is None, command
        assert _git(runtime, "rev-parse", "HEAD") == old


def test_an_edit_made_during_the_fetch_blocks_the_move(tmp_path, monkeypatch):
    _, runtime, old, _ = _fleet(tmp_path)

    def edit_while_fetching(root, *args):
        if args[:1] == ("fetch",):
            (runtime / "a").write_text("edited mid-fetch")
        return _REAL_GIT(root, *args)

    monkeypatch.setattr(su, "_git", edit_while_fetching)
    assert su.fast_forward(runtime) is None
    assert _git(runtime, "rev-parse", "HEAD") == old


def test_a_veto_blocks_the_move_and_is_asked_only_when_one_is_due(tmp_path):
    _, runtime, old, new = _fleet(tmp_path)
    asked: list = []
    assert su.fast_forward(runtime, lambda: asked.append(1) or False) is None
    assert _git(runtime, "rev-parse", "HEAD") == old and asked == [1]
    assert su.fast_forward(runtime, lambda: True) == new
    asked.clear()
    assert su.fast_forward(runtime, lambda: asked.append(1) or True) is None  # up to date
    assert asked == []


def test_diverged_head_is_not_moved(tmp_path):
    _, runtime, _, _ = _fleet(tmp_path)
    mine = _commit(runtime, "local-only")
    _git(runtime, "checkout", "-q", "--detach", mine)
    assert su.fast_forward(runtime) is None
    assert _git(runtime, "rev-parse", "HEAD") == mine


def test_idle_tick_restarts_only_after_a_move(monkeypatch):
    states: list = []
    monkeypatch.setattr(su.time, "sleep", lambda s: None)
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root, may_move=None: "abc123")
    assert su.idle_tick(lambda *a: states.append(a), 1, "node") is True
    assert states == [(None, "idle")]
    assert su.idle_tick(lambda *a: None, 1, "node") is False  # inside the interval
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root, may_move=None: None)
    assert su.idle_tick(lambda *a: None, 1, "node") is False


def test_a_relaunched_runner_updates_before_it_claims(monkeypatch, tmp_path):
    """After a MAX_CLAIMS stop the next launch must not claim on stale code."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    runner = load_module("mesh_runner_startup_update", "mesh/runner.py")
    claimed: list = []
    monkeypatch.setattr(runner, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(runner, "get_work", lambda: claimed.append(1) or [])
    monkeypatch.setattr(runner, "active_agent_count", lambda api, host: 0)
    monkeypatch.setattr(runner.self_update, "update_now", lambda host, may_move=None: True)
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert runner.main() == runner.self_update.RESTART_EXIT
    assert claimed == []


def _runner_with(monkeypatch, tmp_path, agents):
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    runner = load_module("mesh_runner_agent_guard", "mesh/runner.py")
    monkeypatch.setattr(runner, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(runner, "get_work", lambda: [])
    monkeypatch.setattr(runner, "active_agent_count", lambda api, host: agents)
    monkeypatch.setattr(sys, "argv", ["runner"])
    return runner


class _Stop(Exception):
    pass


def test_no_update_while_an_agent_of_ours_may_still_run(monkeypatch, tmp_path):
    """An agent the runner could not stop keeps its claim; exiting would orphan it."""
    for agents in (1, None):  # running, or the fleet could not be read
        runner = _runner_with(monkeypatch, tmp_path, agents)
        startup: list = []
        skips: list = []

        def update_now(host, may_move=None):
            startup.append(may_move())
            return False

        monkeypatch.setattr(runner.self_update, "update_now", update_now)

        def idle(*a, skip=False, **k):
            skips.append(skip)
            raise _Stop

        monkeypatch.setattr(runner.self_update, "idle_tick", idle)
        try:
            runner.main()
        except _Stop:
            pass
        assert startup == [False], agents  # the startup veto refuses the move
        assert skips == [True], agents


def test_an_agent_left_running_blocks_update_even_when_the_fleet_reads_zero(monkeypatch, tmp_path):
    """The idle breadcrumb can erase the fleet's view of an unreaped agent, so the
    runner's own record of it must block the restart."""
    runner = _runner_with(monkeypatch, tmp_path, 0)
    skips: list = []
    monkeypatch.setattr(runner.run_record, "any_left_running", lambda: True)

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


def test_a_tracked_agent_counts_until_its_process_exits(monkeypatch):
    rr = load_module("mesh_run_record_tracking", "mesh/run_record.py")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        rec = type("Rec", (), {"reaped": False, "proc": child})()
        rr.track(rec)
        assert rr.any_left_running() is True
    finally:
        child.kill()
        child.wait()
    assert rr.any_left_running() is False
    rr.track(type("Rec", (), {"reaped": True, "proc": None})())  # reaped agents are not tracked
    assert rr.any_left_running() is False


def test_every_claim_hands_its_run_record_to_the_tracker(monkeypatch, tmp_path):
    from test_mesh_run_record_claim import _runner as _claim_runner

    runner, _calls, _removed, repo = _claim_runner(monkeypatch, tmp_path)
    agent = tmp_path / "agent"
    agent.write_text("#!/bin/sh\nexit 0\n")
    agent.chmod(0o755)
    monkeypatch.setattr(runner, "AGENT_CMD", str(agent))
    tracked: list = []
    monkeypatch.setattr(runner.run_record, "track", tracked.append)
    runner.run_claim({"linear_id": "UNI-T", "repo_dir": str(repo)}, dry_run=False)
    assert len(tracked) == 1 and tracked[0] is not None


def test_dry_run_and_opt_out_never_update(monkeypatch):
    monkeypatch.setattr(su.time, "sleep", lambda s: None)
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root, may_move=None: "abc123")
    assert su.idle_tick(lambda *a: None, 1, "node", skip=True) is False
    monkeypatch.setattr(su, "ENABLED", False)
    assert su.idle_tick(lambda *a: None, 1, "node") is False
