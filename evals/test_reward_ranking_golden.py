"""Prove-It Gate (RA-7020) — golden regression eval for the correctness-first reward.

Deterministic, code-checkable assertions over tao_reward.correctness_first_reward
and tao_reward.select_best (AlphaDev discipline: correctness gates, cost ranks).
No LLM judge. Pins the correctness-first invariant — a correct candidate always
outranks an incorrect one — against silent regression.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.server import tao_reward as tr

_GOLDEN = Path(__file__).parent / "golden" / "reward_ranking.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())
_REWARD = _DATA["reward"]
_INVALID = _DATA["invalid"]
_SELECTION = _DATA["selection"]


@pytest.mark.parametrize("case", _REWARD, ids=lambda c: f"correct={c['correct']},cost={c['cost']}")
def test_reward_matches_expected(case: dict) -> None:
    got = tr.correctness_first_reward(case["correct"], case["cost"])
    assert got == pytest.approx(case["expected"]), (
        f"reward(correct={case['correct']}, cost={case['cost']}) = {got!r} "
        f"!= {case['expected']!r}"
    )


def test_correct_always_outranks_incorrect() -> None:
    """The invariant: any correct reward (even at max cost) exceeds any incorrect one."""
    worst_correct = tr.correctness_first_reward(True, 1.0)
    best_incorrect = tr.correctness_first_reward(False, 0.0)
    assert worst_correct > best_incorrect


@pytest.mark.parametrize("case", _INVALID, ids=lambda c: f"cost={c['cost']},a={c['alpha']},b={c['beta']}")
def test_invariant_guard_raises(case: dict) -> None:
    with pytest.raises(ValueError):
        tr.correctness_first_reward(
            case["correct"], case["cost"], alpha=case["alpha"], beta=case["beta"]
        )


@pytest.mark.parametrize("case", _SELECTION, ids=lambda c: c["winner"])
def test_select_best_picks_expected(case: dict) -> None:
    candidates = [tr.Candidate(**c) for c in case["candidates"]]
    chosen = tr.select_best(candidates)
    assert chosen is not None
    assert chosen.id == case["winner"], (
        f"select_best chose {chosen.id!r}, expected {case['winner']!r}"
    )


def test_select_best_empty_returns_none() -> None:
    assert tr.select_best([]) is None
