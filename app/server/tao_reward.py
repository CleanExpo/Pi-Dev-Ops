"""app/server/tao_reward.py — RA-7020: correctness-first candidate reward (AlphaDev).

Encodes the AlphaDev reward discipline into a deterministic, code-checkable
primitive for ranking generator candidates:

    R(candidate) = 𝟙[correct] · (alpha − beta·cost)

Correctness is a hard gate; among correct candidates, lower cost (latency /
tokens / $, normalized to [0,1]) scores higher. This complements `tao_judge`'s
single LLM scalar with a deterministic tie-break — no model call.

Correctness-first invariant (the load-bearing constraint, RA-7020 judge catch):
a correct candidate must ALWAYS outrank an incorrect one. The naive scalar
breaks this when `alpha − beta·cost` goes negative (a correct-but-expensive
candidate would score below an incorrect one at 0). Two guards enforce the
invariant:

  1. `correctness_first_reward` requires `0 <= cost <= 1` and `alpha > beta`, so
     the correct branch is strictly positive (∈ [alpha−beta, alpha]) and the
     incorrect branch is exactly 0.0.
  2. `select_best` sorts lexicographically on `(correct, −cost)`, so selection is
     robust even if a caller passes an un-normalized cost to the scalar.

Public API: `correctness_first_reward`, `Candidate`, `select_best`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

DEFAULT_ALPHA: float = 1.0
DEFAULT_BETA: float = 0.5


def correctness_first_reward(
    correct: bool,
    cost: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> float:
    """AlphaDev correctness-first reward.

    Returns 0.0 for an incorrect candidate regardless of cost; for a correct
    candidate returns `alpha − beta·cost`, which is strictly positive given the
    invariant guards below.

    Raises ValueError if `cost` is outside [0, 1] or `alpha <= beta`, because
    either violation would let an incorrect candidate (0.0) outrank a correct one.
    """
    if not 0.0 <= cost <= 1.0:
        raise ValueError(f"cost must be normalized to [0, 1], got {cost!r}")
    if alpha <= beta:
        raise ValueError(
            f"alpha ({alpha!r}) must exceed beta ({beta!r}) so the correct "
            "branch stays strictly positive (correctness-first invariant)"
        )
    if not correct:
        return 0.0
    return alpha - beta * cost


@dataclass(frozen=True)
class Candidate:
    """A generator candidate with a correctness verdict and a normalized cost."""

    id: str
    correct: bool
    cost: float


def select_best(candidates: Sequence[Candidate]) -> Candidate | None:
    """Select the best candidate: correct first, then lowest cost.

    Lexicographic on `(correct, −cost)` so a correct candidate always outranks an
    incorrect one and, among equals, lower cost wins. Ties (same correctness and
    cost) resolve to the first candidate, keeping selection stable. Returns None
    for an empty sequence.
    """
    if not candidates:
        return None
    return max(candidates, key=lambda c: (c.correct, -c.cost))


__all__ = [
    "DEFAULT_ALPHA",
    "DEFAULT_BETA",
    "Candidate",
    "correctness_first_reward",
    "select_best",
]
