#!/usr/bin/env python3
"""Baseline ratchet — every ratchet baseline may SHRINK, never GROW (RA-7400).

This repo has four ratchet baselines. Two of them state, in their own words,
that they only ever shrink:

    supabase/tests/pgtap/rls_coverage.sql:21   "THE BASELINE IS SHRINK-ONLY"
    .github/scripts/file_length_lint.py:32     "The baseline only ever goes down"

Nothing enforced it. The consuming scripts read their baseline as ground truth,
so editing the baseline was the unguarded way past the gate, in two directions:

  * ADD a key     -- `rls_coverage.sql` exempts baselined tables from BOTH RLS
                     checks, so one added line drops a table out of RLS
                     enforcement entirely. `file_length_lint.classify()` looks up
                     `baseline.get(path)`; an added entry makes `count > allowed`
                     false and a 2000-line file passes.
  * RAISE a value -- the length gates fail a file that grew "beyond its entry".
                     Raise the entry and it has not grown. CLAUDE.md says "Never
                     raise an entry to get green"; that was a request, not a
                     check. This direction leaves the entry COUNT unchanged, so
                     a check that only counted entries would miss it.

Both are silent. CI stays green and the gate is one table or one file weaker,
with nothing in the diff that reads as a failure.

Found by CodeRabbit on PR #708, 68 seconds before it merged.

WHAT THIS DOES NOT DO. It compares each baseline against its own previous
version, so it only sees changes that arrive through git, and it says nothing
about whether the surviving entries are justified -- that is RA-7393's
per-table work. Legitimate additions stay possible on purpose: see
`Baseline-Allow:` below. A guard with no escape hatch gets deleted the first
time someone genuinely needs one, which is worse than a guard with a documented
one.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# key -> numeric limit, or None where the baseline lists bare keys with no value.
Baseline = dict[str, "int | None"]


def parse_tsv(text: str) -> Baseline:
    """`count \\t fingerprint \\t key` — both length baselines."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 3:
            continue
        try:
            out[parts[2]] = int(parts[0])
        except ValueError:
            continue
    return out


def parse_kv(text: str) -> Baseline:
    """`key=value` — the design-md lint baseline."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        try:
            out[key.strip()] = int(value.strip())
        except ValueError:
            out[key.strip()] = None
    return out


def parse_rls(text: str) -> Baseline:
    """Table names from the `_rls_baseline` INSERT in rls_coverage.sql.

    Comments are stripped FIRST, and that is load-bearing. One of them contains
    an apostrophe ("Supabase's advisor"); a naive quote scan reads it as an
    opening quote and swallows the rest of the block, returning 5 entries where
    there are 9. A parser that under-reports here would report "no additions" on
    a diff that added four -- this guard becoming the thing it guards.
    """
    body = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    match = re.search(r"insert\s+into\s+_rls_baseline.*?;", body, re.S | re.I)
    if not match:
        return {}
    return {t: None for t in re.findall(r"\(\s*'([a-z0-9_]+)'\s*,", match.group(0), re.I)}


def parse_names(text: str) -> Baseline:
    """`name \\t why` — the schema-drift baseline, which carries no numbers."""
    out: Baseline = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out[stripped.split("\t")[0].strip()] = None
    return out


BASELINES = {
    ".github/file-length.baseline.txt": parse_tsv,
    ".github/function-length.baseline.txt": parse_tsv,
    ".github/design-md-lint.baseline.txt": parse_kv,
    # RA-7399. Tables a migration declares that production does not have. Added
    # here so the drift job's own escape hatch ratchets: silencing a newly
    # unapplied migration by appending to that file is blocked, the same way
    # appending to the RLS baseline is.
    ".github/schema-drift.baseline.txt": parse_names,
    "supabase/tests/pgtap/rls_coverage.sql": parse_rls,
}


def git_show(ref: str, path: str) -> "str | None":
    """File content at `ref`, or None when it did not exist there."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True
    )
    return proc.stdout if proc.returncode == 0 else None


def base_ref() -> str:
    """The commit to compare against.

    CI passes the PR's base SHA explicitly. Locally `origin/main` is the honest
    default: comparing against a stale local `main` would compare the baseline
    with a version of itself nobody else has.
    """
    return os.environ.get("BASELINE_BASE_SHA", "").strip() or "origin/main"


def allowed_keys(base: str) -> set[str]:
    """Keys a commit message explicitly authorises adding or raising.

    Format, one per line, in any commit between the base and HEAD:

        Baseline-Allow: <key> -- <why>

    A commit trailer rather than a config file, deliberately: it lands in the
    diff, it names the author, and it cannot be added without touching history a
    reviewer reads. Real additions do happen -- the 2026-09-01 back-fill added
    four entries for tables live in production with RLS and no policy -- so the
    escape hatch is not theoretical. It is per key, never a blanket disable.
    """
    proc = subprocess.run(
        ["git", "log", f"{base}..HEAD", "--format=%B"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return set()
    # `\S+` — the first whitespace-delimited token, NOT `[^\s-]+`. That earlier
    # pattern was meant to stop before the " -- why" separator and instead
    # stopped at the first hyphen in the KEY, so a baselined path such as
    # "remotion-studio/scripts/render.py" was read as "remotion" and authorised
    # nothing. Every key in these baselines is a file path and this repo has
    # hyphenated directories, so it was reachable rather than theoretical.
    # Found via the identical bug in smoke_surface_gate.py (RA-7398).
    return {k.strip() for k in re.findall(r"^Baseline-Allow:\s*(\S+)", proc.stdout, re.M)}


def compare(path: str, before: Baseline, after: Baseline, allowed: set[str]) -> list[str]:
    """Additions and raised values, both weakenings. Removals and drops pass."""
    problems: list[str] = []
    for key in sorted(set(after) - set(before)):
        if key not in allowed:
            problems.append(f"{path}: ADDED  {key}")
    for key in sorted(set(after) & set(before)):
        old, new = before[key], after[key]
        if old is None or new is None or new <= old or key in allowed:
            continue
        problems.append(f"{path}: RAISED {key}  {old} -> {new}")
    return problems


def read_head(path: str) -> "str | None":
    """Working-tree content, or None if the file is absent."""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError:
        return None


def check_one(path: str, parser, base: str, allowed: set[str]) -> list[str]:
    """Compare one baseline against its version at `base`."""
    head_text = read_head(path)
    if head_text is None:
        print(f"skip  {path}: not in the working tree")
        return []
    base_text = git_show(base, path)
    if base_text is None:
        print(f"note  {path}: new at this revision — nothing to ratchet against yet")
        return []
    before, after = parser(base_text), parser(head_text)
    if not before:
        print(f"warn  {path}: parsed 0 entries at {base} — treating as unverifiable")
        return []
    problems = compare(path, before, after, allowed)
    print(f"{'FAIL' if problems else 'ok  '}  {path}: {len(before)} -> {len(after)} entries")
    return problems


def report(problems: list[str]) -> None:
    """Print every weakening, with GitHub annotations, and how to proceed."""
    print("\nBaselines ratchet DOWN only. These grew:\n")
    for problem in problems:
        print(f"  {problem}")
        print(f"::error::baseline-ratchet: {problem}")
    print(
        "\nAn added key exempts something from a gate; a raised value lets a "
        "baselined\noffender grow. Fix the underlying file instead. If the "
        "addition is genuinely\ncorrect, say so in the commit message:"
        "\n\n    Baseline-Allow: <key> -- <why>\n"
    )


def main() -> int:
    base = base_ref()
    # FAIL CLOSED. Without this, an unresolvable base makes every file report
    # "new at this revision" and the run prints a clean pass — a guard green
    # precisely because it could see nothing. `.gitignore` is the probe: it
    # exists at every commit in this repo's history, so failing to read it means
    # the ref is wrong or the checkout is shallow, never that the file moved.
    if git_show(base, ".gitignore") is None:
        print(f"baseline-ratchet: cannot resolve base '{base}'. CI needs "
              "fetch-depth: 0 and a resolvable BASELINE_BASE_SHA. Refusing to "
              "report a clean result it cannot support.")
        return 1

    allowed = allowed_keys(base)
    if allowed:
        print(f"baseline-ratchet: explicitly allowed by trailer: {sorted(allowed)}")

    problems: list[str] = []
    for path, parser in BASELINES.items():
        problems.extend(check_one(path, parser, base, allowed))

    if problems:
        report(problems)
        return 1
    print(f"\nbaseline-ratchet passed — {len(BASELINES)} baselines, none grew.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
