#!/usr/bin/env python3
"""Migration drift check — does the database actually have what the repository thinks it has?

This is the runnable half of the `eng-release` seat. It exists because on 2026-07-29 the ATO
repository was found to have 40+ migration files against 3 recorded in the production ledger: a
correct security migration had been committed on 2026-02-12 and never applied, and nothing
noticed for five and a half months. "Merged" and "applied" are two separate facts.

Exit codes:
    0  in sync
    1  DRIFT — repo and ledger disagree
    2  CANNOT DETERMINE — fail closed

Exit 2 matters as much as exit 1. A check that cannot reach the database and reports "skipped"
is a silent fail-open, which is the same failure mode it was built to catch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION_PREFIX = re.compile(r"^(\d+)")
DEFAULT_LEDGER = "supabase_migrations.schema_migrations"


class CannotDetermine(Exception):
    """Raised when the check cannot establish both sides. Never downgrade this to a pass."""


def run(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=60)
    except FileNotFoundError as exc:
        raise CannotDetermine(f"{cmd[0]} is not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise CannotDetermine(f"{cmd[0]} timed out after 60s") from exc
    if result.returncode:
        raise CannotDetermine(
            f"{' '.join(cmd[:2])} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()[:300]}"
        )
    return result.stdout


def version_of(name: str) -> str | None:
    """Leading digit run of a migration filename. `20260212_rls.sql` -> `20260212`."""
    match = VERSION_PREFIX.match(Path(name).name)
    return match.group(1) if match else None


def repo_versions(root: Path, migrations_dir: str, ref: str | None) -> dict:
    """Migration versions in the repository, mapped version -> filename.

    Reading from a git ref rather than the working tree is deliberate: a migration that exists
    only on a feature branch is invisible by construction, so unapplied local work never trips
    the check and no filtering heuristic is needed.
    """
    if ref:
        out = run(["git", "ls-tree", "-r", "--name-only", ref, "--", migrations_dir], cwd=root)
        names = [line.strip() for line in out.splitlines() if line.strip().endswith(".sql")]
    else:
        target = root / migrations_dir
        if not target.is_dir():
            raise CannotDetermine(f"migrations directory not found: {migrations_dir}")
        names = [str(p.relative_to(root)) for p in sorted(target.glob("*.sql"))]

    # version -> [filenames]. A list, not a single name: two files can legitimately share a
    # version prefix (20260212_composite_indexes.sql and 20260212_rls_xero_connections.sql), and
    # collapsing them hides one. The first run of this check against ATO did exactly that, and the
    # file it hid was the unapplied security migration the whole check exists to surface.
    versions: dict = {}
    unversioned = []
    for name in names:
        version = version_of(name)
        if version is None:
            unversioned.append(name)
        else:
            versions.setdefault(version, []).append(Path(name).name)
    return {"versions": versions, "unversioned": unversioned, "count": len(names)}


def applied_versions(db_url: str | None, ledger: str, column: str, from_file: str | None) -> set:
    """Versions the database says are applied."""
    if from_file:
        text = Path(from_file).read_text()
        return {line.strip() for line in text.splitlines() if line.strip()}
    if not db_url:
        raise CannotDetermine(
            "no --db-url and no --applied-from-file; cannot establish what is applied"
        )
    out = run(["psql", db_url, "-Atc", f"select {column} from {ledger} order by 1;"])
    return {line.strip() for line in out.splitlines() if line.strip()}


def reconcile(repo: dict, applied: set) -> dict:
    """Match repo versions against applied versions, tolerating prefix-length conventions.

    Supabase records 14-digit timestamps (20260729033909) while repositories commonly name files
    with an 8-digit date (20260729_fix.sql). Treating one as a match for the other when either is
    a prefix of the other is a heuristic, and it is the honest trade: without it every repo using
    date-prefixed filenames reports permanent false drift, which trains people to ignore the check.
    """
    repo_versions_set = set(repo["versions"])

    def matches(candidate: str, pool: set) -> bool:
        return any(candidate == other or candidate.startswith(other) or other.startswith(candidate)
                   for other in pool)

    missing = sorted(v for v in repo_versions_set if not matches(v, applied))
    extra = sorted(v for v in applied if not matches(v, repo_versions_set))
    return {
        "missing_from_database": [
            {"version": v, "file": name}
            for v in missing for name in sorted(repo["versions"][v])
        ],
        "applied_but_not_in_repo": extra,
        "repo_migration_count": repo["count"],
        "applied_count": len(applied),
        "unversioned_files": repo["unversioned"],
    }


def report(result: dict, root: Path, grace_minutes: int, ref: str | None) -> int:
    missing = result["missing_from_database"]
    extra = result["applied_but_not_in_repo"]
    if not missing and not extra:
        print(f"MIGRATION_DRIFT_OK  repo={result['repo_migration_count']} "
              f"applied={result['applied_count']}")
        return 0

    print("MIGRATION DRIFT", file=sys.stderr)
    if missing:
        print(f"\n  {len(missing)} migration(s) in the repository are NOT applied to the database:",
              file=sys.stderr)
        for item in missing:
            merged = merged_at(root, item["file"], ref)
            age = f", merged {merged}" if merged else ""
            print(f"    {item['file']}{age}", file=sys.stderr)
    if extra:
        print(f"\n  {len(extra)} version(s) applied to the database with no file in the repository:",
              file=sys.stderr)
        for version in extra:
            print(f"    {version}  (applied out of band — dashboard, console, or a loose .sql)",
                  file=sys.stderr)
    if result["unversioned_files"]:
        print(f"\n  {len(result['unversioned_files'])} file(s) with no version prefix, "
              "not comparable:", file=sys.stderr)
        for name in result["unversioned_files"][:10]:
            print(f"    {name}", file=sys.stderr)

    print("\n  Apply the missing migrations, then re-run this check. Do not add a new migration "
          "on top of an already-drifted ledger.", file=sys.stderr)
    return 1


def merged_at(root: Path, filename: str, ref: str | None) -> str | None:
    if not ref:
        return None
    try:
        out = run(["git", "log", "-1", "--format=%ad", "--date=short", ref, "--",
                   f"*{filename}"], cwd=root).strip()
        return out or None
    except CannotDetermine:
        return None


def self_test() -> int:
    """Positive control: prove the check can return non-zero before trusting a zero.

    A drift check that has never failed is indistinguishable from one that cannot fail.
    """
    import tempfile

    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        migrations = root / "supabase" / "migrations"
        migrations.mkdir(parents=True)
        for name in ("001_init.sql", "20260212_security_fix.sql",
                     "20260212_composite_indexes.sql", "20260729_later.sql"):
            (migrations / name).write_text("-- test\n")

        repo = repo_versions(root, "supabase/migrations", ref=None)

        # Case 1: ledger knows only the first migration -> must report drift.
        drifted = reconcile(repo, {"001"})
        reported = {item["file"] for item in drifted["missing_from_database"]}
        # Three files, two sharing the 20260212 prefix. All three must be named: collapsing a
        # shared prefix to one filename is how this check hid ATO's unapplied security migration.
        if reported != {"20260212_security_fix.sql", "20260212_composite_indexes.sql",
                        "20260729_later.sql"}:
            print(f"SELF-TEST FAIL: shared-prefix files were dropped; reported {reported}",
                  file=sys.stderr)
            ok = False

        # Case 2: everything applied, with Supabase's longer timestamp form -> must be clean.
        clean = reconcile(repo, {"001", "20260212010101", "20260729033909"})
        if clean["missing_from_database"] or clean["applied_but_not_in_repo"]:
            print(f"SELF-TEST FAIL: expected clean, got {clean}", file=sys.stderr)
            ok = False

        # Case 3: ledger carries a version with no file -> out-of-band change, must report.
        out_of_band = reconcile(repo, {"001", "20260212", "20260729", "20260601999999"})
        if out_of_band["applied_but_not_in_repo"] != ["20260601999999"]:
            print(f"SELF-TEST FAIL: expected the out-of-band version to be reported, got "
                  f"{out_of_band['applied_but_not_in_repo']}", file=sys.stderr)
            ok = False

        # Case 4: an unreachable database must fail closed, never report in sync.
        try:
            applied_versions(db_url=None, ledger=DEFAULT_LEDGER, column="version", from_file=None)
            print("SELF-TEST FAIL: missing db-url did not raise CannotDetermine", file=sys.stderr)
            ok = False
        except CannotDetermine:
            pass

    print("SELF-TEST PASS: the check reports drift, tolerates timestamp-length conventions, "
          "reports out-of-band versions, and fails closed without a database."
          if ok else "SELF-TEST FAILED", file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)

    check = sub.add_parser("check", help="compare repo migrations against the applied ledger")
    check.add_argument("--root", default=".", help="repository root (default: cwd)")
    check.add_argument("--migrations-dir", default="supabase/migrations")
    check.add_argument("--ref", default="origin/main",
                       help="git ref to read migrations from; 'worktree' to use the filesystem")
    check.add_argument("--db-url", default=os.environ.get("DRIFT_DB_URL"))
    check.add_argument("--ledger", default=DEFAULT_LEDGER)
    check.add_argument("--column", default="version")
    check.add_argument("--applied-from-file",
                       help="read applied versions from a file, one per line, instead of psql")
    check.add_argument("--grace-minutes", type=int, default=0,
                       help="tolerate migrations merged within this window (cron use only)")
    check.add_argument("--json", action="store_true")

    sub.add_parser("self-test", help="positive control: prove the check can fail")

    args = parser.parse_args(argv)
    if args.action == "self-test":
        return self_test()

    root = Path(args.root).expanduser().resolve()
    ref = None if args.ref == "worktree" else args.ref
    try:
        repo = repo_versions(root, args.migrations_dir, ref)
        applied = applied_versions(args.db_url, args.ledger, args.column, args.applied_from_file)
    except CannotDetermine as exc:
        print(f"MIGRATION_DRIFT_CANNOT_DETERMINE: {exc}", file=sys.stderr)
        print("  This is a FAILURE, not a skip. A check that cannot see the database is the "
              "same silent fail-open it exists to catch.", file=sys.stderr)
        return 2

    result = reconcile(repo, applied)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if not (result["missing_from_database"] or result["applied_but_not_in_repo"]) else 1
    return report(result, root, args.grace_minutes, ref)


if __name__ == "__main__":
    sys.exit(main())
