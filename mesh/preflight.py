"""Prove this node can do a run before it claims one (RA-7802).

Each check returns "" when it passes or a short, fixed-shape problem. The
problems come from this module, never from agent output, so they are safe to
put in a heartbeat.

  run_log      — a run log opens here. Catches platform faults in the runner
                 itself: on Windows `os.O_NOFOLLOW` raised before any agent ran
                 (RA-7801), and every claim failed.
  agent_writes — the agent, started exactly as a real run starts it, writes a
                 file in a scratch worktree of the repo it builds in. Catches an
                 agent that cannot act: on 28/09 the Mini's new runtime folder
                 was never trusted by Claude Code, so the repo's permissions
                 were ignored and every run ended "no commits".
"""
from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Callable

import agent_sandbox
import claim_lifecycle
import run_record

PROBE_PROMPT = ("Create a file named {name} in the current directory containing "
                "the single word ok. Do not do anything else. Do not commit.")
UNTRUSTED = "has not been trusted"
AGENT_TIMEOUT = 300


def run_log() -> str:
    """A run log opens in a scratch directory on this machine."""
    scratch = Path(tempfile.mkdtemp(prefix="mesh-preflight-"))
    try:
        rec = run_record.RunRecord("00000000", scratch)
        opened = rec.path is not None
        rec.close()
        return "" if opened else "run log could not be opened"
    except Exception as exc:  # noqa: BLE001 — a crash here is what a real run would hit
        return f"run log raised {type(exc).__name__}"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def agent_writes(repo_dir: Path, agent_cmd: str,
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    """The agent writes a file in a scratch worktree, and is not in an untrusted workspace."""
    worktree = Path(tempfile.mkdtemp(prefix="mesh-preflight-wt-", dir=claim_lifecycle.temp_root())) / "wt"
    try:
        added = run(["git", "-C", str(repo_dir), "worktree", "add", "--detach", str(worktree), "HEAD"],
                    capture_output=True, text=True, check=False)
        if added.returncode != 0:
            return "scratch worktree could not be created"
        # A fresh name each time, proven absent first: a file the repo already
        # tracks, or one left by an earlier probe, must never pass for the agent's.
        probe = worktree / f"mesh-preflight-{uuid.uuid4().hex}.txt"
        if probe.exists():
            return "scratch worktree already holds the probe file"
        agent = run(agent_sandbox.agent_argv(agent_cmd, PROBE_PROMPT.format(name=probe.name)),
                    cwd=str(worktree), env=agent_sandbox.agent_env(),
                    capture_output=True, text=True, check=False, timeout=AGENT_TIMEOUT)
        if UNTRUSTED in f"{agent.stdout or ''}{agent.stderr or ''}":
            return f"agent workspace not trusted: run `{agent_cmd}` once in {repo_dir} and accept"
        if agent.returncode != 0:
            return f"agent exited {agent.returncode}"
        if not probe.is_file() or probe.read_text(errors="replace").strip().lower() != "ok":
            return "agent could not write a file"
        return ""
    except subprocess.TimeoutExpired:
        return "agent timed out"
    except OSError:
        return "agent could not start"
    finally:
        run(["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(worktree)],
            capture_output=True, text=True, check=False)
        shutil.rmtree(worktree.parent, ignore_errors=True)


def runner_loads(mesh_dir: Path) -> str:
    """Every module in this checkout's mesh/ compiles, and runner.py imports.

    self_update runs a candidate commit's preflight.py in a fresh interpreter, so
    this is the only place the NEW runner code is loaded before the runner restarts
    onto it. Without it, a syntax error in runner.py passed (Codex round 4).
    """
    for module in sorted(mesh_dir.glob("*.py")):
        try:
            compile(module.read_text(encoding="utf-8"), str(module), "exec")  # no .pyc written
        except (SyntaxError, ValueError, OSError):
            return f"{module.name} does not compile"
    try:
        importlib.import_module("runner")
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — any failure to load is a failure to run
        return f"runner does not import: {type(exc).__name__}"
    return ""


def check(repo_dir: Path, agent_cmd: str) -> str:
    """Every preflight check, first problem wins."""
    return run_log() or agent_writes(repo_dir, agent_cmd)


if __name__ == "__main__":  # self_update runs a NEW commit's preflight this way
    problem = runner_loads(Path(__file__).resolve().parent) or check(Path(sys.argv[1]), sys.argv[2])
    print(problem or "ok")
    sys.exit(1 if problem else 0)
