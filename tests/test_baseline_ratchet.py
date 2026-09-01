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
