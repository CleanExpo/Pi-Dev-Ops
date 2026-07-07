"""Prove-It Gate slice 3a (RA-7014) — calibration math, deterministic tests.

These prove the gate logic (disagreement %, run-to-run instability, the <20%
calibrated verdict) without any model call, using synthetic judge verdicts.
"""
from __future__ import annotations

import pytest

from evals.calibration import (
    MAX_DISAGREEMENT,
    CalibrationCase,
    compute_calibration,
    format_report,
)


def _case(cid: str, expert: bool, votes: list[bool]) -> CalibrationCase:
    return CalibrationCase(case_id=cid, expert_pass=expert, judge_passes=votes)


def test_perfect_agreement_is_calibrated():
    cases = [_case(f"c{i}", True, [True, True, True]) for i in range(5)] + [
        _case(f"d{i}", False, [False, False, False]) for i in range(5)
    ]
    r = compute_calibration(cases)
    assert r.disagreement_rate == 0.0
    assert r.flip_rate == 0.0
    assert r.calibrated


def test_disagreement_over_bar_blocks_calibration():
    # 3/10 disagree = 30% > 20% bar → not calibrated
    cases = [_case(f"ok{i}", True, [True, True, True]) for i in range(7)] + [
        _case(f"bad{i}", True, [False, False, False]) for i in range(3)
    ]
    r = compute_calibration(cases)
    assert r.disagreement_rate == pytest.approx(0.30)
    assert not r.calibrated
    assert set(r.disagreements) == {"bad0", "bad1", "bad2"}


def test_disagreement_just_under_bar_is_calibrated():
    # 1/6 ≈ 16.7% < 20% → calibrated on the agreement axis
    cases = [_case(f"ok{i}", True, [True]) for i in range(5)] + [_case("bad", True, [False])]
    r = compute_calibration(cases)
    assert r.disagreement_rate < MAX_DISAGREEMENT
    assert r.calibrated


def test_majority_vote_across_runs():
    # judge says PASS twice, FAIL once → majority PASS, matches expert PASS (agrees)
    # but it flipped across runs → counted as unstable
    cases = [_case("c", True, [True, True, False])]
    r = compute_calibration(cases)
    assert r.disagreements == []          # majority agrees with expert
    assert r.unstable == ["c"]            # but not unanimous
    assert r.flip_rate == 1.0


def test_instability_over_bar_blocks_even_when_agreeing():
    # every case agrees on majority but all flip → flip_rate 100% > 20% → not calibrated
    cases = [_case(f"c{i}", True, [True, True, False]) for i in range(10)]
    r = compute_calibration(cases)
    assert r.disagreement_rate == 0.0
    assert r.flip_rate == 1.0
    assert not r.calibrated  # a coin-flip judge that happens to agree is still untrustworthy


def test_uneven_run_counts_rejected():
    with pytest.raises(ValueError):
        compute_calibration([_case("a", True, [True, True]), _case("b", True, [True])])


def test_empty_rejected():
    with pytest.raises(ValueError):
        compute_calibration([])


def test_format_report_states_verdict():
    r = compute_calibration([_case("c", True, [True])])
    assert "CALIBRATED" in format_report(r)
