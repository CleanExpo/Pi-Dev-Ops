#!/usr/bin/env python3
"""Route inventory — which FastAPI routes are declared in the surface map (RA-7401).

`scripts/smoke_test_e2e.py` iterates the DECLARED surfaces in
`.github/smoke-surfaces.json`. A route missing from that file has nothing
exercising it end-to-end against the live deploy, which is the condition
CLAUDE.md's surface-treatment prohibition exists to prevent. So the first
question is simply: which routes are missing?

WHY THIS EXISTS RATHER THAN A GREP. RA-7401 answered that question with
`grep -rnE '@router\\.(get|post|...)' app/server/routes/*.py`, reasoning that
"no `include_router` call passes a `prefix=`, so decorator paths are complete
as written". The premise is true and the conclusion does not follow: the prefix
is set on the CONSTRUCTOR instead, `APIRouter(prefix="/api/nexus")`, in 13 of
the 29 route modules. Decorator text is therefore not the route path, and three
of that ticket's top-five "concentration" modules were prefixed ones.

The grep has three further blind spots, each silent:

  * it matches only a variable literally named `router`, so nexus.py's
    `webhooks_router` (5 routes) is invisible;
  * a decorator whose path is not a same-line string literal is missed;
  * anything mounted dynamically is missed by construction.

FastAPI already knows all of this. `app.openapi()["paths"]` is the resolved
truth — prefixes applied, methods enumerated, nothing inferred. Reading it
removes the entire class of error rather than patching the instance somebody
tripped over, which is the lesson CLAUDE.md's Observability section records
about the table-count command that under-reported by four.

`app.routes` is NOT the shortcut it appears to be: this app's routers are
attached lazily and show up there as 29 opaque `_IncludedRouter` objects with
no path, so a naive walk of it reports 5 routes out of 128.

The matcher is imported from `.github/scripts/smoke_surface_gate.py` rather
than reimplemented, so the proxy-prefix and `{param}` rules have one definition
and one set of tests (tests/test_smoke_surface_gate.py).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys
from collections import Counter

REPO = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = REPO / ".github" / "smoke-surfaces.json"
GATE = REPO / ".github" / "scripts" / "smoke_surface_gate.py"

# `python scripts/route_inventory.py` puts scripts/ on sys.path, not the repo
# root, so `import app.server.main` fails unless the root is added explicitly.
# Prepending keeps it working from any cwd and under pytest alike.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

METHODS = ("get", "post", "put", "patch", "delete")

# Controls. The matcher must be able to answer BOTH ways before any count it
# produces means anything: a matcher stuck on False reports every route as an
# undeclared gap, and one stuck on True reports a clean system. Zero findings
# from a broken comparison looks exactly like zero findings from a healthy one.
CONTROL_DECLARED = "/api/autonomy/status"
CONTROL_ABSENT = "/api/definitely-not-real"


def load_gate():
    """The surface gate module, for `normalise()` — one definition, one test."""
    spec = importlib.util.spec_from_file_location("smoke_surface_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_api_paths() -> dict:
    """`{path: {method: operation}}` straight from FastAPI, prefixes resolved."""
    from app.server.main import app

    return app.openapi().get("paths", {})


def route_entries(paths: dict) -> list:
    """One (path, METHOD, tag) per operation. Entries, not paths.

    A declared `GET /x` says nothing about whether `POST /x` is exercised, and
    the smoke suite probes a method, so the entry is the honest unit.
    """
    out = []
    for path, operations in paths.items():
        for method, spec in operations.items():
            if method.lower() not in METHODS:
                continue
            tags = spec.get("tags") or ["(untagged)"]
            out.append((path, method.upper(), tags[0]))
    return sorted(out)


def declared_paths(gate) -> set:
    """Declared (METHOD, path) pairs, proxy prefix and query string stripped.

    METHOD is part of the key, and that is not a detail. The manifest declares
    a method and `smoke_test_e2e.py` probes that method, so keying on path
    alone would let a declared `GET /api/triggers` mark `POST /api/triggers`
    as covered when nothing exercises the POST at all. Measured: it silently
    absorbed 2 extra entries the first time this was written, which is the
    same path-versus-entry unit confusion RA-7401 was itself corrected for.
    """
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        (surface.get("method", "GET").upper(), gate.normalise(surface["path"]))
        for surface in manifest.get("horizontal", [])
        if surface.get("path")
    }


def _as_regex(path: str) -> str:
    """`/a/{id}/b` -> a regex matching `/a/anything/b`."""
    escaped = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
    return re.sub(r"\{[^}]+\}", "[^/]+", escaped)


def is_declared(route: str, method: str, declared: set) -> bool:
    """Match either direction, for this method only.

    The manifest carries concrete paths (`/api/projects/pi-dev-ops/findings`);
    the app carries templates (`/api/projects/{project_id}/findings`). Compared
    as strings they never match, which is most of how the naive count reached
    106 undeclared against an actual 71.
    """
    for candidate_method, candidate in declared:
        if candidate_method != method.upper():
            continue
        if candidate == route:
            return True
        if re.fullmatch(_as_regex(candidate), route):
            return True
        if re.fullmatch(_as_regex(route), candidate):
            return True
    return False


def run_controls(declared: set) -> "str | None":
    """Prove the matcher can answer both ways. Returns an error, or None."""
    if not is_declared(CONTROL_DECLARED, "GET", declared):
        return f"control failed: {CONTROL_DECLARED} is declared but read as undeclared"
    if is_declared(CONTROL_ABSENT, "GET", declared):
        return f"control failed: {CONTROL_ABSENT} does not exist but read as declared"
    return None


def report(entries: list, paths: dict, declared: set, undeclared: list) -> None:
    """Human-readable summary, grouped by OpenAPI tag."""
    print(f"route entries      : {len(entries)}")
    print(f"distinct paths     : {len(paths)}")
    print(f"declared in map    : {len(declared)}")
    print(f"UNDECLARED entries : {len(undeclared)}")
    print(f"UNDECLARED paths   : {len(set(e[0] for e in undeclared))}\n")
    for tag, count in Counter(e[2] for e in undeclared).most_common():
        print(f"  {tag:<18} {count}")
    print()
    for path, method, tag in sorted(undeclared, key=lambda e: (e[2], e[0])):
        print(f"{tag:<18} {method:<6} {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    gate = load_gate()
    paths = open_api_paths()
    entries = route_entries(paths)
    declared = declared_paths(gate)

    # FAIL CLOSED, both directions. An import that yields no routes, or a
    # manifest that parses to nothing, must not read as "no gap" — that is a
    # verdict produced by never having looked.
    if not entries:
        print("route-inventory: the app exposed 0 routes. Refusing to report a "
              "gap of zero from an app that did not load.", file=sys.stderr)
        return 2
    if not declared:
        print(f"route-inventory: parsed 0 declared paths from {MANIFEST.name}. "
              "Refusing to call every route undeclared.", file=sys.stderr)
        return 2

    failure = run_controls(declared)
    if failure:
        print(f"route-inventory: {failure}", file=sys.stderr)
        return 2

    undeclared = [e for e in entries if not is_declared(e[0], e[1], declared)]

    if args.json:
        print(json.dumps({
            "entries": len(entries),
            "paths": len(paths),
            "declared": len(declared),
            "undeclared": [{"path": p, "method": m, "tag": t} for p, m, t in undeclared],
        }, indent=2))
    else:
        report(entries, paths, declared, undeclared)
    return 0


if __name__ == "__main__":
    sys.exit(main())
