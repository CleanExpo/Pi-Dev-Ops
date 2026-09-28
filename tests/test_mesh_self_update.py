"""tests/test_mesh_self_update.py — a node's runtime follows origin/main (RA-7798).

After #800 merged, all three runners kept running older code until each was
moved by hand. `fast_forward` moves a clean, detached runtime to origin/main and
refuses every other shape; `idle_tick` turns a move into a restart.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mesh"))  # self_update imports its sibling, as runner.py sets up

import left_running  # noqa: E402
from mesh_helpers import load_module  # noqa: E402

su = load_module("mesh_self_update_under_test", "mesh/self_update.py")


@pytest.fixture(autouse=True)
def _private_left_running_file(tmp_path, monkeypatch):
    """Never read or write the node's real ~/.claude/mesh-left-running.json."""
    monkeypatch.setattr(left_running, "PATH", tmp_path / "left-running.json")


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


def test_a_concurrent_fetch_of_another_branch_cannot_redirect_the_move(tmp_path, monkeypatch):
    """FETCH_HEAD is shared; a second fetch landing after ours must not pick the target."""
    origin, runtime, old, new = _fleet(tmp_path)
    _git(origin, "checkout", "-q", "-b", "other", old)
    other = _commit(origin, "c")
    _git(origin, "checkout", "-q", "main")

    def fetch_then_race(root, *args):
        result = _REAL_GIT(root, *args)
        if args[:1] == ("fetch",):
            _REAL_GIT(root, "fetch", "-q", "origin", "other")  # overwrites FETCH_HEAD
        return result

    monkeypatch.setattr(su, "_git", fetch_then_race)
    assert su.fast_forward(runtime) == new
    assert _git(runtime, "rev-parse", "HEAD") == new != other


def test_a_branch_checked_out_during_the_fetch_is_not_detached(tmp_path, monkeypatch):
    _, runtime, old, _ = _fleet(tmp_path)

    def fetch_then_operator_checkout(root, *args):
        result = _REAL_GIT(root, *args)
        if args[:1] == ("fetch",):
            _REAL_GIT(root, "checkout", "-q", "-b", "operator-work", old)
        return result

    monkeypatch.setattr(su, "_git", fetch_then_operator_checkout)
    assert su.fast_forward(runtime) is None
    assert _git(runtime, "symbolic-ref", "--short", "HEAD") == "operator-work"
    assert _git(runtime, "rev-parse", "HEAD") == old


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


def test_dry_run_and_opt_out_never_update(monkeypatch):
    monkeypatch.setattr(su.time, "sleep", lambda s: None)
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root, may_move=None: "abc123")
    assert su.idle_tick(lambda *a: None, 1, "node", skip=True) is False
    monkeypatch.setattr(su, "ENABLED", False)
    assert su.idle_tick(lambda *a: None, 1, "node") is False
