"""Regression tests for scripts/route_inventory.py (RA-7401).

RA-7401's original count came from a grep that was wrong in principle: it read
decorator text, while 13 of 29 route modules set their prefix on
`APIRouter(prefix=...)`. The script under test reads FastAPI's resolved OpenAPI
schema instead, so the tests that matter most here are:

  * `test_matcher_does_not_cross_a_path_separator` — a `{param}` that expanded
    to `.*` would silently match half the app and report a gap of nearly zero.
  * `test_controls_catch_a_matcher_stuck_*` — the fail-closed pair. A matcher
    that cannot answer both ways produces a number indistinguishable from a
    healthy system, which is the defect this whole ticket family is about.

Every test below was verified to FAIL against a deliberately broken
implementation, not merely to pass against the working one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "route_inventory.py"


def _load():
    spec = importlib.util.spec_from_file_location("route_inventory", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inv = _load()


# --------------------------------------------------------------------------
# entries, not paths
# --------------------------------------------------------------------------

SPEC = {
    "/api/one": {"get": {"tags": ["alpha"]}, "post": {"tags": ["alpha"]}},
    "/api/two": {"get": {}},
    "/api/three": {"get": {"tags": ["beta"]}, "parameters": [{"name": "x"}]},
}


def test_one_entry_per_method_not_per_path():
    """`GET /x` being declared says nothing about `POST /x`.

    The smoke suite probes a method, so collapsing to paths would report a
    route as covered on the strength of a different verb entirely.
    """
    entries = inv.route_entries(SPEC)
    assert len(entries) == 4
    assert ("/api/one", "GET", "alpha") in entries
    assert ("/api/one", "POST", "alpha") in entries


def test_non_http_keys_are_not_mistaken_for_methods():
    """OpenAPI path items carry `parameters` alongside verbs."""
    entries = inv.route_entries(SPEC)
    assert not any(m == "PARAMETERS" for _, m, _ in entries)
    assert ("/api/three", "GET", "beta") in entries


def test_untagged_operations_get_a_placeholder_tag():
    assert ("/api/two", "GET", "(untagged)") in inv.route_entries(SPEC)


# --------------------------------------------------------------------------
# the matcher
# --------------------------------------------------------------------------

def test_exact_path_matches():
    assert inv.is_declared("/api/me", "GET", {("GET", "/api/me")})


def test_template_on_the_declared_side_matches_a_concrete_route():
    assert inv.is_declared("/api/projects/pi-dev-ops/findings", "GET",
                           {("GET", "/api/projects/{project_id}/findings")})


def test_template_on_the_route_side_matches_a_concrete_declaration():
    """The direction that actually occurs here.

    The manifest carries concrete paths; the app carries templates. A matcher
    that only expanded the declared side would call every parameterised route
    undeclared.
    """
    assert inv.is_declared("/api/projects/{project_id}/findings", "GET",
                           {("GET", "/api/projects/pi-dev-ops/findings")})


def test_a_genuine_non_match_is_reported_as_undeclared():
    assert not inv.is_declared("/api/definitely-not-real", "GET", {("GET", "/api/me"), ("GET", "/api/health")})


def test_matcher_does_not_cross_a_path_separator():
    """`{id}` is `[^/]+`, never `.*`.

    With `.*` the single declared entry `/api/sessions/{sid}/logs` would
    swallow unrelated deeper routes and the undeclared count would collapse
    toward zero — a gate reporting success because it stopped discriminating.
    """
    assert not inv.is_declared("/api/a/b/c", "GET", {("GET", "/api/a/{id}")})
    assert not inv.is_declared("/api/a/{id}", "GET", {("GET", "/api/a/b/c")})


def test_regex_metacharacters_in_a_path_are_escaped():
    """A literal dot must not act as a wildcard."""
    assert not inv.is_declared("/api/vXbeta", "GET", {("GET", "/api/v.beta")})
    assert inv.is_declared("/api/v.beta", "GET", {("GET", "/api/v.beta")})


# --------------------------------------------------------------------------
# the controls — the fail-closed pair
# --------------------------------------------------------------------------

def test_controls_pass_against_a_healthy_declared_set():
    assert inv.run_controls({("GET", inv.CONTROL_DECLARED)}) is None


def test_controls_catch_a_matcher_stuck_on_undeclared():
    """A matcher that never matches reports every route as a gap."""
    problem = inv.run_controls(set())
    assert problem and inv.CONTROL_DECLARED in problem


def test_controls_catch_a_matcher_stuck_on_declared():
    """A matcher that matches everything reports a clean system.

    One all-template entry is not enough to demonstrate this, and finding that
    out is the point: `{param}` is `[^/]+`, so a template only matches paths of
    its own segment count. The two controls differ in depth
    (`/api/autonomy/status` is three segments, `/api/definitely-not-real` two),
    so over-matching takes one template per depth. That the separator rule
    makes this hard to construct is the rule doing its job.
    """
    problem = inv.run_controls({("GET", "/api/{a}"), ("GET", "/api/{a}/{b}")})
    assert problem and inv.CONTROL_ABSENT in problem


# --------------------------------------------------------------------------
# against the real repo
# --------------------------------------------------------------------------

def test_declared_paths_reads_the_real_manifest_and_strips_the_proxy_prefix():
    """`/api/pi-ceo/api/autonomy/status` must normalise to the backend path.

    Without this the proxied routes — most of the manifest — compare as
    undeclared, which is how the naive count reached 106 against an actual 71.
    """
    declared = inv.declared_paths(inv.load_gate())
    assert declared, "the committed manifest should not parse to nothing"
    assert ("GET", "/api/autonomy/status") in declared
    assert not any(path.startswith("/api/pi-ceo") for _, path in declared)


def test_the_real_manifest_satisfies_the_controls():
    """If this fails, every count the script prints is meaningless."""
    assert inv.run_controls(inv.declared_paths(inv.load_gate())) is None


def test_a_declared_get_does_not_cover_the_same_paths_post():
    """Regression: the matcher keys on (method, path), never path alone.

    Found while adding this ticket's own first batch — declaring
    `GET /api/triggers` silently marked `POST /api/triggers` as covered, so the
    undeclared count fell by 11 when only 9 entries were added. The suite
    probes a method, so path-only coverage overstates it. This is the same
    path-versus-entry unit confusion RA-7401 was itself corrected for once.
    """
    declared = {("GET", "/api/triggers")}
    assert inv.is_declared("/api/triggers", "GET", declared)
    assert not inv.is_declared("/api/triggers", "POST", declared)
