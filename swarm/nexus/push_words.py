"""Raise-only check: does any `git push` write a branch the command does not name? (RA-8245)

Two Codex review rounds found the same class of leak in a character-level parse:
`git push origin m'a'in` is `main` to Bash, and `git push origin "x;" HEAD` pushes
HEAD because the `;` is inside quotes. A parse that splits on separators without
knowing about quotes, or that deletes quotes after splitting, reads both wrong.

So this module reads the command as Bash does first, with `shlex` in POSIX mode:
quotes and escapes are removed inside a word, `\\<newline>` joins two lines, and
`; & | < > ( )` and newline end a simple command only when they are unquoted.
Unbalanced quoting cannot be read and is refused. Comment handling is off, so a
`#` can never hide what follows it. Then, in every simple command (and, to a fixed
depth, in every word that is itself a command string, for `bash -c` and `eval`),
a `git ... push` must name every destination as a literal, unprotected branch.
Anything else - no refspec, HEAD, @, `$`, backtick, an unknown flag, `--all`,
`--mirror`, a protected name - returns True, which the classifier turns into L3.

The failure direction is fixed: this can only RAISE a verdict. Every doubt is True.
"""

from __future__ import annotations

import shlex

try:
    from .push_targets import (
        _PLAIN_REF_RE, _PROTECTED_REFS, _SAFE_PUSH_FLAGS, _UNRESOLVABLE_REFS,
        _refspec_target,
    )
except ImportError:  # pragma: no cover - exercised by the by-path test loader
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "swarm_nexus_push_targets_for_words", _Path(__file__).with_name("push_targets.py"))
    _pt = _ilu.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_pt)
    _PLAIN_REF_RE, _PROTECTED_REFS = _pt._PLAIN_REF_RE, _pt._PROTECTED_REFS
    _SAFE_PUSH_FLAGS, _UNRESOLVABLE_REFS = _pt._SAFE_PUSH_FLAGS, _pt._UNRESOLVABLE_REFS
    _refspec_target = _pt._refspec_target

_NL = "\n"
_OPERATOR_CHARS = "();<>|&" + _NL
_MAX_CHARS = 10_000
_MAX_DEPTH = 3
_BROADCAST_FLAGS = frozenset({"--all", "--mirror"})
# Git global options whose value is the NEXT word, so it is not a subcommand.
_GIT_OPTS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                                  "--exec-path", "--super-prefix", "--config-env"})


class _Unreadable(Exception):
    """The command cannot be read as Bash would read it."""


def _words(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\\" + _NL, ""), posix=True,
                        punctuation_chars=_OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:  # unbalanced quote or trailing escape
        raise _Unreadable(str(exc)) from exc


def _simple_commands(words: list[str]) -> list[list[str]]:
    commands, current = [], []
    for word in words:
        if word and all(ch in _OPERATOR_CHARS for ch in word):
            commands.append(current)
            current = []
        else:
            current.append(word)
    commands.append(current)
    return [c for c in commands if c]


def _push_args(words: list[str]) -> list[str] | None:
    """The words after `push` when this simple command runs `git push`, else None."""
    for i, word in enumerate(words):
        if word != "git" and not word.endswith("/git"):
            continue
        j = i + 1
        while j < len(words) and words[j].startswith("-"):
            j += 2 if words[j] in _GIT_OPTS_WITH_VALUE else 1
        if j < len(words) and words[j] == "push":
            return words[j + 1:]
    return None


def _destinations_are_explicit(args: list[str]) -> bool:
    positionals = []
    for token in args:
        if "$" in token or "`" in token:
            return False  # substitution: the value is unknown
        if token.startswith("-"):
            base = token.split("=", 1)[0]
            if base in _BROADCAST_FLAGS:
                return False
            if token not in _SAFE_PUSH_FLAGS and base not in _SAFE_PUSH_FLAGS:
                return False  # may take a value and shift the positionals
            continue
        positionals.append(token)
    if len(positionals) < 2:
        return False  # no refspec: pushes the current branch, whatever it is
    for token in positionals[1:]:
        dest = _refspec_target(token)
        if not _PLAIN_REF_RE.match(dest) or dest in _UNRESOLVABLE_REFS or dest in _PROTECTED_REFS:
            return False
    return True


def _has_implicit_push(command: str, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return True
    for words in _simple_commands(_words(command)):
        args = _push_args(words)
        if args is not None and not _destinations_are_explicit(args):
            return True
        # `bash -c '...'`, `eval "..."`: a word that is itself a command string.
        for word in words:
            if any(ch.isspace() for ch in word) and "push" in word:
                if _has_implicit_push(word, depth + 1):
                    return True
    return False


def push_destination_is_implicit(command: str) -> bool:
    """True when any `git push` in `command` may write a branch the text does not name."""
    if "push" not in command.lower():
        return False
    if len(command) > _MAX_CHARS:
        return True
    try:
        return _has_implicit_push(command, 0)
    except _Unreadable:
        return True


__all__ = ["push_destination_is_implicit"]
