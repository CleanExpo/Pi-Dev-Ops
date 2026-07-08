"""app/server/tao_sample_filter.py — RA-7023: sample-and-filter synthesis (AlphaCode).

Encodes the AlphaCode discipline for hard generator tasks:

    shortlist = top_k( rerank( cluster( sample_N(model) ) ) )

Generate N candidates upstream, then deterministically: cluster near-duplicates
(by a canonical signature the caller supplies), keep each cluster's best-scoring
representative, rerank representatives by score, and hand only the top-k shortlist
to the judge. Sampling wide + filtering deterministically is how AlphaCode reached
competition-grade reliability without judging every raw sample.

This module owns the deterministic middle (cluster → rerank → top_k); sampling and
scoring are upstream. Pure functions, reproducible.

Public API: `Candidate`, `cluster`, `shortlist`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Candidate:
    """A sampled candidate: `signature` groups near-duplicates; `score` ranks."""

    id: str
    signature: str
    score: float


def cluster(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Collapse each signature-group to its highest-scoring representative.

    Preserves first-seen order of the surviving representatives so the result is
    deterministic. Ties within a cluster keep the first-seen candidate.
    """
    best: dict[str, Candidate] = {}
    order: list[str] = []
    for c in candidates:
        cur = best.get(c.signature)
        if cur is None:
            best[c.signature] = c
            order.append(c.signature)
        elif c.score > cur.score:
            best[c.signature] = c
    return [best[sig] for sig in order]


def shortlist(candidates: Sequence[Candidate], k: int) -> list[Candidate]:
    """Return the top-k cluster representatives by score.

    `shortlist = top_k(rerank(cluster(candidates)))`. Rerank is by score
    descending, then id ascending for a stable order on ties. Raises ValueError
    if k < 1. If fewer than k distinct clusters exist, returns all of them.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    reps = cluster(candidates)
    reps.sort(key=lambda c: (-c.score, c.id))
    return reps[:k]


__all__ = ["Candidate", "cluster", "shortlist"]
