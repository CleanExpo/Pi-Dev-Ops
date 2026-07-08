"""app/server/tao_tournament.py — RA-7022: tournament ranking of candidates (Co-Scientist).

Encodes the Co-Scientist mechanism: rank candidate proposals by an Elo score
updated from pairwise "which is better" judgements, rather than a single noisy
scalar per candidate. Pairwise comparison surfaces high-confidence candidates
more reliably where single-shot scoring is noisy.

    E_a  = 1 / (1 + 10^((R_b − R_a)/400))          # expected score of a vs b
    R_a' = R_a + K·(S_a − E_a)                       # update after a result

`rank_candidates` replays a sequence of pairwise results (deterministic order)
and returns candidates sorted by final rating, high to low. Pure arithmetic —
the LLM only supplies the pairwise verdicts upstream; the ranking itself is
reproducible.

Public API: `expected_score`, `update_ratings`, `rank_candidates`.
"""
from __future__ import annotations

from typing import Iterable, Sequence

DEFAULT_RATING: float = 1000.0
DEFAULT_K: float = 32.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Elo expected score of A against B, in (0, 1)."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float,
    rating_b: float,
    a_won: bool,
    *,
    k: float = DEFAULT_K,
) -> tuple[float, float]:
    """Return (new_a, new_b) after one pairwise result. `a_won` = A beat B."""
    exp_a = expected_score(rating_a, rating_b)
    exp_b = 1.0 - exp_a
    s_a = 1.0 if a_won else 0.0
    s_b = 1.0 - s_a
    return rating_a + k * (s_a - exp_a), rating_b + k * (s_b - exp_b)


def rank_candidates(
    candidates: Sequence[str],
    results: Iterable[tuple[str, str]],
    *,
    k: float = DEFAULT_K,
    base_rating: float = DEFAULT_RATING,
) -> list[tuple[str, float]]:
    """Replay pairwise (winner, loser) results and rank candidates by final Elo.

    Returns [(candidate_id, rating), ...] sorted by rating descending, then by
    candidate id ascending for a stable, reproducible order on ties. Raises
    ValueError if a result references an unknown candidate.
    """
    ratings: dict[str, float] = {c: base_rating for c in candidates}
    for winner, loser in results:
        if winner not in ratings or loser not in ratings:
            raise ValueError(f"result ({winner!r}, {loser!r}) references unknown candidate")
        new_w, new_l = update_ratings(ratings[winner], ratings[loser], True, k=k)
        ratings[winner], ratings[loser] = new_w, new_l
    return sorted(ratings.items(), key=lambda kv: (-kv[1], kv[0]))


__all__ = ["DEFAULT_K", "DEFAULT_RATING", "expected_score", "rank_candidates", "update_ratings"]
