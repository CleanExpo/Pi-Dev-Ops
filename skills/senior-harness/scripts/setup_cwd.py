"""cwd recovery for Claude Code Bash calls (pattern from github.com/ddaanet/cwd-safety).

Claude Code keeps the shell cwd between Bash calls. A bare `cd` out of the repo moves the
session outside Git, after which the outside-Git gate denies every mutating tool, including
the `cd` back, and the session is locked. Two narrow rules, which grant no new authority:
outside Git, a Bash call whose whole text is the exact recovery string below is allowed, and
so is a bare `cd <path>` into an existing Git work-tree folder (see `is_cd_into_git_checkout`).

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


def _clean_git_env() -> dict[str, str]:
    """The hook's environment minus every GIT_* override (GIT_DIR, GIT_WORK_TREE, ...).

    Inherited overrides would make `rev-parse --show-toplevel` report a forced worktree
    instead of proving the root is a checkout on its own.
    """
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


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
            env=_clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = probe.stdout
    if probe.returncode != 0 or not out.endswith("\n"):
        return None
    try:
        # Drop only Git's one trailing newline: a root may itself end in a space.
        top = Path(out[:-1]).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return raw if top == root else None


def recovery_command() -> str | None:
    """The exact command an agent outside Git may run to return to the project root."""
    raw = project_root_text()
    return f'cd "{raw}"' if raw is not None else None


def matches_recovery_command(payload: dict[str, Any], literal: str | None) -> bool:
    """True only when the payload is Bash and its whole text is literal (from recovery_command)."""
    command = _bash_command(payload)
    if command is None or literal is None:
        return False
    return command.strip(_SURROUNDING_WS) == literal


def is_cd_to_project_root(payload: dict[str, Any]) -> bool:
    """True only when the whole command text is the exact recovery string."""
    if _bash_command(payload) is None:
        return False  # Not Bash: skip the Git probe entirely.
    return matches_recovery_command(payload, recovery_command())


# `cd <path>` into any Git checkout folder (RA-8135 follow-up). The path must not hold a
# character with meaning to Bash in either form: expansion ($ ` ~ !), quoting (' " \),
# separators and redirection (; & | < > #), grouping and globbing (( ) [ ] { } * ?).
_UNSAFE_IN_PATH = _UNSAFE_IN_QUOTES | frozenset("'~;&|<>#()[]{}*?")


def _cd_target(command: str) -> str | None:
    """The literal path of `cd <path>` or `cd "<path>"`, or None for any other text."""
    text = command.strip(_SURROUNDING_WS)
    if text.startswith('cd "') and text.endswith('"') and len(text) > 5:
        path = text[4:-1]
    elif text.startswith("cd "):
        path = text[3:]
        if " " in path:  # Unquoted: a space would split the word.
            return None
    else:
        return None
    if not path.startswith("/") or ".." in Path(path).parts:
        return None  # Absolute skips CDPATH; no `..` keeps logical and physical cd equal.
    return None if any(ch in _UNSAFE_IN_PATH for ch in path) else path


def _inside_git_work_tree(path: str) -> bool:
    """True only when Git itself, without GIT_* overrides, says path is inside a work tree."""
    if not Path(path).is_dir():
        return False
    try:
        probe = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
             "--no-pager", "-C", path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=10, check=False,
            env=_clean_git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and probe.stdout == "true\n"


def is_cd_into_git_checkout(payload: dict[str, Any]) -> bool:
    """True only when the whole Bash text is `cd <path>` and path is inside a Git work tree."""
    command = _bash_command(payload)
    target = _cd_target(command) if command is not None else None
    return target is not None and _inside_git_work_tree(target)
