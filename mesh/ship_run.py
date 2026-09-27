"""Ship a mesh run's worktree branch from the runner itself (RA-7780).

A run is not delivered until its commits are on the remote. The runner used to
report `done` on agent exit 0 and leave shipping to a per-machine Claude Stop hook
(mesh/hooks/mesh_ship.sh). A node without that hook — the Windows PC and the
MacBook on 28/09/2026 — then lost the work when `run_claim` force-removed the
worktree, while the fleet recorded a success.

`ship()` commits anything the agent left uncommitted, requires at least one
commit beyond the run's start point, and pushes the branch with an explicit
refspec and never a force. On a node that still has the Stop hook, that hook has
usually pushed already and this push is an up-to-date no-op.

The start point is read by the runner BEFORE the agent launches and held in the
runner's memory. Anything read from the repository afterwards — the checkout's
HEAD, the branch reflog — can be moved or rewritten by the agent running in that
worktree, and two review rounds showed each one faking an empty run as delivered.
This measures delivery, not quality: an agent set on faking work can still commit
junk, which the pushed branch then shows for review.

It returns None when the branch is on the remote, else a one-line reason, which
`run_claim` turns into `failed` so the ticket goes back to the pool instead of
reading as done.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REMOTE = "origin"
_TIMEOUT = 120


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, timeout=_TIMEOUT, check=False)


def _commit_leftovers(worktree: Path, linear_id: str, host: str) -> str | None:
    """Commit uncommitted agent output. The identity is set only for this commit,
    so a node with no git identity configured still ships."""
    if not _git(worktree, "status", "--porcelain").stdout.strip():
        return None
    _git(worktree, "add", "-A")
    done = _git(worktree, "-c", f"user.name=Nexus Mesh ({host})",
                "-c", "user.email=mesh@unite-group.invalid",
                "commit", "-q", "-m", f"{linear_id}: mesh run output from {host}")
    return None if done.returncode == 0 else f"commit failed: {done.stderr.strip()[:200]}"


def start_point(repo_dir: Path) -> str:
    """The checkout's HEAD, which `worktree add -b` branches the run from. Call it
    BEFORE the agent launches and keep the value; "" when unreadable, which ship()
    treats as nothing proven."""
    head = _git(Path(repo_dir), "rev-parse", "HEAD")
    return head.stdout.strip() if head.returncode == 0 else ""


def ship(start: str, worktree: Path, branch: str, linear_id: str,
         host: str) -> str | None:
    """Put this run's branch on the remote. None on success, else why not."""
    if not branch.startswith("mesh/"):
        return f"refusing to push non-mesh branch {branch}"
    error = _commit_leftovers(Path(worktree), linear_id, host)
    if error:
        return error
    ahead = _git(Path(worktree), "rev-list", "--count", f"{start}..HEAD").stdout.strip()
    if not start or ahead in ("", "0"):
        return "no commits: agent exited 0 but changed nothing"
    pushed = _git(Path(worktree), "push", "-q", REMOTE, f"HEAD:refs/heads/{branch}")
    if pushed.returncode != 0:
        return f"push failed: {pushed.stderr.strip()[:200]}"
    return None


def settle(plan: dict, start: str, worktree: Path, branch: str, linear_id: str,
           host: str) -> None:
    """Turn a `done` run into `failed` when its work did not reach the remote.
    Any other state already says the run did not deliver, so it is left alone."""
    if plan.get("state") != "done":
        return
    error = ship(start, worktree, branch, linear_id, host)
    if error:
        plan.update(state="failed", error=error)
