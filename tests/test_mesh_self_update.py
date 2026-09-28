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
    monkeypatch.setattr(su, "fast_forward", lambda root: "abc123")
    assert su.idle_tick(lambda *a: states.append(a), 1, "node") is True
    assert states == [(None, "idle")]
    assert su.idle_tick(lambda *a: None, 1, "node") is False  # inside the interval
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root: None)
    assert su.idle_tick(lambda *a: None, 1, "node") is False


def test_a_relaunched_runner_updates_before_it_claims(monkeypatch, tmp_path):
    """After a MAX_CLAIMS stop the next launch must not claim on stale code."""
    monkeypatch.delenv("MESH_REPO_DIR", raising=False)
    runner = load_module("mesh_runner_startup_update", "mesh/runner.py")
    claimed: list = []
    monkeypatch.setattr(runner, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(runner, "get_work", lambda: claimed.append(1) or [])
    monkeypatch.setattr(runner.self_update, "update_now", lambda host: True)
    monkeypatch.setattr(sys, "argv", ["runner"])
    assert runner.main() == runner.self_update.RESTART_EXIT
    assert claimed == []


def test_dry_run_and_opt_out_never_update(monkeypatch):
    monkeypatch.setattr(su.time, "sleep", lambda s: None)
    monkeypatch.setattr(su, "_last_check", [float("-inf")])
    monkeypatch.setattr(su, "fast_forward", lambda root: "abc123")
    assert su.idle_tick(lambda *a: None, 1, "node", skip=True) is False
    monkeypatch.setattr(su, "ENABLED", False)
    assert su.idle_tick(lambda *a: None, 1, "node") is False
