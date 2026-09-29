#!/usr/bin/env python3
"""Reject reviewer findings whose quoted_line does not exist in the diff.

A blocking finding must anchor to a line that literally appears in the unified
diff, under the file it names. Anything else is an unanchored claim and cannot
block a release.

Usage:  verify_citations.py <reviewer.json> <diff.txt>
Exit 0 = every blocking finding is anchored. Exit 2 = at least one is not.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata


def _canon(s: str) -> str:
    """Canonical Unicode equivalence, and NOTHING else.

    NFC belongs here: canonical composition maps different SPELLINGS of the same
    character onto one value, which is Unicode's own definition of "the same text". A
    reviewer quoting the NFC form of `café_call` was otherwise rejected against a diff
    line holding the canonically equivalent NFD form (review 2026-08-09, P1).

    The quote-style and dash-style substitutions that used to sit here did NOT have
    that property, and the previous commit's claim that they could not manufacture a
    line was wrong. `'` and `’` are different characters that can change what a string
    literal contains; folding them let a fabricated line — a real source line with its
    quotes swapped, or its em dash replaced by a hyphen — compare equal to one that
    exists and pass the unrestricted whole-line hatch (review 2026-08-09, P1). The
    tolerance for a model that retypes typography is not worth a rule that accepts
    text nobody wrote; a reviewer that mangles quotes can re-quote.
    """
    return unicodedata.normalize("NFC", s)


def norm(s: str) -> str:
    """Outer whitespace and presentation noise only. Internal spacing is CONTENT.

    This used to collapse every internal whitespace run to a single space, so that a
    model echoing a line with different spacing still matched. That tolerance accepted
    a line nobody wrote: against the real diff, a quote carrying two spaces inside a
    Python string literal matched a source line holding one, and the CLI printed
    ANCHORED (review 2026-08-09, P1). Splitting the rule so that only the whole-line
    hatch was strict did not fix it either — the fragment path re-admitted the same
    fabrication, because both sides were still being collapsed before comparison.

    So the collapsing is gone. A quote must carry the spacing the line actually has.
    Leading and trailing whitespace is still forgiven, because re-indentation is
    presentation; a space inside a literal is not. The quote-style and dash
    substitutions in `_canon` stay for the same reason — a model really does swap
    typographic quotes — and neither can manufacture a line that does not exist,
    because both map many spellings of the SAME character, not different content.
    """
    return _canon(s).strip()


_C_ESCAPE = {"a": 7, "b": 8, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11,
             '"': 0x22, "\\": 0x5C}


def _unquote(tok: str) -> str:
    """Undo git's C-quoting of a path containing spaces or non-ASCII bytes.

    Git escapes each BYTE outside printable ASCII as a three-digit octal, so a UTF-8
    path arrives as a byte sequence, not as characters. The first implementation ran
    `unicode_escape`, which decodes those octals to Latin-1 code points: `caf\\303\\251.py`
    became `cafÃ©.py`, the index key never matched the real path, and a genuine finding
    on that file was rejected unread (review 2026-08-09, P1). Decode to bytes first,
    then decode the bytes as UTF-8 — the encoding git itself assumes.
    """
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        body, out, i = tok[1:-1], bytearray(), 0
        while i < len(body):
            ch = body[i]
            if ch != "\\" or i + 1 >= len(body):
                out.extend(ch.encode("utf-8"))
                i += 1
                continue
            nxt = body[i + 1]
            octal = body[i + 1:i + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8))
                i += 4
            elif nxt in _C_ESCAPE:
                out.append(_C_ESCAPE[nxt])
                i += 2
            else:  # unknown escape: keep the escaped character literally
                out.extend(nxt.encode("utf-8"))
                i += 2
        # surrogateescape, not strict: a path that is not valid UTF-8 is still a path,
        # and must round-trip to a key rather than raise and drop the file.
        return out.decode("utf-8", "surrogateescape")
    return tok


def _header_paths(line: str) -> list[str]:
    """Extract the paths named by any `diff ...` header, quoted or not.

    Handles `diff --git a/x b/x`, `diff --git "a/has space.py" "b/has space.py"`, and
    the combined forms `diff --cc <path>` / `diff --combined <path>`. Returning [] means
    "unparsable", which the caller treats as a hard file boundary.

    Quoted paths previously matched no branch at all, so such a file could never anchor
    ANY finding — a total false-reject on real changed files (review 2026-08-09).
    """
    if line.startswith(("diff --cc ", "diff --combined ")):
        raw = line.split(" ", 2)[2].strip()
        return [_unquote(raw)] if raw else []
    if not line.startswith("diff --git "):
        return []
    # Tokenise the remainder into quoted or bare paths.
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', line[len("diff --git "):])
    paths = [re.sub(r"^[ab]/", "", _unquote(t)) for t in toks]
    return paths if len(paths) >= 2 else []


def diff_index(diff_text: str) -> dict[str, list[str]]:
    """Map each file path in the diff to the lines that EXIST AFTER the change —
    additions and context only.

    Removed lines are excluded deliberately. Round 7 quoted a `-` line
    ("CARSI is an Australian IICRC-aligned...") and reported it as a live defect,
    when the diff was the commit that DELETED it. A quote is only evidence about
    the head if the line survives at the head.

    Header lines are identified by POSITION, not by prefix. Matching on prefix
    discarded real added source: a line whose own text begins `+++` is encoded in the
    hunk as `++++...`, which `startswith("+++")` swallowed — and with a one-line file
    that emptied the whole index, so a genuine finding was rejected as unanchored and,
    per this gate's contract, discarded unread. Reproduced 2026-08-08 (Codex P1 #3).
    After a `@@` hunk header every line is content, so prefixes stop being ambiguous.
    """
    files: dict[str, list[str]] = {}
    current: list[str] | None = None
    markers = 0  # marker columns in the current hunk; 0 == not inside a hunk
    for line in diff_text.splitlines():
        if line.startswith("diff "):
            paths = _header_paths(line)
            if paths:
                for p in paths:
                    files.setdefault(p, [])
                current = files[paths[-1]]  # post-image path is last
            else:
                # A header shape we cannot parse. Drop the previous file rather than
                # folding this one's lines into it — misattribution is the
                # false-ACCEPT direction for a rejection tool.
                current = None
            markers = 0
            continue
        if current is None:
            continue
        if line.startswith("@@"):
            # `@@` = 1 marker column; `@@@` = 2 (a combined/merge diff, `diff --cc`).
            # Treating a combined hunk as ordinary shifted every line by one column
            # and left its content attributed to the previous file.
            markers = len(line) - len(line.lstrip("@")) - 1
            markers = max(markers, 1)
            continue
        if not markers:
            continue  # still in this file's header block
        prefix, content = line[:markers], line[markers:]
        # A line survives into the post-image when no parent marks it removed.
        if prefix and all(c in "+ " for c in prefix):
            current.append(content)
    return files


# Rejecting fabricated fragments is the BOUNDARY rule's job, and it does it
# structurally. The specificity rule (further down) only has to clear a floor; every
# version of it that tried to do more got caught pulling one way or the other.
#
# ZWNJ (U+200C), ZWJ (U+200D) and `$` are IdentifierPart in JavaScript but are not
# Python identifier characters, so they must be added to the ID_Continue judgement
# _is_word_char asks. Without them a fabricated fragment ending just in front of one
# looks like it stopped at a token boundary. Escapes on purpose: the first two are
# invisible in a diff.
_JOINERS = "\u200c\u200d$"


def _is_word_char(ch: str) -> bool:
    """True when `ch` can occur INSIDE an identifier.

    Three consecutive reviews found a hole here, each a character class the previous
    rule had not thought of: `\\w` misses combining marks (U+0301), then it misses
    ZWNJ/ZWJ, then it misses U+00B7 MIDDLE DOT and U+203F UNDERTIE. Enumerating the
    exceptions was always going to lose that game — every round found another code
    point, and the ones it found were the ones a reviewer happened to try.

    So stop enumerating and ASK. `("a" + ch).isidentifier()` is Unicode's own
    ID_Continue judgement, which already covers letters, digits, underscore, marks,
    connector punctuation and Other_ID_Continue. Only ZWNJ and ZWJ need adding: they
    are IdentifierPart in JavaScript but not in Python.
    """
    return ("a" + ch).isidentifier() or ch in _JOINERS


# A fragment that boundary-matches more lines than this identifies none of them.
# Three is a judgement, not a discovery: it admits a citation repeated across a couple
# of nearby hunks while rejecting punctuation that occurs on every line of a file. A
# reviewer whose quote is genuinely that common should quote the whole line, which
# always anchors — the rejection message says so.
_MAX_MATCHING_LINES = 3


def _is_specific(quoted: str) -> bool:
    """True when `quoted` is more than a single stray character.

    SIX rounds of review moved this rule, alternately widening and narrowing it, and
    every version that judged the fragment IN ISOLATION was caught: a 12-character
    floor killed `os.system(`; a 3-character identifier component killed `fs.rm(`;
    "3 characters including a letter" killed `>= 3`; three non-whitespace characters
    killed `> 5` — while a two-character floor would readmit `()`, which was the
    original defect.

    The last two demands are unsatisfiable together by any length rule: `> 5` and `s =`
    are both two non-whitespace characters. So length stopped being the question. What
    actually distinguishes them is whether the quote IDENTIFIES a line, and that is
    measured against the file, not read off the fragment — see `anchors`. This is now
    only a floor against a single character, which can never identify anything.
    """
    return sum(1 for c in quoted if not c.isspace()) >= 2


def _fragment_anchors(quoted: str, line: str) -> bool:
    """True when `quoted` occurs in `line` ON TOKEN BOUNDARIES.

    A bare `in` test accepted arbitrary slices of a longer identifier: against
    `dangerous_call()` the fragments "dan", "ger" and "call" each satisfied the
    identifier rule and the substring test, so a fabricated citation could be made
    to look mechanically anchored (review 2026-08-09, P1). Requiring the fragment's
    own leading/trailing WORD characters to sit on a token boundary rejects all
    three, while `os.system(`, `dangerous_call` and `system` — the specific
    citations a reviewer legitimately gives — still anchor.

    Every occurrence is tried, not just the first: a fragment may sit mid-identifier
    once and on a boundary later in the same line.
    """
    start = line.find(quoted)
    while start != -1:
        end = start + len(quoted)
        left_ok = not (_is_word_char(quoted[0]) and start > 0
                       and _is_word_char(line[start - 1]))
        right_ok = not (_is_word_char(quoted[-1]) and end < len(line)
                        and _is_word_char(line[end]))
        if left_ok and right_ok:
            return True
        start = line.find(quoted, start + 1)
    return False


def anchors(quoted: str, lines: list[str]) -> bool:
    """True when `quoted` is real evidence about a line in this file's post-image.

    Takes the RAW quote and chooses the normalisation per check: exact for the
    whole-line hatch, collapsing for fragments.

    A fragment must both occur on token boundaries AND single out a small number of
    lines. Discriminativeness is what the earlier length floors were reaching for and
    kept missing: `> 5` and `()` are the same length, but in a real file the first
    picks out one line and the second picks out most of them. Measuring that against
    the file answers the question the fragment alone cannot.
    """
    if any(norm(quoted) == norm(l) for l in lines):
        return True  # a whole-line match is always evidence, however short
    fragment = norm(quoted)
    if not _is_specific(fragment):
        return False  # one character can never identify a line
    hits = sum(1 for l in lines if _fragment_anchors(fragment, norm(l)))
    return 1 <= hits <= _MAX_MATCHING_LINES


def resolve(path: str, files: dict[str, list[str]]) -> list[str] | None:
    """Map a reviewer's file path onto a path in the diff, or None.

    Tolerates a leading `a/` or `b/` and a path the model SHORTENED to a unique suffix
    of a real one. It does not tolerate the reverse. `stripped.endswith("/" + k)` used
    to accept a reviewer path merely because a real path was a suffix of it, so
    `not-a-real-tree/skills/.../verify_reviewer_citations.py` resolved to the real file
    and a genuine line anchored under an invented path (review 2026-08-09, P1) — which
    is the wrong-file false-accept this verifier exists to reject, arrived at from the
    other end. Shortening a path is a plausible model abbreviation; lengthening one is
    a claim about a tree that does not exist.
    """
    if path in files:
        return files[path]
    stripped = re.sub(r"^[ab]/", "", path)
    if stripped in files:
        return files[stripped]
    matches = [v for k, v in files.items() if k.endswith("/" + stripped)]
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    report = json.load(open(sys.argv[1], encoding="utf-8"))
    files = diff_index(open(sys.argv[2], encoding="utf-8", errors="replace").read())

    findings = report.get("blocking_findings") or []
    if not findings:
        print("No blocking findings to anchor.")
        return 0

    unanchored = []
    for i, f in enumerate(findings, 1):
        path = (f.get("file") or "").strip()
        # Pass the RAW quote to anchors(); it decides which normalisation each check
        # gets. Normalising here once and reusing that value for both is what let a
        # collapsed line reach the exact-match hatch.
        raw = f.get("quoted_line") or ""
        quoted = norm(raw)
        sev = f.get("severity", "?")
        lines = resolve(path, files)

        if not quoted:
            unanchored.append((i, sev, path, "no quoted_line supplied"))
            continue
        if lines is None:
            unanchored.append((i, sev, path, "file does not appear in the diff"))
            continue
        if anchors(raw, lines):
            print(f"  ANCHORED   [{sev}] {path}: {quoted[:70]}")
        elif not _is_specific(quoted):
            unanchored.append((i, sev, path,
                               "quoted_line is a single character and matches no line "
                               "exactly — quote the expression or the whole line"))
        elif sum(1 for l in lines if _fragment_anchors(quoted, norm(l))) > _MAX_MATCHING_LINES:
            unanchored.append((i, sev, path,
                               f"quoted_line matches more than {_MAX_MATCHING_LINES} lines "
                               "in that file, so it identifies none of them — quote the "
                               "whole line, which always anchors"))
        else:
            unanchored.append((i, sev, path, "quoted_line is absent from that file's diff"))

    if unanchored:
        print()
        print(f"REJECTED {len(unanchored)} of {len(findings)} blocking finding(s) as unanchored:")
        for i, sev, path, why in unanchored:
            print(f"  #{i} [{sev}] {path} — {why}")
        return 2

    print(f"\nAll {len(findings)} blocking finding(s) anchored to real diff lines.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
