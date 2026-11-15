#!/usr/bin/env python3
"""WorktreeCreate / WorktreeRemove hook for Claude Code.

Claude Code sends the event as JSON on stdin. It does not set WORKTREE_DIR or
WORKTREE_BRANCH; the old one-line hooks read those and so asked git for a branch
with an empty name.

  worktree_hook.py create   stdin {"name": "<slug>", ...}; prints the new path as the last stdout line
  worktree_hook.py remove   stdin {"worktree_path": "<abs path>", ...}

Create puts the worktree at <repo>/.claude/worktrees/<name> on branch worktree-<name>.
Remove takes only a folder create could have made (owned_target decides for both), and
deletes the branch only if git says it is fully merged. It never forces: a worktree
holding modified or untracked files, or commits on no local branch (a tag or a remote
ref does not count), is left in place (exit 1). Files the repository ignores (caches,
node_modules) and commits only its reflog remembers do go with the worktree. All git
output goes to stderr. Fails closed (exit 1).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")  # used with fullmatch: `$` would accept a trailing newline


def fail(message: str) -> int:
    print(f"worktree_hook: {message}", file=sys.stderr)
    return 1


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    sys.stderr.write(proc.stdout + proc.stderr)
    return proc


def owned_target(repo: Path, name: object) -> Path:
    """The one rule for which folder this hook may touch. Create and remove both ask here; nothing else decides.

    It is <repo>/.claude/worktrees/<name>: a plain name, and no symlink at .claude, at worktrees or at the name
    itself, so the folder really is inside the project. Anything else raises ValueError with the reason.
    """
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(f"worktree name {name!r} needs letters, digits, '-' or '_'")
    target = repo / ".claude" / "worktrees" / name
    if target.resolve() != repo.resolve() / ".claude" / "worktrees" / name:
        raise ValueError(f"{target} is reached through a symlink that leads somewhere else")
    return target


def create(repo: Path, event: dict) -> int:
    try:
        target = owned_target(repo, event.get("name"))
    except ValueError as why:
        return fail(f"refusing to create: {why}")
    if target.exists():
        return fail(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    if git(repo, "worktree", "add", str(target), "-b", f"worktree-{target.name}").returncode != 0:
        return fail("git worktree add failed")
    print(target)
    return 0


def remove(repo: Path, event: dict) -> int:
    raw = event.get("worktree_path")
    if not isinstance(raw, str) or not raw:
        return fail("no worktree_path in the event")
    try:  # only a folder create could have made: the asked path must be the owned folder for its own last part
        target = owned_target(repo, Path(raw).name)
        if Path(raw).resolve() != target.resolve():
            raise ValueError(f"it is not a folder directly inside {target.parent}")
    except ValueError as why:
        return fail(f"refusing to remove {raw}: {why}")
    if not target.exists():
        return 0
    # HEAD and the refs git keeps per worktree go when the worktree goes; only a local branch keeps a commit after that.
    loose = git(target, "rev-list", "--max-count=1", "HEAD", "--glob=refs/bisect", "--glob=refs/worktree",
                "--glob=refs/rewritten", "--not", "--branches")
    if loose.returncode != 0 or loose.stdout.strip():
        return fail(f"refusing to remove {target}: it holds commits on no branch, or git could not tell; "
                    "make a branch for them first")
    # No --force: git itself refuses a worktree that holds modified or untracked files, so unsaved work is kept.
    if git(repo, "worktree", "remove", str(target)).returncode != 0:
        return fail(f"{target} was not removed; if it holds uncommitted or untracked files, commit or delete them")
    git(repo, "branch", "-d", f"worktree-{target.name}")  # merged branches only; a refusal is fine
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if mode not in {"create", "remove"}:
        return fail("usage: worktree_hook.py create|remove")
    if not project or not Path(project).is_dir():
        return fail("CLAUDE_PROJECT_DIR is not set to a folder")
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return fail("stdin is not JSON")
    if not isinstance(event, dict):
        return fail("stdin JSON is not an object")
    return create(Path(project), event) if mode == "create" else remove(Path(project), event)


if __name__ == "__main__":
    sys.exit(main())
