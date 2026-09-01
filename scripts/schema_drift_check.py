#!/usr/bin/env python3
"""Schema drift — compare the LIVE catalog against what this repo declares (RA-7399).

`rls-assertions` builds its shadow database from files in this repo, so it can
only ever assert that the DECLARED schema is sound. It is structurally incapable
of saying anything about production. PR #707 made the two sets match on
2026-09-01; that was a snapshot, not a mechanism. Create a table straight against
Pi CEO tomorrow and it is invisible to that gate again, exactly as 20 tables were.

This is the second job with the different input. It reads the live table list on
STDIN (the workflow pipes `psql` into it) and diffs it against the declared set.

BOTH DIRECTIONS MATTER, and they mean opposite things:

  * LIVE but NOT DECLARED -- the RLS gate is blind to that table. This is the
    condition RA-7396 found 20 of. Hard failure, no baseline: the whole point is
    that it should never happen again.
  * DECLARED but NOT LIVE -- a migration that was never applied. Code
    referencing the table does not crash; `supabase_log` reads return `[]` and
    writes return False, both with a log warning, so the feature degrades to a
    silent no-op. Ten exist today, so this direction is BASELINED and
    shrink-only, like every other ratchet here.

WHY STDIN. The live query needs a credential this repo does not hold, so the
fetch is deliberately outside the script: the workflow owns the secret, the
script owns the logic, and the logic is testable with no database at all.

THE TRAP THIS MUST NOT FALL INTO, quoting the ticket that asked for it: "A drift
job that silently fails to connect, or queries the wrong project, reports 'no
drift' -- indistinguishable from a clean system." An empty live set is therefore
a HARD ERROR, never "nothing live, so nothing undeclared". That single rule is
what stops this check from becoming the thing it checks for.
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
BASELINE = REPO / ".github" / "schema-drift.baseline.txt"

# All three, and the third is load-bearing. CLAUDE.md's own re-derivation command
# read only the first two for months and under-reported by four tables -- the
# mesh_* set, live in production and cited by ADR-008 as the schema of record.
SOURCES = ("supabase/migration.sql", "supabase/migrations/*.sql", "mesh/schema/*.sql")

_CREATE = re.compile(
    r'create\s+table\s+(?:if\s+not\s+exists\s+)?["\']?(?:public\.)?([a-z0-9_]+)', re.I
)


def source_files() -> list:
    """Every .sql file that declares part of the schema, in apply order."""
    out = []
    for pattern in SOURCES:
        if "*" in pattern:
            out.extend(sorted(REPO.glob(pattern)))
        elif (REPO / pattern).exists():
            out.append(REPO / pattern)
    return out


def declared_tables() -> dict:
    """table name -> the file that declares it (first declaration wins)."""
    found = {}
    for path in source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for name in _CREATE.findall(text):
            found.setdefault(name.lower(), str(path.relative_to(REPO)))
    return found


def parse_live(text: str) -> set:
    """One table name per line, as `psql -At` emits."""
    return {ln.strip().lower() for ln in text.splitlines() if ln.strip()}


def read_baseline() -> dict:
    """Declared-but-absent tables that are known and accepted, name -> why."""
    if not BASELINE.exists():
        return {}
    out = {}
    for line in BASELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, why = line.partition("\t")
        out[name.strip().lower()] = why.strip()
    return out


def classify(declared: dict, live: set, baseline: dict) -> dict:
    """Both drift directions, with the baseline applied to one of them."""
    return {
        "live_not_declared": sorted(live - set(declared)),
        "declared_not_live": sorted(t for t in set(declared) - live if t not in baseline),
        "baselined_now_live": sorted(t for t in baseline if t in live),
    }


def report(result: dict, declared: dict, live: set) -> int:
    """Print the verdict. Returns the process exit code."""
    print(f"declared: {len(declared)}   live: {len(live)}\n")
    failed = False

    if result["live_not_declared"]:
        failed = True
        print("LIVE but NOT DECLARED — the RLS gate is blind to these:")
        for t in result["live_not_declared"]:
            print(f"   {t}")
            print(f"::error::schema-drift: {t} exists live but no migration declares it")
        print("\n  Declare each in a dated file under supabase/migrations/ so the")
        print("  rls-assertions gate can see it. This direction has no baseline.\n")

    if result["declared_not_live"]:
        failed = True
        print("DECLARED but NOT LIVE — migration never applied:")
        for t in result["declared_not_live"]:
            print(f"   {t:<32} {declared[t]}")
            print(f"::error::schema-drift: {t} is declared by {declared[t]} but absent from live")
        print("\n  Code touching these does not crash — reads return [] and writes")
        print("  return False, each with a log warning — so the feature silently")
        print("  does nothing. Apply the migration, or baseline it with a reason.\n")

    if result["baselined_now_live"]:
        failed = True
        print("BASELINED but now LIVE — remove from the baseline, it only shrinks:")
        for t in result["baselined_now_live"]:
            print(f"   {t}")
            print(f"::error::schema-drift: {t} is live now; drop it from {BASELINE.name}")
        print()

    if not failed:
        print(f"no drift — every live table is declared, and every declared table is "
              f"live or baselined ({len(read_baseline())} baselined).")
    return 1 if failed else 0


def main() -> int:
    raw = sys.stdin.read()
    live = parse_live(raw)
    # FAIL CLOSED, and this is the single most important line in the file. An
    # empty live set means psql failed, the credential is wrong, or the wrong
    # project was queried. Treated as data it reads as "nothing live", which
    # produces zero live-but-undeclared and a clean bill of health for a check
    # that never reached the database.
    if not live:
        print("schema-drift: received an EMPTY live table list on stdin.\n"
              "Refusing to report 'no drift' from a query that returned nothing —\n"
              "that is indistinguishable from a healthy database and is exactly the\n"
              "failure this check exists to prevent. Verify SUPABASE_DB_URL and that\n"
              "psql succeeded (use `set -o pipefail`).", file=sys.stderr)
        return 2

    declared = declared_tables()
    if not declared:
        print("schema-drift: parsed 0 declared tables — the source globs matched "
              "nothing. Refusing to call every live table undeclared.", file=sys.stderr)
        return 2

    return report(classify(declared, live, read_baseline()), declared, live)


if __name__ == "__main__":
    sys.exit(main())
