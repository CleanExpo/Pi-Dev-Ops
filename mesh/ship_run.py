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

The start commit AND the push URL are read by the runner BEFORE the agent launches
and held in the runner's memory. Anything read from the repository afterwards can
be moved or rewritten by the agent running in that worktree. Review rounds showed
the checkout's HEAD, the branch reflog, `remote.origin.pushurl` and
`push.followTags` each faking or widening a ship. So the push names the held URL
directly rather than the `origin` remote, and it passes `--no-follow-tags`.

Threat model: this measures delivery, not quality, and it does not contain a
hostile agent. An agent set on faking work can commit junk, which the pushed branch
then shows for review. An agent that rewrites git's own URL rewriting or hooks has
the same shell and credentials it would need to push anywhere itself.

It returns None when the branch is on the remote, else a one-line reason, which
`run_claim` turns into `failed` so the ticket goes back to the pool instead of
reading as done.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import NamedTuple

REMOTE = "origin"
_TIMEOUT = 120


class Start(NamedTuple):
    """What the runner holds from before the agent ran: the commit the run branches
    from and the URL its work must reach."""
    sha: str
    url: str


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                          text=True, timeout=_TIMEOUT, check=False)


def _commit_leftovers(worktree: Path, linear_id: str, host: str) -> str | None:
    """Commit uncommitted agent output. The identity is set only for this commit,
    so a node with no git identity configured still ships. A failed status or stage
    is an error, never "nothing to commit": either one left work behind that the
    worktree removal would then destroy."""
    status = _git(worktree, "status", "--porcelain")
    if status.returncode != 0:
        return f"status failed: {status.stderr.strip()[:200]}"
    if not status.stdout.strip():
        return None
    staged = _git(worktree, "add", "-A")
    if staged.returncode != 0:
        return f"stage failed: {staged.stderr.strip()[:200]}"
    done = _git(worktree, "-c", f"user.name=Nexus Mesh ({host})",
                "-c", "user.email=mesh@unite-group.invalid",
                "commit", "-q", "-m", f"{linear_id}: mesh run output from {host}")
    return None if done.returncode == 0 else f"commit failed: {done.stderr.strip()[:200]}"


def start_point(repo_dir: Path) -> Start:
    """The checkout's HEAD, which `worktree add -b` branches the run from, and the
    URL `origin` pushes to. Call it BEFORE the agent launches and keep the value.
    Either field is "" when unreadable, which ship() treats as nothing proven.
    It never raises: run_claim calls it before its try/finally, so an escaping git
    timeout would leave the claim `working` and lock the ticket from every node."""
    try:
        head = _git(Path(repo_dir), "rev-parse", "HEAD")
        url = _git(Path(repo_dir), "remote", "get-url", "--push", REMOTE)
    except (OSError, subprocess.SubprocessError):
        return Start("", "")
    return Start(head.stdout.strip() if head.returncode == 0 else "",
                 url.stdout.strip() if url.returncode == 0 else "")


def ship(start: Start, worktree: Path, branch: str, linear_id: str,
         host: str) -> str | None:
    """Put this run's branch on the remote. None on success, else why not."""
    if not branch.startswith("mesh/"):
        return f"refusing to push non-mesh branch {branch}"
    error = _commit_leftovers(Path(worktree), linear_id, host)
    if error:
        return error
    ahead = _git(Path(worktree), "rev-list", "--count", f"{start.sha}..HEAD").stdout.strip()
    if not start.sha or ahead in ("", "0"):
        return "no commits: agent exited 0 but changed nothing"
    if not start.url:
        return "no push URL was readable before the agent ran"
    pushed = _git(Path(worktree), "push", "-q", "--no-follow-tags", start.url,
                  f"HEAD:refs/heads/{branch}")
    if pushed.returncode != 0:
        return f"push failed: {pushed.stderr.strip()[:200]}"
    return None


def settle(plan: dict, start: Start, worktree: Path, branch: str, linear_id: str,
           host: str) -> None:
    """Turn a `done` run into `failed` when its work did not reach the remote.
    Any other state already says the run did not deliver, so it is left alone."""
    if plan.get("state") != "done":
        return
    error = ship(start, worktree, branch, linear_id, host)
    if error:
        plan.update(state="failed", error=error)
