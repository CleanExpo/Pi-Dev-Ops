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

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import run_record

PROBE_FILE = "MESH_PREFLIGHT.txt"
PROBE_PROMPT = (f"Create a file named {PROBE_FILE} in the current directory containing "
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
    worktree = Path(tempfile.mkdtemp(prefix="mesh-preflight-wt-")) / "wt"
    try:
        added = run(["git", "-C", str(repo_dir), "worktree", "add", "--detach", str(worktree), "HEAD"],
                    capture_output=True, text=True, check=False)
        if added.returncode != 0:
            return "scratch worktree could not be created"
        agent = run([agent_cmd, "-p", PROBE_PROMPT], cwd=str(worktree),
                    capture_output=True, text=True, check=False, timeout=AGENT_TIMEOUT)
        if UNTRUSTED in f"{agent.stdout or ''}{agent.stderr or ''}":
            return f"agent workspace not trusted: run `{agent_cmd}` once in {repo_dir} and accept"
        if not (worktree / PROBE_FILE).is_file():
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


def check(repo_dir: Path, agent_cmd: str) -> str:
    """Every preflight check, first problem wins."""
    return run_log() or agent_writes(repo_dir, agent_cmd)
