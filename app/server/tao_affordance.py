"""app/server/tao_affordance.py — RA-7021: affordance-gated action selection (PaLM-SayCan).

Encodes the SayCan "say × can" rule as a deterministic action-scoring primitive
for the autonomy ladder:

    score(a) = p_lm(a｜goal) · p_afford(a｜state)
    a*       = argmax_a score(a)

`p_lm` is the model's goal-relevance ("say"); `p_afford` is the affordance —
here the role-based decision-rights + operational-state check ("can"), which is
0.0 when the action is out of tier or the kill-switch/unsafe state blocks it.
Where SayCan *learns* affordances from robot data, we *encode* them.

Load-bearing invariant: `p_afford == 0.0` HARD-BLOCKS the action — the product is
0.0 regardless of how relevant the model thinks it is, so an out-of-tier or
unsafe action can never be selected over any feasible one. The multiplicative
form (not additive) is what makes "can" a veto rather than a discount.

Public API: `affordance_gated_score`, `Action`, `select_action`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


def affordance_gated_score(p_lm: float, p_afford: float) -> float:
    """SayCan combined score = p_lm · p_afford.

    Both inputs are probabilities in [0, 1]. Returns 0.0 whenever p_afford is 0.0
    (the "can" veto), regardless of p_lm. Raises ValueError if either input is
    outside [0, 1], since an out-of-range factor would break the veto guarantee.
    """
    if not 0.0 <= p_lm <= 1.0:
        raise ValueError(f"p_lm must be in [0, 1], got {p_lm!r}")
    if not 0.0 <= p_afford <= 1.0:
        raise ValueError(f"p_afford must be in [0, 1], got {p_afford!r}")
    return p_lm * p_afford


@dataclass(frozen=True)
class Action:
    """A candidate action with a language ("say") and affordance ("can") score."""

    id: str
    p_lm: float
    p_afford: float


def select_action(actions: Sequence[Action]) -> Action | None:
    """Select the highest combined-score action; None if none is feasible.

    An action is feasible only when its combined score is strictly positive (both
    factors non-zero). If every action is blocked (p_afford == 0) or the sequence
    is empty, returns None — the ladder must escalate rather than fire a blocked
    action. Ties resolve to the first action for stable selection.
    """
    feasible = [a for a in actions if affordance_gated_score(a.p_lm, a.p_afford) > 0.0]
    if not feasible:
        return None
    return max(feasible, key=lambda a: affordance_gated_score(a.p_lm, a.p_afford))


__all__ = ["Action", "affordance_gated_score", "select_action"]
