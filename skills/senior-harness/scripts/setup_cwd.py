"""cwd recovery for Claude Code Bash calls (pattern from github.com/ddaanet/cwd-safety).

Claude Code keeps the shell cwd between Bash calls. A bare `cd` out of the repo moves the
session outside Git, after which the outside-Git gate denies every mutating tool, including
the `cd` back, and the session is locked. One narrow rule, which grants no new authority:
outside Git, a Bash call that is exactly `cd <project root>` is allowed, where the project
root is CLAUDE_PROJECT_DIR (the session's start root) and is itself a Git checkout.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from setup_common import _normalise_tool_name


def _bash_command(payload: dict[str, Any]) -> str | None:
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    if name != "bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) and command.strip() else None


def _project_root() -> Path | None:
    raw = os.environ.get("CLAUDE_PROJECT_DIR")
    if not raw:
        return None
    try:
        root = Path(raw).resolve(strict=True)
    except OSError:
        return None
    return root if (root / ".git").exists() else None


def _resolve_target(token: str, cwd: str) -> Path | None:
    """Expand only $CLAUDE_PROJECT_DIR / ${CLAUDE_PROJECT_DIR} and ~; any other expansion is unknown."""
    expanded = re.sub(r"\$\{CLAUDE_PROJECT_DIR\}|\$CLAUDE_PROJECT_DIR\b",
                      lambda _m: os.environ.get("CLAUDE_PROJECT_DIR", "\0"), token)
    if "\0" in expanded or "$" in expanded or "`" in expanded or token == "-":
        return None
    try:
        return (Path(cwd) / Path(expanded).expanduser()).resolve()
    except (OSError, ValueError):
        return None


def is_cd_to_project_root(payload: dict[str, Any]) -> bool:
    """True only for a whole command `cd <root>` (no chaining, no other words)."""
    command = _bash_command(payload)
    root = _project_root()
    if command is None or root is None or re.search(r"[\n;&|<>`()'\\]|\$\(", command):
        # Single quotes and backslashes change whether Bash expands $CLAUDE_PROJECT_DIR;
        # shlex.split hides that, so recovery accepts only unquoted or double-quoted forms.
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if len(argv) != 2 or argv[0] != "cd" or not _is_provable_target(argv[1]):
        return False
    return _resolve_target(argv[1], str(payload.get("cwd") or "/")) == root


def _is_provable_target(token: str) -> bool:
    """Absolute and free of `..`, so Bash's logical cd and Path.resolve land in the same place.

    Bash searches CDPATH for a relative name, and drops `link/..` as text before following any
    symlink, while Path.resolve follows the link first; either can put Bash somewhere else.
    """
    expanded = re.sub(r"\$\{CLAUDE_PROJECT_DIR\}|\$CLAUDE_PROJECT_DIR\b",
                      lambda _m: os.environ.get("CLAUDE_PROJECT_DIR", ""), token)
    absolute = expanded.startswith(("/", "~/")) or expanded == "~"
    return absolute and ".." not in Path(expanded).parts
