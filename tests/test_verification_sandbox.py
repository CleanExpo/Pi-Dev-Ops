"""Verification must never execute generated code against host credentials."""
import asyncio
import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.server import verification_sandbox as sandbox
from app.server import workspace_verify as verify
from app.server.spec_pipeline import ship_gate


@pytest.fixture(autouse=True)
def candidate_metadata(tmp_path):
    (tmp_path / ".git").mkdir()


def test_linux_command_has_private_mounts_network_and_clean_env(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/bwrap")
    monkeypatch.setenv("SECRET_ADDED_LATER", "never-inherit")
    monkeypatch.setenv("PYTHONPATH", "/host/private")
    monkeypatch.setenv("NODE_OPTIONS", "--require /host/inject.js")
    args, env = sandbox.build_command(str(tmp_path), ["python3", "-m", "pytest"])
    assert "--unshare-all" in args
    assert "--die-with-parent" in args
    assert "--new-session" in args
    assert "--clearenv" in args
    assert "--disable-userns" in args
    assert "--unshare-user" in args
    assert "--share-net" not in args
    assert ["--bind", str(tmp_path.resolve()), "/workspace"] == args[args.index("--bind"):args.index("--bind") + 3]
    assert args[-3:] == ["python3", "-m", "pytest"]
    assert env["HOME"] == "/tmp/home"
    assert env["PYTHONPATH"] == "/workspace"
    assert "never-inherit" not in str(env)
    assert "/host/private" not in str(env)
    assert "NODE_OPTIONS" not in env
    assert "/home" not in args and "/run" not in args
    metadata = ["--ro-bind", str(tmp_path.resolve() / ".git"), "/workspace/.git"]
    assert any(args[i:i + 3] == metadata for i in range(len(args)))


def test_linked_gitfile_is_readonly_without_mounting_its_external_target(monkeypatch, tmp_path):
    (tmp_path / ".git").rmdir()
    (tmp_path / ".git").write_text("gitdir: /host/private/metadata")
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/bwrap")
    args, _ = sandbox.build_command(str(tmp_path), ["python3", "-c", "pass"])
    assert "/host/private/metadata" not in args
    assert any(args[i:i + 3] == ["--ro-bind", str(tmp_path / ".git"), "/workspace/.git"] for i in range(len(args)))


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_unsupported_host_never_starts_unconfined_process(monkeypatch, tmp_path, platform):
    monkeypatch.setattr(sandbox.sys, "platform", platform)
    spawn = Mock()
    monkeypatch.setattr(sandbox.subprocess, "Popen", spawn)
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.run_isolated(str(tmp_path), ["python3", "-c", "pass"], timeout_s=1)
    spawn.assert_not_called()


def test_nested_cwd_must_remain_in_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    monkeypatch.setattr(sandbox.shutil, "which", lambda _: "/usr/bin/bwrap")
    with pytest.raises(sandbox.SandboxUnavailable):
        sandbox.build_command(str(tmp_path), ["python3"], cwd=str(tmp_path.parent))


@pytest.mark.parametrize("failure", [asyncio.TimeoutError, asyncio.CancelledError])
async def test_async_verification_stops_owned_tree_on_timeout_or_cancel(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(sandbox, "build_command", lambda *a, **kw: (["bwrap", "probe"], {}))
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    proc = SimpleNamespace(pid=54321, returncode=None, kill=Mock(),
                           communicate=AsyncMock(side_effect=[failure(), (b"", b"")]))
    killpg = Mock()
    monkeypatch.setattr(sandbox.os, "killpg", killpg, raising=False)
    spawn = AsyncMock(return_value=proc)
    monkeypatch.setattr(sandbox.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(failure):
        await sandbox.run_isolated_async(str(tmp_path), ["probe"], timeout_s=1)
    assert spawn.call_args.kwargs["start_new_session"] is True
    assert spawn.call_args.kwargs["stdin"] == subprocess.DEVNULL
    killpg.assert_called_once_with(proc.pid, signal.SIGKILL)
    proc.kill.assert_called_once()
    assert proc.communicate.await_count == 2


def test_sync_timeout_stops_owned_tree_and_reaps(monkeypatch, tmp_path):
    monkeypatch.setattr(sandbox, "build_command", lambda *a, **kw: (["bwrap", "probe"], {}))
    monkeypatch.setattr(signal, "SIGKILL", 9, raising=False)
    proc = SimpleNamespace(pid=54321, returncode=None, kill=Mock(),
                           communicate=Mock(side_effect=[subprocess.TimeoutExpired("probe", 1), (b"", b"")]))
    killpg = Mock()
    monkeypatch.setattr(sandbox.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(sandbox.subprocess, "Popen", Mock(return_value=proc))
    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run_isolated(str(tmp_path), ["probe"], timeout_s=1)
    killpg.assert_called_once_with(proc.pid, signal.SIGKILL)
    assert proc.communicate.call_count == 2


def test_oracles_all_use_isolated_runner(monkeypatch, tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "dashboard").mkdir()
    monkeypatch.setattr(ship_gate, "_changed_files", lambda _: ["dashboard/app/page.tsx"])
    isolated = Mock(return_value=subprocess.CompletedProcess([], 0, b"passed", b""))
    monkeypatch.setattr(ship_gate, "run_isolated", isolated)
    monkeypatch.setattr(ship_gate.subprocess, "run", Mock(side_effect=AssertionError("unconfined execution")))
    assert all(ship_gate.run_oracles(str(tmp_path)).values())
    assert isolated.call_count == 3
    for call in isolated.call_args_list:
        assert call.args[0] == str(tmp_path)
        assert "env" not in call.kwargs


def test_missing_tests_never_count_as_passing_oracle(monkeypatch, tmp_path):
    monkeypatch.setattr(ship_gate, "_changed_files", lambda _: [])
    monkeypatch.setattr(ship_gate, "run_isolated", Mock(return_value=subprocess.CompletedProcess([], 0, b"", b"")))
    assert ship_gate.run_oracles(str(tmp_path))["pytest_ok"] is False


@pytest.mark.parametrize("code, expected", [(0, verify.PASSED), (1, verify.FAILED)])
async def test_workspace_result_preserves_real_oracle_outcome(monkeypatch, tmp_path, code, expected):
    monkeypatch.setattr(verify, "detect_check", lambda _: (["probe"], "probe"))
    runner = AsyncMock(return_value=subprocess.CompletedProcess([], code, b"test output", b""))
    monkeypatch.setattr(verify, "run_isolated_async", runner)
    result = await verify.run_workspace_checks(str(tmp_path))
    assert result.status == expected
    assert result.output_tail == "test output"


async def test_workspace_verifier_propagates_cancellation(monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "detect_check", lambda _: (["probe"], "probe"))
    monkeypatch.setattr(verify, "run_isolated_async", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await verify.run_workspace_checks(str(tmp_path))


async def test_workspace_timeout_remains_distinct_from_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "detect_check", lambda _: (["probe"], "probe"))
    monkeypatch.setattr(verify, "run_isolated_async", AsyncMock(side_effect=asyncio.TimeoutError))
    result = await verify.run_workspace_checks(str(tmp_path))
    assert result.status == verify.TIMED_OUT


def test_merge_binds_reviewed_candidate_sha(monkeypatch):
    sha = "a" * 40
    monkeypatch.setattr(ship_gate, "machine_ship_enabled", lambda: True)
    def request(method, path, body=None):
        if method == "POST":
            return {"number": 123}
        if method == "PUT":
            assert body["sha"] == sha
            return {"merged": True, "sha": "b" * 40}
        if path.endswith("/pulls/123"):
            return {"head": {"sha": sha}, "base": {"ref": "main"}}
        if path.endswith("/protection"):
            return {"required_status_checks": {"contexts": ["test"]}}
        if "/check-suites?" in path:
            return {"total_count": 1}
        if "/check-runs?" in path:
            return {"total_count": 1, "check_runs": [{"id": 1, "name": "test", "app": {"id": 1},
                "head_sha": sha, "status": "completed", "conclusion": "success"}]}
        return []  # No ruleset requirements or legacy statuses.
    api = Mock(side_effect=request)
    monkeypatch.setattr(ship_gate, "_github_request", api)
    result = ship_gate.open_pr_and_merge(repo="org/repo", branch="candidate", title="reviewed", body="ok", candidate_sha=sha)
    assert result["status"] == "merged" and result["candidate_sha"] == sha
    assert api.call_args.args[2]["sha"] == sha


def test_changed_pr_head_cannot_be_merged(monkeypatch):
    monkeypatch.setattr(ship_gate, "machine_ship_enabled", lambda: True)
    api = Mock(side_effect=[{"number": 123}, {"head": {"sha": "b" * 40}}])
    monkeypatch.setattr(ship_gate, "_github_request", api)
    result = ship_gate.open_pr_and_merge(repo="org/repo", branch="candidate", title="reviewed", body="ok", candidate_sha="a" * 40)
    assert result["status"] == "blocked"
    assert api.call_count == 2


def test_unreadable_diff_cannot_pass_boundary_or_oracles(monkeypatch, tmp_path):
    monkeypatch.setattr(ship_gate.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 128, "", "not a repo")))
    monkeypatch.setattr(ship_gate, "run_isolated", Mock(return_value=subprocess.CompletedProcess([], 0, b"", b"")))
    assert ship_gate.scan_diff_boundary(str(tmp_path)).tier == "blocked"
    assert ship_gate.run_oracles(str(tmp_path))["tsc_ok"] is False


@pytest.mark.parametrize("path", [".env.local", "nested/.env", "nested/server.key", "app/data/.session-secret"])
def test_secret_paths_cannot_pass_diff_boundary(monkeypatch, path):
    monkeypatch.setattr(ship_gate.subprocess, "run", Mock(return_value=subprocess.CompletedProcess([], 0, path, "")))
    assert ship_gate.scan_diff_boundary("workspace").tier == "blocked"


@pytest.mark.skipif(sys.platform != "linux", reason="real bubblewrap confinement requires Linux/WSL2")
def test_real_sandbox_can_work_but_cannot_reach_host_files_or_network(tmp_path):
    if sandbox.shutil.which("bwrap") is None:
        pytest.skip("bubblewrap is not installed")
    secret = tmp_path / "host-secret"
    secret.write_text("synthetic-do-not-expose")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    script = (
        "import os,pathlib,socket; "
        "assert not os.environ.get('GITHUB_TOKEN'); "
        f"assert not pathlib.Path({str(secret)!r}).exists(); "
        "pathlib.Path('/workspace/output').write_text('ok'); "
        "s=socket.socket(); s.settimeout(0.1); "
        "assert s.connect_ex(('192.0.2.1',443)) != 0"
    )
    result = sandbox.run_isolated(str(workspace), ["python3", "-c", script], timeout_s=10)
    assert result.returncode == 0, result.stderr
    assert (workspace / "output").read_text() == "ok"
    assert secret.read_text() == "synthetic-do-not-expose"
