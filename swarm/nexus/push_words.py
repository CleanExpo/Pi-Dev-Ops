"""Raise-only check: does any `git push` write a branch the command does not name? (RA-8245)

Five Codex rounds found one root cause: the reader trusted a word's TEXT where Bash
decides its VALUE at run time (`m'a'in`, `"x;" HEAD`, `$'...'`, `pu''sh`, `$g push`,
`printf ... | bash`, backtick bodies, `alias g='git push ...'`). So a push is accepted
only when it is SEEN: a literal `git`, a literal `push`, and every destination a literal
unprotected branch. Anything whose value is unknown where it could be the command, the
subcommand or code is a possible push and returns True: `$'...'` anywhere; a `$` or
backtick word as command name, git subcommand, before `git`, or beside a runner; a shell
fed from a pipe or process substitution; an inline-code interpreter on a line that
mentions push; git options that mention push; `send-pack`, `subtree push`, `git-push`.

Every `...` and $(...) body is cut out and read as a command of its own (Bash runs it
first); the hole is an unknown value. Words are read with `shlex` in POSIX mode, comments
off. A word that may be code (`bash -c`, `eval`, `trap`, `alias g=...`, `--flag=prog`) is
read again to a fixed depth; arguments of data-only commands (`echo`, `grep`) and the
message text of `git commit`/gh are data, never code. Every doubt is True.
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
    options = words[index + 1:len(words) - len(args) - 1]
    if any(_mentions_push(w) for w in options) or (
            any("alias." in w for w in words) and _mentions_push(" ".join(words))):
        return True  # `-c alias.x=push`, `-c core.editor='git push ...'`: config runs code
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
    if call is None and not _is_data_only(words) and any(_unknown(w) for w in words):
        if _unknown(name) or base in _RUNNERS or mentions:
            return True
    return False


# Commands whose arguments are data: they print or search text and never run it.
_DATA_ONLY = frozenset({"echo", "printf", "grep", "egrep", "fgrep", "rg", "true", "false",
                        ":", "test", "[", "ls", "wc", "head", "tail", "cat"})
# For these, only the VALUE of a text flag is data: other options can run a program
# (`git fetch --upload-pack=...`, `gh alias set --shell ...`).
_TEXT_FLAGS = frozenset({"-m", "--message", "--body", "-b", "--title", "-t"})
_GIT_TEXT_SUBS = frozenset({"commit", "tag", "notes", "stash", "merge", "revert"})


def _is_data_only(words: list[str]) -> bool:
    """True only for a literal command known never to execute any of its arguments."""
    name = _command_name(words)
    return name is not None and not _unknown(name) and _base(name) in _DATA_ONLY


def _text_values(words: list[str]) -> set[int]:
    """Indexes of words that are the value of a message/title/body flag of git or gh."""
    name = _command_name(words)
    if name is None or _unknown(name):
        return set()
    call = _git_call(words)
    is_text_git = call is not None and words[call[0]] == name and call[1] in _GIT_TEXT_SUBS
    if not is_text_git and not (_base(name) == "gh" and "alias" not in words):
        return set()
    return {i + 1 for i, w in enumerate(words[:-1]) if w in _TEXT_FLAGS}


def _code_words(words: list[str]) -> list[str]:
    """The words of a simple command that Bash, or the program, may run as code.

    `NAME=value` values always count: `alias g='git push origin HEAD'` defines code
    that a later `g` runs, and `GIT_EDITOR=...` is run by git. Other words count unless
    they are data: every argument of a data-only command (`echo "git push ..."`), and
    the message, title or body text of git commit/tag/merge and gh.
    """
    out = [w.split("=", 1)[1] for w in words
           if _ASSIGNMENT_RE.match(w) and _mentions_push(w)]
    if _is_data_only(words):
        return out
    text = _text_values(words)
    for i, w in enumerate(words):
        if i in text or not any(ch.isspace() for ch in w):
            continue
        if _mentions_push(w) or _unknown(w):
            out.append(w)
            if "=" in w:  # `--upload-pack=<program>`: the value alone is the command
                out.append(w.split("=", 1)[1])
    return out


_SUBSTITUTION_MARK = " $__SUBSTITUTION__ "


def _lift_substitutions(text: str) -> tuple[str, list[str]]:
    """Cut out every `...` and $(...) body; each runs as a command before its host.

    Quoting is ignored on purpose: lifting a span Bash would not run can only add a
    command to check and turn a literal word into an unknown one, so it only raises.
    """
    outer, inners, i = [], [], 0
    while i < len(text):
        if text[i] == "`":
            end = text.find("`", i + 1)
            if end < 0:
                raise _Unreadable("unbalanced backtick")
            inners.append(text[i + 1:end])
            outer.append(_SUBSTITUTION_MARK)
            i = end + 1
        elif text.startswith("$(", i):
            depth, j = 1, i + 2
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            if depth:
                raise _Unreadable("unbalanced $(")
            inners.append(text[i + 2:j - 1])
            outer.append(_SUBSTITUTION_MARK)
            i = j
        else:
            outer.append(text[i])
            i += 1
    return "".join(outer), inners


def _has_implicit_push(command: str, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        return True
    command, inners = _lift_substitutions(command)
    if any(_has_implicit_push(inner, depth + 1) for inner in inners):
        return True
    mentions = _mentions_push(command) or any(_mentions_push(x) for x in inners)
    for before, words, after in _simple_commands(_tokens(command)):
        if _command_is_implicit(before, words, after, mentions):
            return True
        # A word that is itself code: `bash -c '...'`, `eval "..."`, `alias g='...'`.
        if any(_has_implicit_push(word, depth + 1) for word in _code_words(words)):
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
