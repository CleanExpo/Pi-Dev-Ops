#!/usr/bin/env python3
"""Smoke surface gate — a NEW surface must be DECLARED, not merely accompanied.

RA-1154 built this gate; RA-7398 found what it actually tests. The whole check
was one line of bash:

    MAP_UPDATED=$(git diff --name-only BASE HEAD | grep -Fx ".github/smoke-surfaces.json")

That asks whether the FILENAME appears in the diff. It never parsed the file and
never related a new route to a new entry, so any touch satisfied it: a whitespace
change, a reordering, or an entry added for an unrelated surface.

Nothing downstream compensates. `scripts/smoke_test_e2e.py` iterates the
*declared* surfaces, so an undeclared one is invisible to it by construction --
which is precisely the invisibility this gate exists to prevent.

TWO CHANGES, and the second is why the first is safe.

  1. It now compares PARSED ENTRY SETS, so a cosmetic touch no longer satisfies
     it, and where a path is derivable it names the exact undeclared surface.

  2. It only fires on files the PR ADDED. The old gate fired on any change under
     the interactive paths, which is what created the bypass habit: a bug-fix to
     an existing component cannot honestly add a surface entry, so a cosmetic
     touch was the only way past. Removing that false positive is what makes
     requiring a real entry reasonable rather than something to route around.

Net effect: stricter about the case it exists for, silent about the case it
never should have blocked.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from urllib.parse import urlsplit

MANIFEST = ".github/smoke-surfaces.json"
INTERACTIVE = ("dashboard/components/", "dashboard/app/api/", "app/server/routes/")

# The dashboard reaches the backend through dashboard/app/api/pi-ceo/[...path],
# so the manifest declares "/api/pi-ceo/api/autonomy/status" for the FastAPI
# route "/api/autonomy/status". Comparing those two literally reports a route as
# undeclared when it is declared -- measured on 2026-09-01, a naive comparison
# called 106 routes undeclared where the true figure was 66.
PROXY_PREFIX = "/api/pi-ceo"


def normalise(path: str) -> str:
    """A declared path reduced to the form a route template can be matched against."""
    bare = urlsplit(path).path
    if bare.startswith(PROXY_PREFIX):
        bare = bare[len(PROXY_PREFIX):] or "/"
    return bare


def parse_manifest(text: str) -> dict:
    """Entry names and normalised paths. Empty dict when the JSON will not parse.

    A parse failure must never read as "no entries" -- that would make every
    addition look declared. `main` treats an unparseable base as fatal.
    """
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    horizontal = data.get("horizontal") or []
    names = {e.get("name") for e in horizontal if isinstance(e, dict) and e.get("name")}
    paths = {normalise(e["path"]) for e in horizontal if isinstance(e, dict) and e.get("path")}
    return {"names": names, "paths": paths}


def nextjs_route(path: str) -> "str | None":
    """`dashboard/app/api/zte/route.ts` -> `/api/zte`; None when not derivable.

    Dynamic segments are skipped rather than guessed: `[...path]` is a catch-all
    proxy, not a surface anyone can declare a concrete entry for.
    """
    if not re.fullmatch(r"dashboard/app/api/.+/route\.tsx?", path):
        return None
    route = "/" + path[len("dashboard/app/"):].rsplit("/route.", 1)[0]
    return None if "[" in route else route


def declared(route: str, paths: set) -> bool:
    """Whether a route path is covered, treating `{param}` as a wildcard."""
    if route in paths:
        return True
    for candidate in paths:
        if "{" not in candidate:
            continue
        if re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", candidate), route):
            return True
    return False


def git(*args: str) -> "str | None":
    """Run git, returning stdout, or None when the command failed."""
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def added_files(base: str) -> list:
    """Files this PR ADDED under the interactive paths.

    --diff-filter=A is the whole point: a modification is not a new surface, and
    demanding a manifest entry for one is the false positive that taught people
    to touch the file cosmetically.
    """
    out = git("diff", "--diff-filter=A", "--name-only", base, "HEAD")
    if out is None:
        return []
    return [ln.strip() for ln in out.splitlines()
            if ln.strip().startswith(INTERACTIVE)]


def allowances(base: str) -> set:
    """Paths a commit trailer says are not interactive surfaces.

        Surface-Allow: <path> -- <why>

    Per file, never a blanket disable, and it lands in the diff where a reviewer
    reads it. Real cases exist -- a helper component, a types module -- and a
    gate with no hatch is deleted the first time it is wrong.
    """
    out = git("log", f"{base}..HEAD", "--format=%B") or ""
    return {m.strip() for m in re.findall(r"^Surface-Allow:\s*([^\s-]+)", out, re.M)}


def evaluate(added: list, before: dict, after: dict, allowed: set) -> list:
    """Problems with this PR, empty when it passes."""
    pending = [f for f in added if f not in allowed]
    if not pending:
        return []

    problems = []
    grew = after.get("names", set()) - before.get("names", set())
    if not grew:
        problems.append(
            "added interactive files but declared no new surface in "
            f"{MANIFEST}: " + ", ".join(sorted(pending))
        )

    for path in sorted(pending):
        route = nextjs_route(path)
        if route and not declared(route, after.get("paths", set())):
            problems.append(f"{path} adds route {route}, which has no entry in {MANIFEST}")
    return problems


def explain(problems: list) -> None:
    """Print the failure and how to satisfy it honestly."""
    print("\n🛑 SMOKE SURFACE GATE\n")
    for problem in problems:
        print(f"  {problem}")
        print(f"::error::smoke-surface-gate: {problem}")
    print(
        f"\nAdd an entry under 'horizontal' in {MANIFEST} with expected_status and"
        "\nbody_contains assertions, so scripts/smoke_test_e2e.py exercises the new"
        "\nsurface on the live deploy. Touching the file is no longer enough — the"
        "\nentry set has to grow (RA-7398).\n"
        "\nIf the added file is genuinely not an interactive surface, say so in the"
        "\ncommit message:\n\n    Surface-Allow: <path> -- <why>\n"
        "\nSee CLAUDE.md § Surface Treatment Prohibition."
    )


def main() -> int:
    base = os.environ.get("SURFACE_BASE_SHA", "").strip() or "origin/main"
    # FAIL CLOSED. An unresolvable base makes `added_files` return nothing, which
    # reads exactly like "this PR added no surfaces" and passes. That is the
    # defect this gate was written to stop, one level up.
    if git("show", f"{base}:.gitignore") is None:
        print(f"smoke-surface-gate: cannot resolve base '{base}'. CI needs "
              "fetch-depth: 0 and a resolvable SURFACE_BASE_SHA. Refusing to "
              "report a clean result it cannot support.")
        return 1

    added = added_files(base)
    if not added:
        print("smoke-surface-gate: no interactive files added — nothing to declare.")
        return 0

    base_manifest = git("show", f"{base}:{MANIFEST}")
    if base_manifest is None or not parse_manifest(base_manifest):
        print(f"smoke-surface-gate: cannot read or parse {MANIFEST} at {base}. "
              "Refusing to report a clean result it cannot support.")
        return 1

    try:
        with open(MANIFEST, encoding="utf-8") as handle:
            head_text = handle.read()
    except FileNotFoundError:
        print(f"smoke-surface-gate: {MANIFEST} is missing from the working tree.")
        return 1

    allowed = allowances(base)
    problems = evaluate(added, parse_manifest(base_manifest), parse_manifest(head_text), allowed)
    if problems:
        explain(problems)
        return 1

    print(f"smoke-surface-gate passed — {len(added)} interactive file(s) added, "
          "each covered by a new or existing declaration.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
