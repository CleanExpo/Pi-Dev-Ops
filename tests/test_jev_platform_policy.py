"""Offline controls for jev_platform.policy (PLAN.md rev 4 expectations)."""
from __future__ import annotations

import pytest

from jev_platform import policy as p

P = "provisional"


@pytest.mark.parametrize("noul, expected", [
    (0.099, p.FAIL), (0.10, p.UNCERTAIN), (0.39, p.UNCERTAIN), (0.40, p.UNCERTAIN),
    (0.60, p.UNCERTAIN), (0.61, p.UNCERTAIN), (0.8999, p.UNCERTAIN), (0.90, p.PASS), (0.99, p.PASS),
])
def test_boundaries_at_threshold_0_9(noul, expected):
    assert p.classify_rule(noul, 0.9, P, True)[0] == expected


def test_boundaries_at_threshold_0_5():
    assert p.classify_rule(0.61, 0.5, P, True)[0] == p.PASS
    assert p.classify_rule(0.60, 0.5, P, True)[0] == p.UNCERTAIN


@pytest.mark.parametrize("state", ["absent", "corrupt", "no_qualifying_threshold", "failed_validation", "stale"])
def test_unusable_calibration_never_passes_or_fails(state):
    assert p.classify_rule(0.99, 0.9, state, True) == (p.UNCERTAIN, state)
    assert p.classify_rule(0.01, 0.9, state, True) == (p.UNCERTAIN, state)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -0.1, 1.1, None, "0.9", True])
def test_invalid_scores_are_signal_unavailable(bad):
    assert p.classify_rule(bad, 0.5, P, True) == (p.UNCERTAIN, "signal_unavailable")


def test_invalid_response_overrides_a_high_score():
    assert p.classify_rule(0.99, 0.5, P, False) == (p.UNCERTAIN, "signal_unavailable")


def test_selection_problems():
    known = {"a", "b"}
    assert p.selection_problems([], known) == ["empty_selection"]
    assert p.selection_problems(["a", "zz"], known) == ["unknown_rule:zz"]
    assert p.selection_problems(["a", "a"], known) == ["duplicate_rule_ids"]
    assert p.selection_problems(["a", "b"], known) == []


def _f(rule, result, reason="x"):
    return {"rule": rule, "result": result, "reason": reason}


@pytest.mark.parametrize("claimed", [0, 1, 2, 3, None, "2", True])
def test_recommendation_never_allows(claimed):
    rec = p.recommend([_f("a", p.PASS), _f("b", p.PASS)], claimed, [])
    assert rec["verdict"] == p.ESCALATE and rec["mode"] == "shadow"
    assert "allow" not in str(rec).lower() and "no_objection" not in str(rec)


def test_class_reason():
    assert p.class_reason(2) == "class_unverified"
    for c in (3, None, "1", True, 4):
        assert p.class_reason(c) == "founder_class"


def test_planted_violation_is_refused_and_cited():
    rec = p.recommend([_f("ch3-4-27", p.FAIL), _f("b", p.PASS)], 1, [])
    assert rec["verdict"] == p.REFUSE and rec["refused_by"] == ["ch3-4-27"]


def test_invalid_selection_blocks_refuse_and_escalates():
    rec = p.recommend([_f("a", p.FAIL)], 1, ["duplicate_rule_ids"])
    assert rec["verdict"] == p.ESCALATE and "duplicate_rule_ids" in rec["reasons"]


def test_coverage_is_reported():
    rec = p.recommend([_f("a", p.PASS)], 1, [])
    assert rec["evaluated"] == 1 and rec["unevaluated"] == 537


def test_overall_rating_is_minimum_and_at_most_a_for_judgment():
    r = p.overall_rating("AAA", True, 1)
    assert r["judgment"] == "A" and r["overall"] == "FAIL"
    assert p.overall_rating("AAA", False, 538)["judgment"] == "FAIL"
