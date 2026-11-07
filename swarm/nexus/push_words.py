"""Raise-only check: does any `git push` write a branch the command does not name? (RA-8245)

Three Codex rounds found one root cause in three spellings: the reader trusted a word's
TEXT where Bash decides its VALUE at run time. `m'a'in` is `main`; `"x;" HEAD` is one
word then HEAD; `bash -c $'git push origin HEAD'` is ANSI-C quoting, which no Python
tokenizer models. The same blindness covers `git pu${x}sh`, `p=push; git $p`, `$g push`,
`printf ... | bash`, a git alias for push, push plumbing (`send-pack`, `subtree push`,
`git-push`) and another language's inline code that runs git.

So the rule is stated about values, not spellings. A push is accepted only when it is
SEEN: a literal `git` word, a literal `push` subcommand, and every destination a
literal unprotected branch name. Anything whose value is unknown when it could be the
command, the subcommand or code is treated as a possible push and returns True:

- `$'...'` / `$"..."` anywhere (not modelled), or unreadable quoting that mentions push;
- a `$` or backtick word in the command name, a git subcommand, before `git`, in a
  command that also mentions push, or as an argument to a command runner;
- a shell fed from a pipe or a process substitution (its code is not on the line);
- an inline-code interpreter (python, node, perl...) in a command that mentions push;
- a git alias that mentions push, `send-pack`, `subtree push`.

Words are read with `shlex` in POSIX mode (quotes and escapes removed inside a word,
`\\<newline>` joined, `; & | < > ( )` and newline end a command only when unquoted;
comments off). A word that is itself code (`bash -c`, `eval`, `ssh host '...'`,
`git rebase --exec`) is read again, to a fixed depth. Every doubt is True.
"""

from __future__ import annotations

import re
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
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish", "eval", "source", "."})
# Commands that run another command from their arguments.
_RUNNERS = _SHELLS | frozenset({"env", "sudo", "doas", "command", "exec", "nohup", "time",
                                "nice", "timeout", "xargs", "watch", "ssh", "su", "builtin"})
_INTERPRETER_RE = re.compile(r"^(python[0-9.]*|node|nodejs|deno|bun|perl|ruby|php|lua|"
                             r"osascript|R|Rscript|awk|gawk|perl[0-9.]*|tclsh|pwsh)$")
_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SQUEEZE = str.maketrans("", "", "'\"\\")


class _Unreadable(Exception):
    """The command cannot be read as Bash would read it."""


def _mentions_push(text: str) -> bool:
    squeezed = text.replace("\\" + _NL, "").translate(_SQUEEZE).lower()
    return "push" in squeezed or "send-pack" in squeezed


def _unknown(word: str) -> bool:
    return "$" in word or "`" in word


def _base(word: str) -> str:
    return word.rsplit("/", 1)[-1]


def _tokens(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\\" + _NL, ""), posix=True,
                        punctuation_chars=_OPERATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError as exc:  # unbalanced quote or trailing escape
        raise _Unreadable(str(exc)) from exc


def _is_operator(token: str) -> bool:
    return bool(token) and all(ch in _OPERATOR_CHARS for ch in token)


def _simple_commands(tokens: list[str]) -> list[tuple[str, list[str], str]]:
    """(operator before, words, operator after) for every simple command."""
    out, words, before = [], [], ""
    for token in tokens + [""]:
        if token == "" or _is_operator(token):
            if words:
                out.append((before, words, token))
            words, before = [], token
        else:
            words.append(token)
    return out


def _command_name(words: list[str]) -> str | None:
    return next((w for w in words if not _ASSIGNMENT_RE.match(w)), None)


def _git_call(words: list[str]) -> tuple[int, str | None, list[str]] | None:
    """(index of git, subcommand, words after it) for the first git invocation."""
    for i, word in enumerate(words):
        base = _base(word)
        if base.startswith("git-") and len(base) > 4:
            return i, base[4:], words[i + 1:]
        if base != "git":
            continue
        j = i + 1
        while j < len(words) and words[j].startswith("-"):
            j += 2 if words[j] in _GIT_OPTS_WITH_VALUE else 1
        return (i, words[j], words[j + 1:]) if j < len(words) else (i, None, [])
    return None


def _destinations_are_explicit(args: list[str]) -> bool:
    positionals = []
    for token in args:
        if _unknown(token):
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


def _git_is_implicit(words: list[str], call: tuple[int, str | None, list[str]]) -> bool:
    index, sub, args = call
    if any(_unknown(w) for w in words[:index]) or sub is None or _unknown(sub):
        return True  # the program, or the subcommand, is decided at run time
    if any("alias." in w for w in words) and _mentions_push(" ".join(words)):
        return True  # an alias can make any name mean push
    if sub == "push":
        return not _destinations_are_explicit(args)
    return sub == "send-pack" or (sub == "subtree" and "push" in args)


def _command_is_implicit(before: str, words: list[str], after: str, mentions: bool) -> bool:
    name = _command_name(words)
    if name is None:
        return False
    call = _git_call(words)
    if call is not None and _git_is_implicit(words, call):
        return True
    base = _base(name)
    if base in _SHELLS and ("|" in before or after.startswith("<(") or after == "<"):
        return True  # code arrives on stdin or from a file the line does not show
    if mentions and _INTERPRETER_RE.match(base):
        return True  # another language may run git; its code is not Bash
    if call is None and any(_unknown(w) for w in words):
        if _unknown(name) or base in _RUNNERS or mentions:
            return True
    return False


def _has_implicit_push(command: str, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return True
    mentions = _mentions_push(command)
    for before, words, after in _simple_commands(_tokens(command)):
        if _command_is_implicit(before, words, after, mentions):
            return True
        # A word that is itself code: `bash -c '...'`, `eval "..."`, `--exec '...'`.
        for word in words:
            if any(ch.isspace() for ch in word) and (_mentions_push(word) or _unknown(word)):
                if _has_implicit_push(word, depth + 1):
                    return True
    return False


def push_destination_is_implicit(command: str) -> bool:
    """True when any `git push` in `command` may write a branch the text does not name."""
    if "$'" in command or '$"' in command:
        return True  # ANSI-C and locale quoting: values shlex cannot compute
    if not (_mentions_push(command) or _unknown(command) or "|" in command or "<(" in command):
        return False
    if len(command) > _MAX_CHARS:
        return True
    try:
        return _has_implicit_push(command, 0)
    except _Unreadable:
        return _mentions_push(command)


__all__ = ["push_destination_is_implicit"]
