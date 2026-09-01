"""Regression tests for .github/scripts/smoke_surface_gate.py (RA-7398).

The gate this replaces passed whenever `.github/smoke-surfaces.json` appeared in
the diff, so a whitespace change satisfied it. The test that matters most here is
`test_cosmetic_touch_of_the_manifest_no_longer_satisfies_the_gate` -- that is the
exact bypass, and it must be seen failing against the old behaviour before any
green from this gate means anything.

Every test below was verified to FAIL against a deliberately broken
implementation, not merely to pass against the working one.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "smoke_surface_gate.py"


def _load():
    """Import by path — `.github/scripts` is not an importable package."""
    spec = importlib.util.spec_from_file_location("smoke_surface_gate", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()


def manifest(*entries) -> str:
    return json.dumps({"version": 1, "horizontal": list(entries), "vertical": {}})


def entry(name, path="/api/x"):
    return {"name": name, "path": path, "method": "GET", "expected_status": 200}


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

def test_proxy_prefix_is_stripped_so_declared_routes_match_backend_paths():
    """/api/pi-ceo/api/autonomy/status declares the FastAPI route /api/autonomy/status.

    Measured 2026-09-01: comparing these literally called 106 routes undeclared
    where the true figure was 66. A gate that over-reports gets ignored.
    """
    parsed = gate.parse_manifest(manifest(entry("a", "/api/pi-ceo/api/autonomy/status")))
    assert parsed["paths"] == {"/api/autonomy/status"}


def test_query_strings_are_stripped():
    parsed = gate.parse_manifest(manifest(entry("a", "/api/routines?limit=1")))
    assert parsed["paths"] == {"/api/routines"}


def test_unparseable_manifest_is_empty_not_silently_entryless():
    """`main` treats this as fatal; it must never read as 'nothing declared'."""
    assert gate.parse_manifest("{not json") == {}


# --------------------------------------------------------------------------
# route derivation
# --------------------------------------------------------------------------

def test_nextjs_route_path_is_derived_from_the_file_path():
    assert gate.nextjs_route("dashboard/app/api/zte/route.ts") == "/api/zte"
    assert gate.nextjs_route("dashboard/app/api/actions/commit/route.ts") == "/api/actions/commit"


def test_dynamic_segments_are_skipped_rather_than_guessed():
    """`[...path]` is a catch-all proxy — no concrete entry can declare it."""
    assert gate.nextjs_route("dashboard/app/api/pi-ceo/[...path]/route.ts") is None


def test_non_route_files_derive_nothing():
    assert gate.nextjs_route("dashboard/components/Button.tsx") is None
    assert gate.nextjs_route("app/server/routes/auth.py") is None


def test_declared_matches_template_parameters():
    paths = {"/api/projects/{project_id}/findings"}
    assert gate.declared("/api/projects/pi-dev-ops/findings", paths)
    assert not gate.declared("/api/projects/pi-dev-ops/other", paths)


# --------------------------------------------------------------------------
# the rule
# --------------------------------------------------------------------------

BEFORE = gate.parse_manifest(manifest(entry("existing")))


def test_modifying_an_existing_file_demands_nothing():
    """The false positive that taught people to touch the manifest cosmetically.

    A bug-fix to an existing component cannot honestly add a surface entry, so
    the old gate's only satisfiable answer was a cosmetic edit. `added` is empty
    for a modification, so nothing is required.
    """
    assert gate.evaluate([], BEFORE, BEFORE, set()) == []


def test_adding_a_component_without_declaring_anything_fails():
    problems = gate.evaluate(["dashboard/components/New.tsx"], BEFORE, BEFORE, set())
    assert len(problems) == 1 and "declared no new surface" in problems[0]


def test_cosmetic_touch_of_the_manifest_no_longer_satisfies_the_gate():
    """THE BYPASS. Reordering or reformatting changes the file, not the entries.

    The replaced gate asked only whether the filename appeared in the diff, so
    this exact case passed. The entry SET is identical here, so it must fail.
    """
    reordered = gate.parse_manifest(manifest(entry("existing", "/api/x")))
    assert reordered["names"] == BEFORE["names"]  # the touch changed nothing real
    problems = gate.evaluate(["dashboard/components/New.tsx"], BEFORE, reordered, set())
    assert len(problems) == 1 and "declared no new surface" in problems[0]


def test_declaring_a_new_surface_passes():
    after = gate.parse_manifest(manifest(entry("existing"), entry("new-thing")))
    assert gate.evaluate(["dashboard/components/New.tsx"], BEFORE, after, set()) == []


def test_a_new_route_declared_under_the_wrong_path_is_named():
    """Growth alone is not enough when the path is derivable."""
    after = gate.parse_manifest(manifest(entry("existing"), entry("unrelated", "/api/somewhere")))
    problems = gate.evaluate(["dashboard/app/api/brand-new/route.ts"], BEFORE, after, set())
    assert any("/api/brand-new" in p and "no entry" in p for p in problems)


def test_a_new_route_declared_correctly_passes():
    after = gate.parse_manifest(manifest(entry("existing"), entry("bn", "/api/brand-new")))
    assert gate.evaluate(["dashboard/app/api/brand-new/route.ts"], BEFORE, after, set()) == []


def test_surface_allow_is_per_file_not_a_blanket_disable():
    added = ["dashboard/components/Helper.tsx", "dashboard/components/Real.tsx"]
    problems = gate.evaluate(added, BEFORE, BEFORE, {"dashboard/components/Helper.tsx"})
    assert len(problems) == 1
    assert "Real.tsx" in problems[0] and "Helper.tsx" not in problems[0]


def test_allowing_every_added_file_passes():
    added = ["dashboard/components/Helper.tsx"]
    assert gate.evaluate(added, BEFORE, BEFORE, set(added)) == []


# --------------------------------------------------------------------------
# the trailer parser — untested until an end-to-end control caught it failing
# --------------------------------------------------------------------------

def test_surface_allow_survives_hyphens_in_the_path(monkeypatch):
    """The path is the first whitespace-delimited token, hyphens included.

    The original pattern was `[^\\s-]+`, written to stop before the " -- why"
    separator. It stopped at the first hyphen in the PATH instead, so
    "dashboard/app/api/scratch-route/route.ts" silently became
    "dashboard/app/api/scratch" and authorised nothing — the hatch looked
    applied and did nothing.

    The unit test above missed this entirely because it passed the allowed set
    in directly and never ran this function. An end-to-end control caught it.
    """
    monkeypatch.setattr(
        gate, "git",
        lambda *a: "scratch\n\nSurface-Allow: dashboard/app/api/scratch-route/route.ts -- control\n",
    )
    assert gate.allowances("BASE") == {"dashboard/app/api/scratch-route/route.ts"}


def test_surface_allow_ignores_the_reason_text():
    """Only the token is the key; the prose after ' -- ' is for the reviewer."""
    import re
    line = "Surface-Allow: a/b.tsx -- because it is a helper, not a surface"
    assert re.findall(r"^Surface-Allow:\s*(\S+)", line, re.M) == ["a/b.tsx"]
