r"""app/server/bash_segments.py — reading a shell command into checkable pieces.

Split from `tool_gate.py` under the 300-line rule, along a real seam: that module
decides POLICY (what the unattended loop may do), this one answers a narrower
mechanical question — given one command string, which pieces should the denylist
be applied to, and does any rule match. Nothing here knows about permissions.

RA-7412 — CLOSING THE QUOTE-BLIND SPLIT, WITHOUT WEAKENING WHAT ALREADY WORKS.

THE LEAK. The gate splits on `SHELL_SEP` before testing `SEGMENT_RULES`. A `;`
inside a quoted ARGUMENT is data, not a command boundary, but the split cannot
tell, so it severs the signature and neither half matches. Two commands reached
the unattended loop ALLOWED: a production deploy, and a hard reset that destroys
uncommitted work — both carrying a `;` inside a quoted argument. Both are denied
correctly once the quoted span is removed, which is what proved it was the split
and not the rules. RA-7382 measured 59-75 leaks of this exact shape against the
INTERACTIVE gate and rejected segmentation for it. This path kept it, and here
there is no human to catch a miss.

WHY NOT SIMPLY TEST THE WHOLE COMMAND TOO. Tried first; the existing suite
rejected it, and was right to. Several rules scan forward with `[^\n]*`, so over
an uncut chain they collect tokens from unrelated later commands:

    rm notes.txt && tar -rvf archive.tar src   -> `rm` + a LATER `-rvf` = rm-rf

Segmentation is not merely weaker than whole-command matching; for those rules it
is what makes them correct. The same is true in the other direction for
`sql-delete-no-where`, whose `(?![\s\S]*\bWHERE\b)` lookahead is suppressed by a
WHERE in an unrelated later statement. Neither reading dominates, so this ADDS a
pass rather than replacing one.

THE ADDED PASS: split a quote-MASKED copy, then run the same rules on it. The
masking only has to be good enough to add a denial — the caller keeps its original
passes untouched, so a masking mistake can never REMOVE protection. That is the
same inversion RA-7383 used, and it is what makes masking safe here when RA-7382
found it unsafe there: that design masked in order to NARROW a match.
"""
from __future__ import annotations

import re

from swarm.nexus.autonomy_ladder import (
    SEGMENT_RULES as _SEGMENT_RULES,
    SHELL_SEP as _SHELL_SEP,
    strip_git_global_opts as _strip_git_global_opts,
)

_QUOTE_CHARS = frozenset("\"'")
# Escapes, backticks and `$(`/`${` defeat a simple masker (RA-7382 measured it).
# Their presence does not disable the pass — that would make the bypass one `$`
# away — it falls back to the strictest reading instead: the whole command as a
# single segment.
_MASK_UNSAFE = frozenset("\\`$")
_QUOTED_SPAN = re.compile(r"\"[^\"]*\"|'[^']*'")

# THREE THINGS `_requoted_segments` GETS RIGHT, each of which it got wrong first
# and each caught by measurement rather than by reading the code:
#
# 1. The trigger covers everything that can HIDE a separator, not just quotes.
#    Testing for `"`/`'` alone left ``vercel --meta note=`echo a;b` --prod``
#    leaking — it carries no quote character, so the pass was skipped entirely and
#    the ordinary split severed the signature at the backticked `;`. A trigger
#    narrower than the set of hiding places is a bypass one backtick wide.
#
# 2. An unclosed quote invalidates the mask, so it takes the strict path. There is
#    no complete span to blank in `vercel -e "a;b --prod`, so masking is a no-op
#    and the split severs exactly as before. The leftover-quote test runs on the
#    MASKED text on purpose: an apostrophe inside a double-quoted span
#    (`echo "don't"`) reads as unbalanced before masking and balanced after, so
#    counting up front would send ordinary commands down the strict path.
#
# 3. The `git rm` exemption does NOT travel with the strict path. It is a claim
#    about ONE command — `git rm -rf x` is recoverable — and `re.match` anchors it
#    at the start, so on an uncut chain it exempted everything after the first
#    command too:
#        git rm x && vercel -e "a;$X" --prod   -> allowed
#        ls        && vercel -e "a;$X" --prod  -> denied   (the control)
#    Prefixing a chain with `git rm x &&` must not launder the rest of it.


def requoted_segments(cmd: str) -> tuple[list[str], bool]:
    """Segments for the ADDED pass, and whether the `git rm` exemption applies.

    No segments means the ordinary split is already correct. The flag is False
    when the single "segment" is the whole uncut command. See the notes above the
    constants for why each branch is shaped the way it is.
    """
    has_quote = any(ch in _QUOTE_CHARS for ch in cmd)
    has_unsafe = any(ch in _MASK_UNSAFE for ch in cmd)
    if not has_quote and not has_unsafe:
        return [], True
    if has_unsafe:
        return [cmd], False
    # Blank each quoted span so separators inside it stop being boundaries. A
    # space, not a placeholder token, so the masked text cannot invent a match.
    masked = _QUOTED_SPAN.sub(lambda m: " " * len(m.group(0)), cmd)
    # A quote left over means a span never closed, so the mask is not trustworthy
    # — `vercel -e "a;b --prod` has no complete span to blank and would split at
    # the quoted `;` exactly as before. Counting quotes up front would be worse
    # than this: an apostrophe inside a double-quoted span (`echo "don't"`) reads
    # as unbalanced before masking and as balanced after, so the check has to run
    # on the masked text or it sends ordinary commands down the strict path.
    if any(ch in _QUOTE_CHARS for ch in masked):
        return [cmd], False
    return [s.strip() for s in _SHELL_SEP.split(masked)], True


def segment_denial(seg: str, git_rm_exempt: bool = True) -> str | None:
    """The label of the first `_SEGMENT_RULES` hit on a segment, or None.

    Carries the RA-7386 contract with it: the original AND the global-option
    normalised form are both tested, and the `git rm` exemption is applied PER
    FORM, so `git -C . rm -rf .` stays denied while `git rm -rf cached` does not.
    """
    for cand in (seg, _strip_git_global_opts(seg)):
        if not cand:
            continue
        if git_rm_exempt and re.match(r"git\s+rm\b", cand, re.IGNORECASE):
            continue  # `git rm` is tracked/recoverable — not the rm-rf rule
        for label, pat in _SEGMENT_RULES:
            if pat.search(cand):
                return label
    return None


__all__ = ["requoted_segments", "segment_denial"]
