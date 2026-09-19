"""Run untrusted deterministic checks inside a private Linux bubblewrap namespace.

Only system runtimes and the candidate workspace are mounted. No host credential
directories, network, inherited environment, or unsandboxed fallback are exposed.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys


class SandboxUnavailable(RuntimeError):
    """The host cannot run verification with the required isolation."""


def child_env() -> dict[str, str]:
    return {
        "PATH": "/workspace/.venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp/home", "TMPDIR": "/tmp", "CI": "1",
        "LANG": "C.UTF-8", "PYTHONPATH": "/workspace",
        "PYTHONNOUSERSITE": "1", "NPM_CONFIG_CACHE": "/tmp/npm-cache",
    }


def build_command(workspace: str, argv: list[str], *, cwd: str | None = None) -> tuple[list[str], dict[str, str]]:
    """Build the bubblewrap command; failures never select a host-shell fallback."""
    if not argv:
        raise SandboxUnavailable("verification command is empty")
    root, working, metadata, binary = _validated_paths(workspace, cwd)
    command = [str(binary), "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent", "--new-session",
               "--cap-drop", "ALL", "--clearenv", "--ro-bind", "/usr", "/usr"]
    # /usr includes /usr/local runtimes. Other layouts may keep libraries in
    # separate top-level directories; expose only those read-only runtime paths.
    for path in ("/bin", "/sbin", "/lib", "/lib64"):
        if Path(path).exists():
            command.extend(["--ro-bind", path, path])
    command.extend(["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                    "--dir", "/tmp/home", "--bind", str(root), "/workspace",
                    "--ro-bind", str(metadata), "/workspace/.git"])
    # The metadata mountpoint cannot be renamed/unlinked through its writable
    # parent. Linked worktree Git files stay read-only; their external metadata
    # target is never mounted. Nested user namespaces cannot unmount this guard.
    env = child_env()
    for name, value in env.items():
        command.extend(["--setenv", name, value])
    relative = working.relative_to(root).as_posix()
    command.extend(["--chdir", "/workspace" if relative == "." else f"/workspace/{relative}", "--"])
    for arg in argv:
        path = Path(arg)
        if path.is_absolute() and path.is_relative_to(root):
            command.append("/workspace/" + path.relative_to(root).as_posix())
        else:
            command.append(arg)
    return command, env


def _stop_tree(proc) -> None:
    """Only target the process group created for this verification invocation."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    if proc.returncode is None:
        try:
            proc.kill()
        except OSError:
            pass


def run_isolated(workspace: str, argv: list[str], *, timeout_s: int, cwd: str | None = None) -> subprocess.CompletedProcess:
    command, env = build_command(workspace, argv, cwd=cwd)
    proc = subprocess.Popen(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, close_fds=True)
    try:
        out, err = proc.communicate(timeout=timeout_s)
    except BaseException:
        _stop_tree(proc)
        try:
            proc.communicate(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


async def run_isolated_async(workspace: str, argv: list[str], *, timeout_s: int, cwd: str | None = None) -> subprocess.CompletedProcess:
    command, env = build_command(workspace, argv, cwd=cwd)
    proc = await asyncio.create_subprocess_exec(
        *command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True, close_fds=True,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except BaseException:
        _stop_tree(proc)
        try:
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            pass
        raise
    finally:
        transport = getattr(proc, "_transport", None)
        if transport is not None:
            transport.close()
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def _validated_paths(workspace, cwd):
    if sys.platform != "linux":
        raise SandboxUnavailable("verification isolation requires Linux or WSL2 with bubblewrap")
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise SandboxUnavailable("verification isolation requires bubblewrap")
    root = Path(workspace).resolve()
    working = Path(cwd or workspace).resolve()
    if not root.is_dir() or not working.is_dir():
        raise SandboxUnavailable("verification workspace does not exist")
    if root == Path(root.anchor) or Path.home().resolve().is_relative_to(root):
        raise SandboxUnavailable("verification workspace cannot expose a host root or home")
    if not working.is_relative_to(root):
        raise SandboxUnavailable("verification cwd escapes the candidate workspace")
    metadata = root / ".git"
    if metadata.is_symlink() or not (metadata.is_dir() or metadata.is_file()):
        raise SandboxUnavailable("verification requires non-symlink candidate Git metadata")
    binary = Path(bwrap).resolve()
    if binary.is_relative_to(root):
        raise SandboxUnavailable("verification sandbox executable cannot come from candidate workspace")
    return root, working, metadata, binary
