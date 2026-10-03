"""Guard sweep 29/09: engine, calibration and policy guards that no test could fail without.

Each test below fails with its named guard removed (tests/mutation/jev_platform_mutants.py). Offline, temp dirs.
"""
# ruff: noqa: F811  (test parameters named `ws` request the imported fixture)
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from jev_scale_support import Recorder, git
from test_jev_platform_calibration import NOW, PROV, B, cases
from test_jev_platform_engine import RULE, budget, fake_post, ws  # noqa: F401  (the shared `ws` fixture)

from jev_platform import calibration as c
from jev_platform import engine, policy


# ---- engine.py

def test_a_selection_problem_sends_nothing_even_when_some_rules_are_known(ws):
    """guard sweep 29/09: one unknown id beside a known one must stop the call, not just be reported."""
    post = Recorder()
    out = engine.decide("anything", ["core-01", "bogus"], 1, post, budget(0.5))
    assert post.calls == [] and out["verdict"] == "escalate"
    assert "unknown_rule:bogus" in out["reasons"] and "not_sent" in out["reasons"]


def test_an_unreadable_record_file_is_corrupt_not_absent(ws):
    """guard sweep 29/09: a record that exists but does not parse is `corrupt`; absent is only a missing file."""
    engine.RECORDS.mkdir()
    (engine.RECORDS / f"{RULE}.json").write_text("{not json")
    assert engine.load_record(RULE) == {"corrupt": True}
    out = engine.decide("x", [RULE], 1, fake_post({}), budget(0.5))
    assert out["findings"][0]["state"] == "corrupt" and out["findings"][0]["result"] == "uncertain"


def test_a_missing_record_rates_fail_absent(ws):
    """guard sweep 29/09: no record is FAIL/absent, never an exception or a pass."""
    assert engine.artifact_rating("missing") == ("FAIL", ["absent"])


@pytest.fixture
def committed(ws, tmp_path, monkeypatch):
    """A calibrated record committed at HEAD of a temp repo that stands in for engine.ROOT."""
    monkeypatch.setattr(engine, "ROOT", tmp_path)
    engine.calibrate(RULE, fake_post(ws), budget())
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "-f", "records")
    git(tmp_path, "commit", "-qm", "records")
    assert engine.artifact_rating(RULE) == ("AAA", [])  # positive control: both halves hold
    return tmp_path


@pytest.mark.parametrize("name", [f"{RULE}.json", f"{RULE}.scored.jsonl"])
def test_untracked_records_are_capped_at_aa(committed, name):
    """guard sweep 29/09: AAA needs each file committed at HEAD, not merely an unchanged working copy."""
    git(committed, "rm", "-q", "--cached", str((engine.RECORDS / name).relative_to(committed)))
    git(committed, "commit", "-qm", "untrack")
    assert (engine.RECORDS / name).exists()  # control: the working copy is untouched
    assert engine.artifact_rating(RULE) == ("AA", ["not bound to HEAD"])


def test_records_that_differ_from_head_are_capped_at_aa(committed):
    """guard sweep 29/09: a tracked record edited after commit (still verifying) is not AAA."""
    path = engine.RECORDS / f"{RULE}.json"
    path.write_text(json.dumps(json.loads(path.read_text()), indent=3) + "\n")
    assert engine.artifact_rating(RULE) == ("AA", ["not bound to HEAD"])


# ---- policy.py

def test_partial_coverage_rates_fail():
    """guard sweep 29/09: fewer rules evaluated than RULE_COUNT is coverage FAIL; all of them is A."""
    assert policy.overall_rating("AAA", True, 10)["coverage"] == "FAIL"
    assert policy.overall_rating("AAA", True, policy.RULE_COUNT)["coverage"] == "A"


# ---- calibration.py

def test_non_dict_label_provenance_is_corrupt():
    """guard sweep 29/09: provenance present but not a dict is `corrupt`, not usable."""
    r = c.build_record("r1", cases(), B, PROV, now=NOW)
    assert c.evaluate_state({**r, "label_provenance": "trust me"}, B, now=NOW) == "corrupt"


def test_a_failed_record_stays_failed_with_matching_bindings_and_fresh():
    """guard sweep 29/09 (HIGH): the stored state is returned; only a provisional record may be usable."""
    r = c.build_record("r1", cases(), B, PROV, now=NOW)
    assert c.evaluate_state({**r, "state": "failed_validation"}, B, now=NOW + timedelta(days=1)) == "failed_validation"


def test_verify_reports_missing_fields_instead_of_crashing():
    """guard sweep 29/09: an empty record is named, not a KeyError."""
    assert c.verify({}, []) == ["missing required fields"]


@pytest.mark.parametrize("key", ["threshold", "miss_rate_upper_95"])
def test_verify_names_an_edit_to_only_the_threshold_or_only_the_bound(key):
    """guard sweep 29/09: every recomputed key is compared, including the threshold and the bound."""
    s = cases()
    r = c.build_record("r1", s, B, PROV, now=NOW)
    if key == "threshold":
        r["threshold"] = 0.95
    else:
        r["miss_rate_upper_95"] = {**r["miss_rate_upper_95"], "bound": 0.001}
    assert c.verify(r, s) == [f"{key} does not recompute"]


def test_too_few_compliant_validation_cases_fails_the_rule():
    """guard sweep 29/09: 60 violations but only 10 compliant cases in validation is failed_validation."""
    calib, valid = c.split(cases(2000))
    v = [x for x in valid if not x["label"]][:60] + [x for x in valid if x["label"]][:10]
    r = c.build_record("r1", calib + v, B, PROV, now=NOW)
    assert r["split"]["validation"] == 70 and r["threshold"] == 0.5
    assert r["state"] == "failed_validation"


def test_no_qualifying_threshold_is_its_own_state():
    """guard sweep 29/09: when every calibration violation scores >= 0.95, no threshold freezes."""
    r = c.build_record("r1", cases(violation_noul=0.99), B, PROV, now=NOW)
    assert r["threshold"] is None and r["state"] == "no_qualifying_threshold"
