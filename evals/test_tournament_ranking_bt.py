"""Order-invariance gate (RA-7024) — batch Bradley-Terry ranking.

`rank_candidates_bt` fits Bradley-Terry strengths from pairwise win/loss COUNTS,
so any permutation of the same results yields an identical ranking — unlike the
sequential-Elo `rank_candidates`, whose leaderboard depends on replay order.
This is the repeatability fix for RA-7022 (see RA-7024).
"""
from __future__ import annotations

import random

import pytest

from app.server import tao_tournament as tt


def _order(results, candidates=("a", "b", "c", "d")):
    return [cid for cid, _ in tt.rank_candidates_bt(list(candidates), results)]


def test_bt_ranking_is_order_invariant() -> None:
    base = [
        ("a", "b"), ("a", "c"), ("a", "d"),
        ("b", "c"), ("b", "d"), ("c", "d"),
        ("a", "b"), ("b", "c"),  # repeated head-to-heads
    ]
    expected = _order(base)
    rng = random.Random(0)
    for _ in range(50):
        shuffled = base[:]
        rng.shuffle(shuffled)
        assert _order(shuffled) == expected, "BT ranking must not depend on results order"


def test_bt_recovers_transitive_order() -> None:
    # a beats everyone, b beats c and d, c beats d -> strict a > b > c > d
    results = [("a", "b"), ("a", "c"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]
    assert _order(results) == ["a", "b", "c", "d"]


def test_bt_symmetric_records_tie_break_by_id() -> None:
    # every pair splits 1-1 -> equal strengths -> deterministic tie-break by id,
    # regardless of the order candidates are supplied in.
    results = [
        ("a", "b"), ("b", "a"),
        ("a", "c"), ("c", "a"),
        ("b", "c"), ("c", "b"),
    ]
    assert _order(results, candidates=("c", "b", "a")) == ["a", "b", "c"]


def test_bt_unknown_candidate_raises() -> None:
    with pytest.raises(ValueError):
        tt.rank_candidates_bt(["a", "b"], [("a", "z")])
