"""An idle runner moves itself to origin/main, but only to code that passes preflight (RA-7802).

Runtimes never updated themselves: every runner fix had to be carried to all
three machines by hand, and on 28/09 the PC ran a version that failed every
claim while the Macs ran another. Now, every CHECK_SECONDS while idle:

  1. fetch origin main; nothing to do if HEAD already matches it;
  2. refuse anything that is not a fast-forward of HEAD;
  3. check the new commit out, detached, in the same folder — so Claude Code's
     workspace trust for that folder carries over;
  4. run the NEW commit's preflight in a fresh process, so the new code itself
     must import and pass on this machine's OS;
  5. pass: the caller exits non-zero and launchd / the Windows watchdog restarts
     it on the new code. Fail: check the old commit back out and say why.
  6. every checkout is proven by reading HEAD back. If the old commit cannot be
     restored the outcome is "stuck" and the runner stops instead of restarting
     on code whose preflight failed.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

CHECK_SECONDS = float(os.environ.get("MESH_UPDATE_SECONDS", "900"))
PREFLIGHT_TIMEOUT = 600
Run = Callable[..., subprocess.CompletedProcess]


def _git(run: Run, repo: Path, *args: str) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def runtime_version(repo: Path, run: Run = subprocess.run) -> str:
    """The commit this runtime runs, for the heartbeat. "unknown" if git cannot say."""
    try:
        head = _git(run, repo, "rev-parse", "HEAD")
    except OSError:
        return "unknown"
    return head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else "unknown"


def mark_stuck(marker: Path, outcome: str) -> None:
    """Record a stuck update where no checkout can remove it. Every later start obeys it."""
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(outcome + "\n", encoding="utf-8")


def stuck_reason(marker: Path) -> str:
    """Why this runtime must not claim, or "". A person deletes the marker once HEAD is proven."""
    try:
        return marker.read_text(encoding="utf-8").strip() or "stuck"
    except FileNotFoundError:
        return ""
    except OSError:
        return "stuck marker unreadable"


class Updater:
    """Decides when to look for new code, and moves to it safely."""

    def __init__(self, repo: Path, agent_cmd: str, run: Run = subprocess.run,
                 clock: Callable[[], float] = time.monotonic, every: float = CHECK_SECONDS):
        self._repo, self._agent, self._run = Path(repo), agent_cmd, run
        self._clock, self._every = clock, every
        self._last = clock()

    def due(self) -> bool:
        return self._clock() - self._last >= self._every

    def try_update(self) -> str:
        """One attempt. "updated" means the caller must exit so it restarts on new code."""
        self._last = self._clock()
        try:
            return self._attempt()
        except (OSError, subprocess.SubprocessError) as exc:
            return f"update failed: {type(exc).__name__}"

    def _attempt(self) -> str:
        if _git(self._run, self._repo, "fetch", "--quiet", "origin", "main").returncode != 0:
            return "update failed: fetch"
        old = runtime_version(self._repo, self._run)
        new = _git(self._run, self._repo, "rev-parse", "FETCH_HEAD").stdout.strip()
        if not new or new == old:
            return "current"
        if _git(self._run, self._repo, "merge-base", "--is-ancestor", old, new).returncode != 0:
            return "update refused: origin/main is not a fast-forward of this runtime"
        if not self._checkout(new):
            return self._back_to(old, "update failed: checkout")
        problem = self._new_code_preflight()
        if problem:
            return self._back_to(old, f"rolled back: {problem}")
        return "updated"

    def _checkout(self, sha: str) -> bool:
        """Check `sha` out, and prove HEAD is now `sha`: an exit code alone is not proof,
        and a checkout that raises is a failed one (Codex round 2), never an escape."""
        try:
            if _git(self._run, self._repo, "checkout", "--quiet", "--detach", sha).returncode != 0:
                return False
        except (OSError, subprocess.SubprocessError):
            return False
        return runtime_version(self._repo, self._run) == sha

    def _back_to(self, old: str, outcome: str) -> str:
        """Return to the old commit. If even that fails the runtime is on code that
        was never proven here, so say "stuck": the runner stops rather than restart on it."""
        if self._checkout(old):
            return outcome
        return f"stuck: could not return to {old[:12]} ({outcome})"

    def _new_code_preflight(self) -> str:
        """Run the checked-out commit's own preflight, in a fresh interpreter."""
        script = self._repo / "mesh" / "preflight.py"
        try:
            done = self._run([sys.executable, str(script), str(self._repo), self._agent],
                             capture_output=True, text=True, check=False, timeout=PREFLIGHT_TIMEOUT)
        except subprocess.TimeoutExpired:
            return "new code's preflight timed out"
        except (OSError, subprocess.SubprocessError) as exc:
            return f"new code's preflight could not start: {type(exc).__name__}"
        if done.returncode == 0:
            return ""
        lines = (done.stdout or "").strip().splitlines()
        return lines[-1][:200] if lines else f"new code's preflight exited {done.returncode}"
