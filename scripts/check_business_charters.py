#!/usr/bin/env python3
"""check_business_charters.py — every declared business charter must resolve.

`config/harness/projects.json` lets a project declare `business_charter`. That file is the
business brain a generated session is supposed to inherit: buyer, pain, promise, quality
bar. `discovery.py` reads it, and `workspace_context.py` plants it into the workspace
CLAUDE.md.

When it cannot be resolved, both degrade to `charter_text = ""` and carry on. Nothing
raises, nothing logs at a level anyone reads, and the session builds against an empty brain
— which looks exactly like a project that never declared one.

A RATCHET, not a wall. Seven entries are known-missing today (the charters live under
`~/.hermes/business-charters/`, which is machine-local and outside the repo, so they do not
propagate). Failing on those would make this gate red on the day it was written, and a gate
that is red on arrival is one nobody reads — the exact failure this repo has fixed twice.
So the known set is recorded below and tolerated; anything NEW fails, and anything that
starts resolving must be removed from the set, which the gate tells you to do.

Exit codes:
    0 — every declared charter resolves, or is in the known-missing set
    1 — a charter went missing that was not already known, or the set is stale
    2 — the registry could not be read
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = REPO_ROOT / "config" / "harness" / "projects.json"

# Charters that do not resolve on a clean checkout today. Shrink this set; never grow it.
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
    hermes = os.environ.get("HERMES_ROOT") or os.path.join(Path.home(), ".hermes")
    return Path(hermes) / "business-charters"


def _resolves(declared: str) -> bool:
    path = Path(declared)
    if path.is_absolute():
        return path.exists()
    return (REPO_ROOT / declared).exists() or (_charters_dir() / path.name).exists()


def main() -> int:
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

    print(f"business charters: {len(declared)} declared, "
          f"{len(resolved)} resolve, {len(missing)} missing "
          f"(charters dir: {_charters_dir()})")

    new_missing = missing - _KNOWN_MISSING
    now_resolving = _KNOWN_MISSING & resolved

    for pid in sorted(missing & _KNOWN_MISSING):
        print(f"  [known-missing] {pid} -> {declared[pid]}")

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
