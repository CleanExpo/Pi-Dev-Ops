#!/usr/bin/env python3
"""check_business_charters.py — every declared business charter must resolve.

`config/harness/projects.json` lets a project declare `business_charter`. That file is the
business brain a generated session is supposed to inherit: buyer, pain, promise, quality
bar. `discovery.py` reads it, and `workspace_context.py` plants it into the workspace
CLAUDE.md.

When it cannot be resolved, both degrade to `charter_text = ""` and carry on. Nothing
raises, nothing logs at a level anyone reads, and the session builds against an empty brain
— which looks exactly like a project that never declared one.

A RATCHET, not a wall. Seven entries are known-missing today. Failing on those would make
this gate red on the day it was written, and a gate that is red on arrival is one nobody
reads — the exact failure this repo has fixed twice. So the known set is recorded below and
tolerated; anything NEW fails, and anything that starts resolving must be removed from the
set, which the gate tells you to do.

THE VERDICT IS A FUNCTION OF THE REPOSITORY ALONE, and that is a repair, not a detail.

Resolution used to consult `~/.hermes/business-charters/` — machine-local state outside the
repo. One Git SHA therefore got two different verdicts:

  * on a machine holding `~/.hermes/business-charters/restoreassist.md` (dated 6 May 2026),
    `restoreassist` resolved, so it "must leave _KNOWN_MISSING" and the gate exited 1;
  * in CI, where no `~/.hermes` exists, nothing resolved, so the same SHA exited 0.

The repair the gate itself demanded — drop `restoreassist` from the known set — would then
have made CI fail with `[MISSING] restoreassist`. No edit to this file could satisfy both
environments, because the input deciding the verdict was not in the repository. A developer
could not make the tree green, and a green tree said nothing about anyone else's.

So resolution is now repository-controlled: a charter resolves when the REPOSITORY carries
it, at a repo-relative path that stays inside the repository. An absolute declared path is
machine-local by construction and never resolves here. Machine-local copies are still what
the RUNTIME reads (`discovery.py` resolves a relative declaration against `CHARTERS_DIR`
under `~/.hermes`), and they are still reported by `--explain-local` — but they are read by
nothing that decides the exit code.

The claim this gate now makes is exactly: "the repository does not carry this charter, so
any checkout without a private local copy builds against an empty business brain." That is a
property of the SHA, which is the only kind of property a repository gate can honestly hold.

Note that this does not weaken CI. CI already exited 0 with these seven entries, because it
never had `~/.hermes` to resolve them from; the change makes every other environment agree
with CI instead of disagreeing with it.

Exit codes:
    0 — every declared charter resolves from the repository, or is in the known-missing set
    1 — a charter went missing that was not already known, or the set is stale
    2 — the registry could not be read

Output on stdout is byte-identical for a given SHA in every environment. Machine-dependent
diagnostics go to stderr, and only when --explain-local is passed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "harness" / "projects.json"

# Charters the REPOSITORY does not carry today. Shrink this set; never grow it.
# Each entry is business context a generated session is currently building without.
_KNOWN_MISSING = {
    "restoreassist",
    "disaster-recovery",
    "dr-nrpg",
    "synthex",
    "unite-group",
    "ccw-crm",
    "carsi",
}


def _charters_dir() -> Path:
    """Where the RUNTIME looks. Diagnostic only — never an input to the verdict."""
    hermes = os.environ.get("HERMES_ROOT") or os.path.join(Path.home(), ".hermes")
    return Path(hermes) / "business-charters"


def _resolves(declared: str) -> bool:
    """Repository-controlled resolution. The only input to the exit code.

    An absolute path is machine-local by construction, so it never resolves here even
    when it exists on this machine — otherwise one developer's filesystem layout would
    decide the verdict again, which is the defect this function was rewritten to remove.

    A relative path that climbs out of the repository is not repository-controlled
    either, so containment is checked rather than assumed.
    """
    path = Path(declared)
    if path.is_absolute():
        return False
    candidate = (REPO_ROOT / path).resolve()
    try:
        candidate.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return candidate.is_file()


def _resolves_locally(declared: str) -> bool:
    """Machine-local presence, as the runtime would resolve it. Reported, never scored."""
    path = Path(declared)
    if path.is_absolute():
        return path.exists()
    return (_charters_dir() / path.name).exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--explain-local",
        action="store_true",
        help="also print, on stderr, which charters exist in the machine-local "
             "~/.hermes store. Diagnostic only: it cannot change the exit code, and "
             "stdout stays byte-identical with or without it.",
    )
    args = parser.parse_args(argv)

    if not REGISTRY.exists():
        print(f"[FAIL] registry not found: {REGISTRY}")
        return 2
    try:
        projects = json.loads(REGISTRY.read_text(encoding="utf-8")).get("projects", [])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[FAIL] registry unreadable: {exc}")
        return 2

    declared = {p.get("id"): p["business_charter"]
                for p in projects if p.get("business_charter")}
    missing = {pid for pid, path in declared.items() if not _resolves(path)}
    resolved = set(declared) - missing

    # No machine path is printed here. The old line embedded the resolved
    # ~/.hermes location, which made even the PASS output differ per machine and
    # per user, so two people could not compare gate logs for the same SHA.
    print(f"business charters: {len(declared)} declared, "
          f"{len(resolved)} resolve from the repository, {len(missing)} missing")

    new_missing = missing - _KNOWN_MISSING
    now_resolving = _KNOWN_MISSING & resolved

    for pid in sorted(missing & _KNOWN_MISSING):
        print(f"  [known-missing] {pid} -> {declared[pid]}")

    if args.explain_local:
        # stderr, so stdout stays byte-identical across environments for one SHA.
        local = sorted(pid for pid, path in declared.items() if _resolves_locally(path))
        print(f"[local] charters dir: {_charters_dir()}", file=sys.stderr)
        print(f"[local] present locally but not carried by the repository: "
              f"{', '.join(sorted(set(local) & missing)) or 'none'}", file=sys.stderr)

    if now_resolving:
        print("\n[FAIL] These charters now resolve and must leave _KNOWN_MISSING, so the "
              "gate keeps protecting them:")
        for pid in sorted(now_resolving):
            print(f"  [FIXED] {pid}")
        return 1

    if new_missing:
        print("\n[FAIL] Charter declared but unresolvable, and not previously known. A "
              "session for this project would build against an empty business brain:")
        for pid in sorted(new_missing):
            print(f"  [MISSING] {pid} -> {declared[pid]}")
        return 1

    print("[PASS] no new unresolvable charters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
