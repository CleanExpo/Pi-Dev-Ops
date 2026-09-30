"""What a mesh build agent is started with, and how everything it started is ended.

Estate audit 30/09/2026, rank 13. The runner used to start `claude -p` with its
own whole environment and stop only that one process. The cloud server does the
opposite (app/server/sdk_execution_boundary._child_environment): every inherited
value it does not need is blanked. The runner now matches it:

  agent_env   — only what the CLI needs to run and to find its own login. On
                darwin the login is in the keychain, reached through HOME/USER;
                no API key or bearer token is passed. CLAUDE_CONFIG_DIR is a path,
                not a credential, and is kept so a node's chosen login still works.
  agent_argv  — an explicit --allowedTools set: the workspace tools, nothing else
                pre-approved.
  end_group   — the agent runs as the leader of its own process group
                (start_new_session), so stopping it signals the whole group and
                then proves the group is empty before the worktree is removed.

Not contained: a descendant that calls setsid() leaves the group. That needs an
OS sandbox, not a signal.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from typing import Mapping, Optional

_AGENT_ENV = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL", "LC_CTYPE",
    "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "WINDIR", "PATHEXT",
    # Windows: where the CLI finds its home and config, and the shell it runs Bash in.
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "COMSPEC",
    "CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CONFIG_DIR",
})
ALLOWED_TOOLS = ("Bash", "Read", "Edit", "Write", "MultiEdit", "Glob", "Grep", "TodoWrite")
GROUPS = hasattr(os, "killpg")  # POSIX; Windows keeps the direct-child stop
EMPTY_TIMEOUT = 5.0


def agent_env(environ: Optional[Mapping[str, str]] = None) -> dict:
    """The allowlisted subset of `environ` (default os.environ). Names compare case-insensitively."""
    source = os.environ if environ is None else environ
    return {name: value for name, value in source.items() if name.upper() in _AGENT_ENV}


def agent_argv(agent_cmd: str, prompt: str) -> list:
    """ONE ``--allowedTools=a,b`` argument, as plan_lane passes --disallowedTools: the flag
    is variadic, and a single ``=`` argument cannot swallow a neighbouring one."""
    return [agent_cmd, "-p", prompt, "--allowedTools=" + ",".join(ALLOWED_TOOLS)]


def signal_group(pgid: Optional[int], sig: int) -> None:
    """Send `sig` to the agent's group. A group that is already empty is not an error."""
    if pgid is None or not GROUPS:
        return
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:  # darwin: a group holding a zombie; group_empty decides
        pass


def group_empty(pgid: Optional[int], timeout: float) -> bool:
    """True once no process is left in the group; False if one still is after `timeout`.

    Killed descendants are reparented to init, which reaps them, so a short wait
    covers the moment they are zombies still counted in the group. A member this
    user cannot signal is also "not empty": the run is then reported unreaped.
    """
    if pgid is None or not GROUPS:
        return True
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:  # darwin answers EPERM while a zombie is in the group
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def end_group(pgid: Optional[int]) -> bool:
    """Kill whatever is left in the agent's group and prove it is empty.

    The kill is resent until the group is empty: darwin can refuse a group signal
    with EPERM while a zombie is in it, and a process may fork while it is sent.
    """
    if pgid is None or not GROUPS:
        return True
    deadline = time.monotonic() + EMPTY_TIMEOUT
    while True:
        signal_group(pgid, signal.SIGKILL)
        if group_empty(pgid, 0):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


class GroupSurvived(RuntimeError):
    """A contained run left a process in its group that could not be ended."""

    def __init__(self, pgid: int):
        super().__init__(f"process group {pgid} could not be emptied")
        self.pgid = pgid


def run_contained(argv: list, *, cwd: Optional[str] = None, env: Optional[dict] = None,
                  timeout: Optional[float] = None, **_run_kwargs) -> subprocess.CompletedProcess:
    """`subprocess.run(argv, capture_output=True, text=True, check=False)` for an agent, except
    that the agent leads its own process group and the whole group is ended before this
    returns: on success, on timeout and on an interrupt. Raises TimeoutExpired as run does,
    and GroupSurvived when the group cannot be proven empty; the caller must then keep its
    worktree. The group is killed before the final read, so a descendant holding the
    output pipes cannot stall it; its output is then discarded."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=GROUPS)
    pgid = proc.pid if GROUPS else None
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        if GROUPS:
            signal_group(pgid, signal.SIGKILL)
        proc.kill()
        proc.wait()  # not communicate(): a surviving descendant holding the pipes would stall it
        for pipe in (proc.stdout, proc.stderr):
            pipe.close()
        if not end_group(pgid):
            raise GroupSurvived(pgid) from None
        raise
    if not end_group(pgid):
        raise GroupSurvived(pgid)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)
