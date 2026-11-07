"""Fail-closed `git push` target parser for the autonomy ladder (RA-7383).

Split out of `autonomy_rules.py` under the repo's 300-line rule, and the split
is not just bookkeeping: this file has one job and one export, and the rule
TABLE it was carved out of is data with no logic. Keeping a parser inside a data
table is how the table stops being readable as a table.

WHAT THIS IS FOR. Two L3 rules in `autonomy_rules._L3_BASH` match a push to a
protected branch using a whole-line `[^\\n]*` gap, so ANY later protected token
satisfies them: a feature-branch push chained with a read-only
`git rev-parse origin/main` classifies L3 though nothing touches a protected
ref. Fail-closed, but three redundant approval prompts.

WHY THIS IS NOT A FOURTH REGEX. Three narrowings were measured against a bash
oracle across three review rounds and every one opened a real bypass, because
each tried to REPLACE the match with a smarter one — so any imperfection in the
parse REMOVED protection. Splitting on separators was quote-blind (59-75 leaks);
masking quoted spans lost to escapes, backticks and `${...}` (75, then 15);
constraining the gap to argument units swallowed a quoted protected ref whole,
dropping `git push origin "main"` from L3 to L1 (18 cases), and letting the gap
cross quotes made it catastrophically backtracking (42 s — a DoS in a PreToolUse
hook). The full post-mortem is in `tests/test_autonomy_ladder_l3_segments.py`.

THE FAILURE DIRECTION IS INVERTED HERE. The whole-line match stays authoritative
and is never weakened. This module can only ever SUBTRACT, and only when it is
certain — so an imperfect parse costs a redundant prompt, never a bypass.
Certainty is defined by refusal, not by cleverness: any quote, `$`, backtick or
backslash ANYWHERE in the push segment and the parse is abandoned. That single
rule is what retires all three prior leak classes at once — every one of them is
a command this refuses to reason about.

ROUND 4 WAS ITSELF ATTACKED, and the first draft leaked twice. `git push origin
HEAD` and `git push origin @` name whatever branch is checked out — possibly a
protected one — but the literal tokens `head` and `@` are not protected branch
names, so the parser read them as safe destinations and subtracted the verdict.
Both were found by an adversarial probe, not by review, and both are closed here
by refusing any destination that is not a plain literal branch name. The lesson
generalises past this file: a token-equality check answers "is this string a
protected branch", which is not the question. The question is "does this write a
protected branch", and the two diverge wherever git accepts an indirection.
Hence `_PLAIN_REF_RE` — refuse the whole class, not the two spellings that
happened to be found.

The probe's corpus is committed alongside the RA-7382 corpus so it runs on every
change, and it also surfaced RA-7409: a pre-existing gap where `--mirror` and
`--all` write protected refs without naming any, so the whole-line rules never
match and this parser is never consulted. That is a WIDENING and is deliberately
not fixed here; it is pinned as a strict xfail.
"""

from __future__ import annotations

import re

# Abandon the parse on sight of any of these. Quoting, substitution and escaping
# are exactly where designs 1-3 died; this refuses to model them at all.
_UNPARSEABLE_CHARS = frozenset("\"'`$\\")

# Shell separators that end the push command. Only meaningful because a segment
# containing any quoting has already been refused, so these cannot be data.
_SEPARATORS = ("&&", "||", ";", "|", "\n", "&")

# Value-less push flags. An allowlist, not a denylist: an unknown flag might take
# a separate value (`-o <value>`), which would shift the positional arguments and
# mis-identify the target. Unknown flag -> refuse.
_SAFE_PUSH_FLAGS = frozenset({
    "-f", "--force", "--force-with-lease", "-u", "--set-upstream", "-q", "--quiet",
    "-v", "--verbose", "--tags", "--follow-tags", "--all", "--dry-run", "-n",
    "--no-verify", "--atomic", "--porcelain", "--progress", "--no-progress",
    "--prune", "--thin", "--no-thin", "--ipv4", "--ipv6", "-4", "-6",
})

_PROTECTED_REFS = frozenset({"main", "master", "prod", "production"})

# Destinations whose real target is only knowable at runtime. `HEAD` and `@` name
# whatever branch happens to be checked out, which may be a protected one, so
# `git push origin HEAD` is exactly as unsafe as a bare push with no refspec.
_UNRESOLVABLE_REFS = frozenset({"head", "@"})

# The only destination shape this parser will read literally. Anything else — a
# glob, an `@{-1}` reflog selector, a `^`/`~` walk, an empty destination — is
# refused rather than guessed at. Same principle as `_UNPARSEABLE_CHARS`: the
# subtraction only happens where the target is certain.
_PLAIN_REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

# Explicit bounds — this runs inside a PreToolUse hook, so unbounded work is its
# own failure mode. Both overruns refuse rather than truncate.
_MAX_COMMAND_CHARS = 10_000
_MAX_PUSH_OCCURRENCES = 32


def _refspec_target(token: str) -> str:
    """The branch a refspec would write to, lowercased.

    `HEAD:refs/heads/main` -> `main`; `+feature/x` -> `feature/x`. Takes the text
    after the LAST colon so `HEAD:refs/heads/x` resolves to the destination, not
    the source — pushing FROM main TO a feature branch is not a protected write,
    and that is also why `HEAD` is refused only as a destination.
    """
    dest = token.rsplit(":", 1)[-1].lstrip("+")
    for prefix in ("refs/heads/", "heads/"):
        if dest.startswith(prefix):
            dest = dest[len(prefix):]
    return dest.lower()


def _push_argument_starts(command: str, lowered: str) -> list[int] | None:
    """Offsets just past each `git push` verb, or None if the scan must refuse.

    Matching `git` then `push` across arbitrary whitespace, rather than with a
    regex, keeps this linear: the file it came from documents a 42-second
    backtracking pattern, and a hook that hangs is a DoS.
    """
    starts: list[int] = []
    idx = lowered.find("git")
    while idx != -1:
        if len(starts) >= _MAX_PUSH_OCCURRENCES:
            return None
        after = lowered[idx + 3:]
        stripped = after.lstrip()
        preceded_by_word_char = idx > 0 and (
            lowered[idx - 1].isalnum() or lowered[idx - 1] in "_-"
        )
        if stripped.startswith("push") and not preceded_by_word_char:
            starts.append(idx + 3 + (len(after) - len(stripped)) + 4)
        idx = lowered.find("git", idx + 1)
    return starts


def _segment_targets_are_unprotected(segment: str) -> bool:
    """True only when every refspec in one `git push` segment is provably safe."""
    if any(ch in _UNPARSEABLE_CHARS for ch in segment):
        return False  # quoting/substitution/escaping — refuse to reason about it

    positionals = []
    for token in segment.split():
        if token.startswith("-"):
            base = token.split("=", 1)[0]
            if token not in _SAFE_PUSH_FLAGS and base not in _SAFE_PUSH_FLAGS:
                return False  # unknown flag may take a value and shift positionals
            continue
        positionals.append(token)

    # positionals[0] is the remote; the rest are refspecs.
    if len(positionals) < 2:
        return False  # no explicit refspec: pushes the current branch, unknown
    if positionals[0].lower() in _PROTECTED_REFS:
        return False  # a remote named like a protected branch — too odd to trust

    for token in positionals[1:]:
        dest = _refspec_target(token)
        if not _PLAIN_REF_RE.match(dest):
            return False  # glob, reflog selector, revision walk, or empty
        if dest in _UNRESOLVABLE_REFS or dest in _PROTECTED_REFS:
            return False
    return True


def push_targets_are_all_unprotected(command: str) -> bool:
    """True only when EVERY `git push` in `command` provably targets a safe ref.

    False on any doubt whatsoever — an unreadable segment, an unknown flag, a
    bare push with no refspec (which pushes the *current* branch, possibly main),
    more pushes than the bound allows, or a protected destination. The caller
    treats False as "leave the whole-line verdict alone", so every False is a
    redundant prompt at worst and never a bypass.
    """
    if not command or len(command) > _MAX_COMMAND_CHARS:
        return False

    lowered = command.lower()
    starts = _push_argument_starts(command, lowered)
    if not starts:
        # None -> over the occurrence bound; [] -> the push rules matched but no
        # `git push` is parseable here. Both are refusals.
        return False

    for start in starts:
        end = len(command)
        for sep in _SEPARATORS:
            pos = command.find(sep, start)
            if pos != -1:
                end = min(end, pos)
        if not _segment_targets_are_unprotected(command[start:end]):
            return False
    return True


__all__ = ["push_targets_are_all_unprotected"]
