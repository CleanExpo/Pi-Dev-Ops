"""Prove-It Gate (RA-7022) — golden regression eval for tournament ranking.

Deterministic assertions over tao_tournament.expected_score, update_ratings, and
rank_candidates (Co-Scientist Elo tournament). The LLM supplies pairwise verdicts
upstream; the ranking replayed here is pure arithmetic and reproducible. No LLM
judge in this test.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.server import tao_tournament as tt

_GOLDEN = Path(__file__).parent / "golden" / "tournament_ranking.yaml"
_DATA = yaml.safe_load(_GOLDEN.read_text())


@pytest.mark.parametrize("case", _DATA["expected"], ids=lambda c: f"{c['rating_a']}v{c['rating_b']}")
def test_expected_score(case: dict) -> None:
    got = tt.expected_score(case["rating_a"], case["rating_b"])
    assert got == pytest.approx(case["expected"])


@pytest.mark.parametrize("case", _DATA["update"], ids=lambda c: f"a_won={c['a_won']}")
def test_update_ratings(case: dict) -> None:
    new_a, new_b = tt.update_ratings(case["rating_a"], case["rating_b"], case["a_won"])
    assert new_a == pytest.approx(case["new_a"])
    assert new_b == pytest.approx(case["new_b"])


@pytest.mark.parametrize("case", _DATA["ranking"], ids=lambda c: "".join(c["order"]))
def test_rank_candidates(case: dict) -> None:
    results = [tuple(pair) for pair in case["results"]]
    ranked = tt.rank_candidates(case["candidates"], results)
    assert [cid for cid, _ in ranked] == case["order"]


@pytest.mark.parametrize("case", _DATA["invalid"], ids=lambda c: "unknown_candidate")
def test_unknown_candidate_raises(case: dict) -> None:
    results = [tuple(pair) for pair in case["results"]]
    with pytest.raises(ValueError):
        tt.rank_candidates(case["candidates"], results)
