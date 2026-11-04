"""cwd recovery for Claude Code Bash calls (pattern from github.com/ddaanet/cwd-safety).

Claude Code keeps the shell cwd between Bash calls. A bare `cd` out of the repo moves the
session outside Git, after which the outside-Git gate denies every mutating tool, including
the `cd` back, and the session is locked. One narrow rule, which grants no new authority:
outside Git, a Bash call whose whole text is one of a few exact strings is allowed.

The check never parses the command or predicts Bash word expansion (shlex/pathlib got that
wrong three ways: CDPATH, logical `..`, quoted `~`). It compares the text, with only
surrounding spaces, tabs and newlines removed, against exactly one string: `cd "<root>"`,
the literal value of CLAUDE_PROJECT_DIR in double quotes (the form the deny message gives).
Variable forms such as `cd "$CLAUDE_PROJECT_DIR"` are not accepted: Claude Code does not
export CLAUDE_PROJECT_DIR into the Bash tool environment, so they expand to `cd ""`, which
succeeds without moving the session back into Git.

The root must be absolute, have no `..` component, contain no character that Bash treats
specially inside double quotes, and be the top level of a Git checkout as Git itself reports
it (`git rev-parse --show-toplevel`), not merely a directory holding a `.git` entry. For those strings Bash does no word
splitting, globbing or tilde expansion, and an absolute path skips CDPATH.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from setup_common import _normalise_tool_name

# Only the characters Bash itself treats as word separators around a simple command.
_SURROUNDING_WS = " \t\n"
# Characters that keep meaning inside double quotes, plus control characters.
_UNSAFE_IN_QUOTES = frozenset('$`\\"!') | frozenset(chr(c) for c in range(32)) | {"\x7f"}


def _bash_command(payload: dict[str, Any]) -> str | None:
    name = _normalise_tool_name(payload.get("tool_name") or payload.get("tool") or "")
    if name != "bash":
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    command = tool_input.get("command")
    return command if isinstance(command, str) else None


def project_root_text() -> str | None:
    """CLAUDE_PROJECT_DIR verbatim, when it is safe to quote literally and is a Git checkout."""
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not raw.startswith("/") or ".." in Path(raw).parts:
        return None
    if any(ch in _UNSAFE_IN_QUOTES for ch in raw):
        return None
    try:
        root = Path(raw).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not root.is_dir():
        return None
    try:
        probe = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
             "--no-pager", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0:
        return None
    try:
        top = Path(probe.stdout.strip()).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return raw if top == root else None


def recovery_command() -> str | None:
    """The exact command an agent outside Git may run to return to the project root."""
    raw = project_root_text()
    return f'cd "{raw}"' if raw is not None else None


def is_cd_to_project_root(payload: dict[str, Any]) -> bool:
    """True only when the whole command text is one of the exact recovery strings."""
    command = _bash_command(payload)
    literal = recovery_command()
    if command is None or literal is None:
        return False
    return command.strip(_SURROUNDING_WS) == literal
