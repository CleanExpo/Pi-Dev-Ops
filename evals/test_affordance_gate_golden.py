"""Prove-It Gate (RA-7021) — golden regression eval for affordance-gated selection.

Deterministic assertions over tao_affordance.affordance_gated_score and
select_action (PaLM-SayCan "say x can"). Pins the "can" veto — p_afford=0 blocks
an action regardless of relevance — against silent regression. No LLM judge.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.server import tao_affordance as ta

_GOLDEN = Path(__file__).parent / "golden" / "affordance_gate.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())


@pytest.mark.parametrize("case", _DATA["score"], ids=lambda c: f"lm{c['p_lm']}xaf{c['p_afford']}")
def test_score_matches_expected(case: dict) -> None:
    got = ta.affordance_gated_score(case["p_lm"], case["p_afford"])
    assert got == pytest.approx(case["expected"]), (
        f"score({case['p_lm']}, {case['p_afford']}) = {got!r} != {case['expected']!r}"
    )


def test_affordance_zero_vetoes_any_relevance() -> None:
    """The invariant: p_afford=0 forces score 0 for even a maximally relevant action."""
    assert ta.affordance_gated_score(1.0, 0.0) == 0.0


@pytest.mark.parametrize("case", _DATA["invalid"], ids=lambda c: f"lm{c['p_lm']}af{c['p_afford']}")
def test_out_of_range_raises(case: dict) -> None:
    with pytest.raises(ValueError):
        ta.affordance_gated_score(case["p_lm"], case["p_afford"])


@pytest.mark.parametrize("case", _DATA["selection"], ids=lambda c: c["winner"] or "none")
def test_select_action_picks_expected(case: dict) -> None:
    actions = [ta.Action(**a) for a in case["actions"]]
    chosen = ta.select_action(actions)
    if case["winner"] == "":
        assert chosen is None
    else:
        assert chosen is not None and chosen.id == case["winner"]
