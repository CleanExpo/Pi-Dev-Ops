"""A local `git merge` is L1 only when the whole command is plain git (RA-8245).

`git merge` was a blanket L3 signature. That blocked an agent from integrating main
into its own feature branch, the step before every PR, while protecting nothing a
merge itself can do: it only moves the checked-out branch, and the reflog undoes it.

But the blanket rule also covered every command that merely CONTAINED a merge, and
some of those push: `git merge feature/x && git push origin HEAD` lands on main from
a main checkout (Codex, RA-8245 round 1). Reading arbitrary Bash to find every hidden
push did not converge over six review rounds, so this rule does not try. It lowers
the tier only for one exact shape and keeps the old L3 for everything else:

- the command is one or more simple commands joined by `&&`, `||`, `;` or newline;
- each is `git [-C <dir>] [--no-pager] <sub> <args>`, with `<sub>` a subcommand that
  neither pushes nor runs code from its arguments;
- every word is plain text: no `$`, backtick, quote, backslash, glob, redirection,
  pipe, bracket or `push`.

Any other command containing a merge stays L3, exactly as before this change. A
direct push to main is also refused by GitHub, whose protection on main requires a
PR and binds admins; this rule never relies on that.
"""

from __future__ import annotations

import re

_MERGE_RE = re.compile(r"\bgit\s+merge(?![-\w])", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"&&|\|\||;|\n")
_PLAIN_WORD_RE = re.compile(r"^[A-Za-z0-9._/@:^~=+,-]+$")
# Subcommands that cannot push and do not execute an argument as code.
_LOCAL_SUBS = frozenset({"merge", "fetch", "status", "log", "diff", "show", "rev-parse",
                         "branch", "switch", "checkout"})


def _is_plain_local_git(part: str) -> bool:
    words = part.split()
    if not words or words[0] != "git":
        return False
    if any(not _PLAIN_WORD_RE.match(w) or w.lower() == "push" for w in words):
        return False
    i = 1
    if words[i:i + 1] == ["-C"]:
        i += 2
    while words[i:i + 1] == ["--no-pager"]:
        i += 1
    return i < len(words) and words[i] in _LOCAL_SUBS


def merge_needs_a_human(command: str, normalised: str = "") -> bool:
    """True when either spelling contains a `git merge` and the RAW command is not plain.

    `normalised` has git global options stripped, so it finds `git -c x=y merge`;
    plainness is judged on the raw text, where that `-c` is still visible.
    """
    if not (_MERGE_RE.search(command) or _MERGE_RE.search(normalised)):
        return False
    parts = [p for p in _SEPARATOR_RE.split(command) if p.strip()]
    return not parts or not all(_is_plain_local_git(p) for p in parts)


__all__ = ["merge_needs_a_human"]
