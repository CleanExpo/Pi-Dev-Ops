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
  cannot push, and every option in `<args>` on that subcommand's exact list, so no
  option can name a program to run, a file to write or work to discard (round 7);
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
_COUNT_RE = re.compile(r"^-n?[0-9]+$")  # `git log -5`, `-n5`
# Subcommands that cannot push, each with the EXACT options it may carry. An option off
# its list keeps L3: some select a program to run (`merge -s <name>` runs
# git-merge-<name>, `fetch --upload-pack=<prog>`), some write files (`diff --output=`),
# some discard work (`switch -f`). `checkout` is absent: `git checkout <file>` throws
# away local edits and a path cannot be told apart from a branch by its text.
_LOCAL_OPTIONS: dict[str, frozenset[str]] = {
    "merge": frozenset({"--no-edit", "--ff-only", "--no-ff", "--ff", "--squash", "--no-commit",
                        "--abort", "--continue", "-q", "--quiet", "--stat", "--no-stat"}),
    "fetch": frozenset({"--prune", "-p", "--tags", "--no-tags", "-q", "--quiet", "--all",
                        "--dry-run"}),
    "status": frozenset({"-s", "--short", "-b", "--branch", "--porcelain"}),
    "log": frozenset({"--oneline", "--graph", "--decorate", "--stat", "--name-only",
                      "--name-status", "--no-merges", "--merges", "--reverse"}),
    "diff": frozenset({"--stat", "--name-only", "--name-status", "--cached", "--staged",
                       "--check", "--shortstat", "--quiet", "--exit-code"}),
    "show": frozenset({"--stat", "--name-only", "--name-status", "--oneline", "--no-patch"}),
    "rev-parse": frozenset({"--abbrev-ref", "--short", "--verify", "--show-toplevel",
                            "--git-dir", "--is-inside-work-tree", "-q", "--quiet"}),
    "branch": frozenset({"--show-current", "-a", "-r", "-v", "-vv", "--list", "--all",
                         "--remotes", "--merged", "--no-merged", "--contains"}),
    "switch": frozenset({"-c", "--create", "--detach"}),
}


def _is_plain_local_git(part: str) -> bool:
    words = part.split()
    if not words or words[0] != "git":
        return False
    if any(not _PLAIN_WORD_RE.match(w) or w.lower() == "push" or "::" in w for w in words):
        return False  # `::` is a transport helper (`ext::<cmd>`), which runs a program.
    i = 1
    if words[i:i + 1] == ["-C"]:
        i += 2
    while words[i:i + 1] == ["--no-pager"]:
        i += 1
    if i >= len(words) or words[i] not in _LOCAL_OPTIONS:
        return False
    allowed = _LOCAL_OPTIONS[words[i]]
    return all(w in allowed or (words[i] == "log" and _COUNT_RE.match(w))
               for w in words[i + 1:] if w.startswith("-"))


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
