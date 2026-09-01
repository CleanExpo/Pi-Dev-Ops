"""Regression tests for .github/scripts/baseline_ratchet.py (RA-7400).

The guard's whole value is that it fails when a baseline grows. Two ways it
could stop doing that without anyone noticing, both tested here:

  * `parse_rls` under-reports. It scans quoted strings, and one comment in
    rls_coverage.sql contains "Supabase's advisor". An apostrophe-naive scan
    reads that as an opening quote and swallows the rest of the block, returning
    5 entries where there are 9 -- so four real entries look absent, and adding
    one more would compare a wrong set against a wrong set.
  * `compare` stops flagging a raised value. That direction leaves the entry
    COUNT unchanged, so nothing about the file's shape reveals it.

Both are silent failures of the checker itself, which is the failure mode
RA-7400 exists to close one level down.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "baseline_ratchet.py"


def _load():
    """Import the script by path — `.github/scripts` is not an importable package."""
    spec = importlib.util.spec_from_file_location("baseline_ratchet", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ratchet = _load()


# Both hazards live in the comments here, deliberately. An earlier version of
# this fixture only carried the apostrophe, and it PASSED with comment-stripping
# removed -- a test whose name promised a guard it did not provide. The
# commented-out tuple is what actually bites: unstripped, it is
# indistinguishable from a real entry.
RLS_SQL = """
-- THE BASELINE IS SHRINK-ONLY.
-- These carry RLS and no policy -- the state Supabase's advisor reports as
-- rls_enabled_no_policy -- so they enter the baseline as they actually are.
-- Example of the format, NOT an entry: ('phantom_table', 'illustration only'),
insert into _rls_baseline (tbl, why) values
  ('youtube_topics',      'RLS off'),
  ('persona_traits',      'RLS off'),
  -- superseded, left for context: ('retired_table', 'was RLS off'),
  ('continuation_horizons', 'RLS on but zero policies'),
  ('workflow_runs',       'RLS on, zero policies live');
"""


def test_parse_rls_ignores_tuples_that_only_appear_inside_comments():
    """Exactly the four real entries — no phantoms from illustrative comments.

    A commented-out tuple is the sharp case: it is textually identical to a real
    entry, so a parser that does not strip comments invents baseline entries
    that do not exist. Those phantoms sit in BOTH the before and after sets, so
    they hide nothing on their own — but a phantom that appears or disappears
    when a comment is edited registers as an addition or a removal of an entry
    nobody touched, which trains readers to ignore this gate.
    """
    assert set(ratchet.parse_rls(RLS_SQL)) == {
        "youtube_topics",
        "persona_traits",
        "continuation_horizons",
        "workflow_runs",
    }


def test_parse_rls_matches_the_real_file():
    """Guards against the real baseline drifting out of the parser's reach."""
    real = Path(__file__).resolve().parents[1] / "supabase/tests/pgtap/rls_coverage.sql"
    if not real.exists():  # pragma: no cover - the file is tracked
        pytest.skip("rls_coverage.sql absent")
    parsed = ratchet.parse_rls(real.read_text(encoding="utf-8"))
    assert len(parsed) >= 4, f"parser found only {len(parsed)} entries — under-reporting"
    assert "workflow_runs" in parsed


def test_parse_tsv_reads_count_and_key():
    text = "# comment\n\n2612\tabc123\tapp/server/big.py\n40\tdef456\tswarm/x.py::run\n"
    assert ratchet.parse_tsv(text) == {"app/server/big.py": 2612, "swarm/x.py::run": 40}


def test_parse_kv_reads_numeric_thresholds():
    assert ratchet.parse_kv("# c\nicon_imports=1\n") == {"icon_imports": 1}


def test_added_key_is_a_failure():
    problems = ratchet.compare("f", {"a": 1}, {"a": 1, "b": 2}, set())
    assert len(problems) == 1 and "ADDED" in problems[0] and "b" in problems[0]


def test_raised_value_is_a_failure_even_though_the_count_is_unchanged():
    before, after = {"a": 100}, {"a": 200}
    assert len(before) == len(after)  # the reason a count-based check misses this
    problems = ratchet.compare("f", before, after, set())
    assert len(problems) == 1 and "RAISED" in problems[0]


def test_removal_and_lowering_pass_because_that_is_the_ratchet_direction():
    assert ratchet.compare("f", {"a": 1, "b": 2}, {"a": 1}, set()) == []
    assert ratchet.compare("f", {"a": 300}, {"a": 100}, set()) == []


def test_allow_list_is_per_key_not_a_blanket_disable():
    problems = ratchet.compare("f", {}, {"ok": 1, "nope": 1}, {"ok"})
    assert len(problems) == 1 and "nope" in problems[0]


def test_no_baseline_entries_at_base_is_not_reported_as_clean(tmp_path, capsys, monkeypatch):
    """A parser returning nothing must not read as 'no additions'.

    `check_one` treats an empty `before` as unverifiable rather than as an empty
    baseline every addition is measured against — otherwise a parser that broke
    would report every file as clean, which is the shape of every defect this
    guard was written for.
    """
    monkeypatch.setattr(ratchet, "git_show", lambda ref, path: "nothing parseable here")
    target = tmp_path / "b.txt"
    target.write_text("1\tfp\tsome/key\n", encoding="utf-8")
    problems = ratchet.check_one(str(target), ratchet.parse_tsv, "BASE", set())
    assert problems == []
    assert "unverifiable" in capsys.readouterr().out


def test_baseline_allow_survives_hyphens_in_the_key(monkeypatch):
    """Same defect as smoke_surface_gate's trailer parser, same fix.

    Every key in these baselines is a file path and this repo has hyphenated
    directories (`remotion-studio/`), so `[^\\s-]+` truncating at the first
    hyphen was reachable, not theoretical: "remotion-studio/scripts/render.py"
    was read as "remotion" and authorised nothing.
    """
    class Result:
        returncode = 0
        stdout = "msg\n\nBaseline-Allow: remotion-studio/scripts/render.py -- generated\n"
    monkeypatch.setattr(ratchet.subprocess, "run", lambda *a, **k: Result())
    assert ratchet.allowed_keys("BASE") == {"remotion-studio/scripts/render.py"}


# --------------------------------------------------------------------------
# the coverage direction — RA-7402
# --------------------------------------------------------------------------

def test_removal_is_a_failure_in_the_coverage_direction():
    """Deleting a smoke entry shrinks what runs against the live deploy.

    The suite then reports the same green with less behind it, and nothing in
    the diff reads as a reduction. That is the whole reason this direction
    exists.
    """
    problems = ratchet.compare("m", {"a": None, "b": None}, {"a": None}, set(),
                               shrink_weakens=True)
    assert problems == ["m: REMOVED b"]


def test_addition_passes_in_the_coverage_direction():
    """The green control. Declaring MORE surfaces must never be blocked."""
    assert ratchet.compare("m", {"a": None}, {"a": None, "b": None}, set(),
                           shrink_weakens=True) == []


def test_the_default_direction_is_untouched_by_the_new_one():
    """Guards against inverting the baselines while adding the manifest.

    Every existing call site passes four positional arguments, so a default
    that flipped would silently reverse five baselines at once and the suite
    would still be green on the tests written before this parameter existed.
    """
    assert ratchet.compare("f", {"a": 1}, {"a": 1, "b": 2}, set()) != []   # added -> fails
    assert ratchet.compare("f", {"a": 1, "b": 2}, {"a": 1}, set()) == []   # removed -> passes


def test_the_allow_trailer_authorises_one_removal_and_not_its_neighbour():
    """The hatch is per key, never a blanket disable — same as the other way.

    Legitimate removals are the common case here (a genuinely deleted surface
    should lose its entry), so this path is load-bearing rather than
    theoretical.
    """
    problems = ratchet.compare("m", {"keep": None, "drop": None}, {}, {"drop"},
                               shrink_weakens=True)
    assert problems == ["m: REMOVED keep"]


# --------------------------------------------------------------------------
# the manifest parser
# --------------------------------------------------------------------------

MANIFEST = """{
  "horizontal": [
    {"name": "alpha", "path": "/api/pi-ceo/api/one", "method": "GET"},
    {"name": "beta",  "path": "/api/two",            "method": "POST"}
  ],
  "vertical": {"flow": "f", "steps": [
    {"action": "login", "path": "/api/auth/login"},
    {"action": "sse",   "path_template": "/api/x/{id}/logs"},
    {"action": "noop"}
  ]}
}"""


def test_parse_surfaces_covers_horizontal_names_and_vertical_steps():
    """RA-7402 named only `horizontal`; a deleted vertical step shrinks
    coverage identically, so both are keyed."""
    keys = ratchet.parse_surfaces(MANIFEST)
    assert "alpha" in keys and "beta" in keys
    assert "vertical:login:/api/auth/login" in keys
    assert "vertical:sse:/api/x/{id}/logs" in keys


def test_parse_surfaces_skips_a_vertical_step_with_no_path():
    """A step with nothing to key on must not become a phantom entry, which
    would then read as REMOVED the moment anything else changed."""
    assert not any(k.startswith("vertical:noop") for k in ratchet.parse_surfaces(MANIFEST))


def test_parse_surfaces_on_unparseable_json_yields_nothing():
    """Fail-closed feed for `check_one`.

    An unparseable manifest must return empty, not partial: empty trips the
    `if not before` guard and is reported as unverifiable, whereas a partial
    parse would report every unparsed entry as REMOVED.
    """
    assert ratchet.parse_surfaces("{not json") == {}


def test_parse_surfaces_matches_the_committed_manifest():
    manifest = _SCRIPT.parents[2] / ".github" / "smoke-surfaces.json"
    keys = ratchet.parse_surfaces(manifest.read_text(encoding="utf-8"))
    assert len(keys) > 50, "the real manifest should not parse to almost nothing"
    assert sum(k.startswith("vertical:") for k in keys) == 4


# --------------------------------------------------------------------------
# the registry
# --------------------------------------------------------------------------

def test_every_baseline_declares_a_direction():
    """BASELINES values are (parser, shrink_weakens). A bare parser left behind
    would raise at unpack time in CI rather than here."""
    for path, entry in ratchet.BASELINES.items():
        assert isinstance(entry, tuple) and len(entry) == 2, path
        assert callable(entry[0]) and isinstance(entry[1], bool), path


def test_only_the_coverage_manifest_ratchets_the_other_way():
    """Pins the direction assignment. Flipping one of the other five would
    silently stop it enforcing anything."""
    inverted = {p for p, (_, shrink) in ratchet.BASELINES.items() if shrink}
    assert inverted == {".github/smoke-surfaces.json"}
