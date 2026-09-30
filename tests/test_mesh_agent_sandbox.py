"""tests/test_mesh_agent_sandbox.py — the mesh agent sees no runner secrets and leaves nothing running.

Estate audit 30/09/2026, rank 13. `claude -p` on a Mac runner inherited the
runner's whole environment, and stop() killed only the direct child, so a
process the agent started could keep running in a worktree the runner then
removed. The server already blanks every inherited value it does not need
(app/server/sdk_execution_boundary._child_environment); the runner now does the
same, starts the agent in its own process group, and reaps that group.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

from mesh_helpers import load_module  # noqa: E402

rr = load_module("mesh_run_record_sandbox_under_test", "mesh/run_record.py")

posix_only = pytest.mark.skipif(not hasattr(os, "killpg"), reason="process groups are POSIX")


def _wait_until_exit(proc, plan):
    proc.wait(timeout=30)
    plan["state"] = "done" if proc.returncode == 0 else "failed"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _gone_within(pid: int, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def test_a_planted_runner_secret_is_invisible_to_the_agent(tmp_path, monkeypatch):
    """The agent sees what the CLI needs (PATH, HOME) and none of the runner's secrets."""
    monkeypatch.setenv("MESH_PLANTED_SECRET", "planted-" + "value-4417")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "planted-" + "api-key")
    monkeypatch.setenv("PI_CEO_API_KEY", "planted-" + "mesh-key")
    dump = tmp_path / "env.txt"
    code = f"import os; open({str(dump)!r}, 'w').write('\\n'.join(sorted(os.environ)))"
    plan: dict = {}
    rec = rr.run_agent(lambda: [sys.executable, "-c", code], str(tmp_path), tmp_path,
                       "0b0b0b01", plan, _wait_until_exit)
    assert plan["state"] == "done", plan
    seen = set(dump.read_text().split("\n"))
    assert "PATH" in seen and "HOME" in seen, f"positive control: the agent lost what it needs: {seen}"
    for name in ("MESH_PLANTED_SECRET", "ANTHROPIC_API_KEY", "PI_CEO_API_KEY"):
        assert name not in seen, f"{name} leaked into the agent's environment"
    assert rec.reaped is True


def _spawn_grandchild_then(tmp_path: Path, then: str) -> list:
    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time\n"
        "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(g.pid))\n"
        f"{then}\n"
    )
    return [sys.executable, "-c", code], pid_file


def _read_pid(pid_file: Path) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pid_file.exists() and pid_file.read_text().strip():
            return int(pid_file.read_text())
        time.sleep(0.05)
    raise AssertionError("the agent never started its grandchild")


@posix_only
def test_stop_reaps_a_sleeping_grandchild(tmp_path):
    """A failed run's stop() ends everything the agent started, not only the agent."""
    cmd, pid_file = _spawn_grandchild_then(tmp_path, "time.sleep(60)")
    seen: list = []

    def failing_wait(proc, _plan):
        seen.append(_read_pid(pid_file))
        raise OSError("wait failed")

    plan: dict = {}
    rec = rr.run_agent(lambda: cmd, str(tmp_path), tmp_path, "0b0b0b02", plan, failing_wait)
    try:
        assert plan["state"] == "failed"
        assert _gone_within(seen[0]), "the agent's sleeping grandchild outlived stop()"
        assert rec.reaped is True
    finally:
        if seen and _alive(seen[0]):
            os.kill(seen[0], 9)


@posix_only
def test_a_clean_exit_still_reaps_what_the_agent_left_behind(tmp_path):
    """An agent that exits 0 with a background process running must not leave it in the worktree."""
    cmd, pid_file = _spawn_grandchild_then(tmp_path, "sys.exit(0)")
    plan: dict = {}
    rec = rr.run_agent(lambda: cmd, str(tmp_path), tmp_path, "0b0b0b03", plan, _wait_until_exit)
    pid = _read_pid(pid_file)
    try:
        assert plan["state"] == "done"
        assert _gone_within(pid), "the agent's background process outlived the run"
        assert rec.reaped is True
    finally:
        if _alive(pid):
            os.kill(pid, 9)


@posix_only
def test_a_descendant_that_cannot_be_ended_marks_the_run_unreaped(tmp_path, monkeypatch):
    """If the group cannot be proven empty, the claim and worktree must be kept (reaped False)."""
    monkeypatch.setattr(rr.agent_sandbox, "group_empty", lambda _pgid, _timeout: False)
    monkeypatch.setattr(rr.agent_sandbox, "EMPTY_TIMEOUT", 0.2)
    plan: dict = {}
    rec = rr.run_agent(lambda: [sys.executable, "-c", "pass"], str(tmp_path), tmp_path,
                       "0b0b0b04", plan, _wait_until_exit)
    assert rec.reaped is False
    assert rr.unreaped(rec)


@posix_only
def test_a_survivor_of_an_exited_agent_keeps_blocking_self_update(tmp_path, monkeypatch):
    """Review P1: with the leader gone and a descendant alive, the record must still say alive."""
    import left_running  # on sys.path via run_record

    monkeypatch.setattr(left_running, "PATH", tmp_path / "left.json")
    monkeypatch.setattr(rr.agent_sandbox, "signal_group", lambda _pgid, _sig: None)  # the kill fails
    monkeypatch.setattr(rr.agent_sandbox, "EMPTY_TIMEOUT", 0.2)
    cmd, pid_file = _spawn_grandchild_then(tmp_path, "sys.exit(0)")
    plan: dict = {}
    rec = rr.run_agent(lambda: cmd, str(tmp_path), tmp_path, "0b0b0b05", plan, _wait_until_exit)
    survivor = _read_pid(pid_file)
    try:
        assert rec.reaped is False and not _alive(rec.proc.pid)
        left_running.track(rec)
        assert left_running.any_alive(), "an exited leader's live descendant was forgotten"
    finally:
        os.kill(survivor, 9)
    assert _gone_within(survivor)
    assert _gone_within_group(rec.pgid) and not left_running.any_alive()


def _gone_within_group(pgid: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.05)
    return False


def test_the_build_agent_gets_an_explicit_tool_allowlist(monkeypatch, tmp_path):
    """runner.py starts the agent with an explicit --allowedTools set."""
    monkeypatch.setenv("MESH_REPO_DIR", str(REPO_ROOT))
    runner = load_module("mesh_runner_sandbox_under_test", "mesh/runner.py")
    captured: list = []

    def fake_run_agent(make_cmd, *_a, **_k):
        captured.append(make_cmd())

    monkeypatch.setattr(runner.run_record, "run_agent", fake_run_agent)
    monkeypatch.setattr(runner.claim_lifecycle, "add_worktree", lambda *a: True)
    monkeypatch.setattr(runner.claim_lifecycle, "deliver", lambda *a: None)
    monkeypatch.setattr(runner.claim_lifecycle, "end", lambda *a, **k: None)
    monkeypatch.setattr(runner.ship_run, "start_point", lambda *a: None)
    monkeypatch.setattr(runner, "_api", lambda *a, **k: {})
    monkeypatch.setattr(runner, "STATE_FILE", tmp_path / "state.json")
    runner.run_claim({"linear_id": "UNI-1", "id": "c1", "repo_dir": str(REPO_ROOT)}, dry_run=False)
    argv = captured[0]
    assert argv[:2] == [runner.AGENT_CMD, "-p"]
    flags = [a for a in argv if a.startswith("--allowedTools=")]
    assert len(flags) == 1, argv
    tools = flags[0].split("=", 1)[1].split(",")
    assert "Bash" in tools and "Edit" in tools and "Write" in tools, tools


def test_the_env_allowlist_is_case_insensitive_and_drops_unknown_names():
    """Windows spells PATH as Path; an unknown name is dropped whatever it holds."""
    env = rr.agent_sandbox.agent_env({"Path": "x", "HOME": "/h", "GITHUB_TOKEN": "t", "SSH_AUTH_SOCK": "s"})
    assert env == {"Path": "x", "HOME": "/h"}
