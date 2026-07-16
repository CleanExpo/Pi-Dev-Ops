"""app/server/tao_tournament.py — RA-7022: tournament ranking of candidates (Co-Scientist).

Encodes the Co-Scientist mechanism: rank candidate proposals by pairwise "which
is better" judgements, rather than a single noisy scalar per candidate. Pairwise
comparison surfaces high-confidence candidates more reliably where single-shot
scoring is noisy.

Two rankers are provided:

* ``rank_candidates`` — sequential **Elo**. Deterministic for a *fixed* replay
  order, but the leaderboard is **order-sensitive**: the same set of pairwise
  results replayed in a different order can rank candidates differently. Keep it
  only where the replay order is itself meaningful and fixed.

    E_a  = 1 / (1 + 10^((R_b − R_a)/400))          # expected score of a vs b
    R_a' = R_a + K·(S_a − E_a)                       # update after a result

* ``rank_candidates_bt`` — batch **Bradley-Terry** MLE. Fits each candidate's
  strength from the win/loss COUNTS only, so it is **order-invariant** — any
  permutation of the same results yields an identical ranking. This is the
  order-invariant default for an authoritative board/council ranking (RA-7024).

    P(i beats j) = p_i / (p_i + p_j)

The LLM only supplies the pairwise verdicts upstream; the ranking itself is pure
arithmetic and reproducible.

Public API: ``expected_score``, ``update_ratings``, ``rank_candidates``,
``rank_candidates_bt``.
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

    Deterministic for a fixed input order, but ORDER-SENSITIVE: a different
    ordering of the same results can produce a different leaderboard. Prefer
    ``rank_candidates_bt`` where the ranking must be order-invariant.

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


def rank_candidates_bt(
    candidates: Sequence[str],
    results: Iterable[tuple[str, str]],
    *,
    prior: float = 1.0,
    tol: float = 1e-12,
    max_iter: int = 10_000,
) -> list[tuple[str, float]]:
    """Rank candidates by a batch Bradley-Terry MLE — ORDER-INVARIANT (RA-7024).

    Fits each candidate's strength from the pairwise win/loss COUNTS only, so any
    permutation of ``results`` yields an identical ranking (unlike the sequential
    Elo ``rank_candidates``). Model: ``P(i beats j) = p_i / (p_i + p_j)``;
    strengths are fit by the standard minorization-maximization (MM) iteration
    (Hunter, 2004).

    A symmetric ``prior`` (``prior`` virtual wins and ``prior`` virtual losses for
    every candidate against a phantom opponent pinned at strength 1.0)
    regularizes disconnected or degenerate comparison graphs, so the estimate is
    unique and finite even when a candidate has zero wins or zero losses, and it
    anchors the otherwise-unidentifiable overall scale.

    Returns [(candidate_id, strength), ...] sorted by strength descending, then
    candidate id ascending for a stable order on ties. Raises ValueError if a
    result references an unknown candidate.
    """
    ids = list(candidates)
    index = {c: i for i, c in enumerate(ids)}
    n = len(ids)
    if n == 0:
        return []

    wins = [0.0] * n                        # total wins per candidate
    games = [[0.0] * n for _ in range(n)]   # games[i][j] = games played between i and j
    for winner, loser in results:
        if winner not in index or loser not in index:
            raise ValueError(f"result ({winner!r}, {loser!r}) references unknown candidate")
        wi, li = index[winner], index[loser]
        wins[wi] += 1.0
        games[wi][li] += 1.0
        games[li][wi] += 1.0

    # MM iteration. Every candidate also plays `prior` wins + `prior` losses
    # against a phantom opponent held at strength 1.0 — this both regularizes
    # degenerate records and pins the scale, so no separate normalization is
    # needed and the fixed point is unique.
    strengths = [1.0] * n
    for _ in range(max_iter):
        updated = [0.0] * n
        for i in range(n):
            numerator = wins[i] + prior
            denominator = (2.0 * prior) / (strengths[i] + 1.0)  # phantom: 2*prior games at strength 1
            for j in range(n):
                if i != j and games[i][j]:
                    denominator += games[i][j] / (strengths[i] + strengths[j])
            updated[i] = numerator / denominator if denominator > 0.0 else strengths[i]
        delta = max(abs(updated[i] - strengths[i]) for i in range(n))
        strengths = updated
        if delta < tol:
            break

    return sorted(
        ((ids[i], strengths[i]) for i in range(n)),
        key=lambda kv: (-kv[1], kv[0]),
    )


__all__ = [
    "DEFAULT_K",
    "DEFAULT_RATING",
    "expected_score",
    "rank_candidates",
    "rank_candidates_bt",
    "update_ratings",
]
