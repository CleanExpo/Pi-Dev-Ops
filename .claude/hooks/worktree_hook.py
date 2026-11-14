#!/usr/bin/env python3
"""WorktreeCreate / WorktreeRemove hook for Claude Code.

Claude Code sends the event as JSON on stdin. It does not set WORKTREE_DIR or
WORKTREE_BRANCH; the old one-line hooks read those and so asked git for a branch
with an empty name.

  worktree_hook.py create   stdin {"name": "<slug>", ...}; prints the new path as the last stdout line
  worktree_hook.py remove   stdin {"worktree_path": "<abs path>", ...}

Create puts the worktree at <repo>/.claude/worktrees/<name> on branch worktree-<name>.
Remove only touches paths inside <repo>/.claude/worktrees, and deletes the branch only
if git says it is fully merged. All git output goes to stderr. Fails closed (exit 1).
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


def create(repo: Path, event: dict) -> int:
    name = event.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        return fail(f"refusing worktree name {name!r}: need letters, digits, '-' or '_'")
    target = repo / ".claude" / "worktrees" / name
    if target.exists():
        return fail(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    if git(repo, "worktree", "add", str(target), "-b", f"worktree-{name}").returncode != 0:
        return fail("git worktree add failed")
    print(target)
    return 0


def remove(repo: Path, event: dict) -> int:
    raw = event.get("worktree_path")
    if not isinstance(raw, str) or not raw:
        return fail("no worktree_path in the event")
    target, root = Path(raw).resolve(), (repo / ".claude" / "worktrees").resolve()
    if root not in target.parents:
        return fail(f"refusing to remove {target}: not inside {root}")
    if not target.exists():
        return 0
    if git(repo, "worktree", "remove", str(target), "--force").returncode != 0:
        return fail("git worktree remove failed")
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
