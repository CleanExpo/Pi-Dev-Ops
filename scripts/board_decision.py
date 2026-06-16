#!/usr/bin/env python3
"""board_decision.py — the decision mathematics for the Senior PM / Board.

Two honest jobs:

1) Show WHY long autonomous chains fail (and why "40%" happens), and show the
   ONE lever that fixes it — verification + bounded retry — with real numbers.
   No equation raises the base model's raw capability; this raises the SYSTEM's
   reliability by catching failures instead of shipping them.

2) Choose the next move the way a Board should: maximise expected value toward
   the finish line, but HARD-GATE anything irreversible/high-blast to a human,
   regardless of how attractive the expected value looks.

Run:  python scripts/board_decision.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — the reliability mathematics (why 40%, and the real path to ~98%)
# ─────────────────────────────────────────────────────────────────────────────

def end_to_end(p_step: float, n_steps: int) -> float:
    """Success of a chain of n independent steps each succeeding w.p. p_step.
    This is p**n — the compounding that destroys long autonomous runs."""
    return p_step ** n_steps


def step_with_retry(p_step: float, retries: int) -> float:
    """Effective success of one step given a TRUE verifier + bounded retries.
    A failure is caught and retried; the step only fails if every attempt fails.
    = 1 - (1 - p)**(attempts).  Requires a real check — without it you cannot
    know to retry, and compounding works against you instead."""
    return 1.0 - (1.0 - p_step) ** (retries + 1)


def combined_catch(catch_rates: list[float]) -> float:
    """Two INDEPENDENT verifiers (e.g. tests + a clean-context reviewer).
    Combined miss = product of individual misses, so catch rises fast."""
    miss = 1.0
    for c in catch_rates:
        miss *= (1.0 - c)
    return 1.0 - miss


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Calibration metric. predictions = stated P(success); outcomes = 0/1.
    Lower is better (0 = perfect). If this is high, the model's confidence is
    NOT trustworthy and every EV below is garbage-in. Calibrate before you act."""
    if not predictions:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — choosing the next move (expected value under a safety constraint)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Move:
    name: str
    p_success: float       # CALIBRATED probability of success (0..1), not a vibe
    value: float           # value toward the finish line if it succeeds
    cost_if_fail: float    # cost/cleanup if it fails
    reversible: bool       # can it be undone with no real-world harm?
    irreversible_kind: str = ""   # e.g. "deploy", "payment", "delete", "email"


# thresholds — tune from your own calibration data, not guesses
THETA_ACT = 0.85     # auto-proceed only when calibrated success >= this
THETA_VERIFY = 0.55  # between this and THETA_ACT: gather evidence first


def expected_value(m: Move) -> float:
    return m.p_success * m.value - (1.0 - m.p_success) * m.cost_if_fail


def decide(m: Move) -> tuple[str, str]:
    """Return (action, why). The human gate is a HARD constraint that overrides
    expected value — this is the line autonomy does not cross."""
    if not m.reversible:
        return ("ESCALATE_TO_HUMAN",
                f"irreversible ({m.irreversible_kind or 'high blast radius'}) — "
                f"gated regardless of EV")
    ev = expected_value(m)
    if ev <= 0:
        return ("DROP / REPLAN", f"expected value {ev:+.1f} ≤ 0 — not worth it")
    if m.p_success >= THETA_ACT:
        return ("PROCEED (auto)", f"EV {ev:+.1f}, calibrated p={m.p_success:.0%} ≥ {THETA_ACT:.0%}")
    if m.p_success >= THETA_VERIFY:
        return ("VERIFY FIRST", f"EV {ev:+.1f} but p={m.p_success:.0%} — run a check to raise confidence before acting")
    return ("ESCALATE_TO_HUMAN", f"EV {ev:+.1f} but p={m.p_success:.0%} too low to act alone")


# ─────────────────────────────────────────────────────────────────────────────
# Demonstration with real numbers
# ─────────────────────────────────────────────────────────────────────────────

def _demo() -> None:
    print("=" * 70)
    print("PART 1 — why you're at ~40%, and the real path to ~98%")
    print("=" * 70)
    p, n = 0.90, 15
    raw = end_to_end(p, n)
    print(f"A 15-step build, each step {p:.0%} reliable, NO verification:")
    print(f"   end-to-end success = {p}^{n} = {raw:.1%}   <- this is your '40%' (worse, even)")
    eff = step_with_retry(p, retries=2)
    gated = end_to_end(eff, n)
    print(f"\nSame steps, but each wrapped in a TRUE check + up to 2 retries:")
    print(f"   effective per-step = 1-(1-{p})^3 = {eff:.3f}")
    print(f"   end-to-end success = {eff:.3f}^{n} = {gated:.1%}   <- THIS is your 98%")
    print(f"\nThe jump from {raw:.0%} to {gated:.0%} came from verification + retry,")
    print("NOT a smarter model. Without a real check you can't retry, and the")
    print(f"{raw:.0%} stands. The gauge is the multiplier.")
    two = combined_catch([0.80, 0.80])
    print(f"\nTwo independent checks (tests + clean-context reviewer), 80% catch each:")
    print(f"   combined catch = 1-(0.2*0.2) = {two:.0%}  (why a second reviewer pays off)")

    print("\n" + "=" * 70)
    print("PART 2 — Board choosing the next move (EV, with a hard human gate)")
    print("=" * 70)
    moves = [
        Move("Add API contract tests for RestoreAssist auth", 0.92, value=8, cost_if_fail=1, reversible=True),
        Move("Wire password-reset backend flow", 0.70, value=9, cost_if_fail=3, reversible=True),
        Move("Refactor whole payment module blind", 0.40, value=10, cost_if_fail=9, reversible=True),
        Move("Deploy to production", 0.95, value=10, cost_if_fail=8, reversible=False, irreversible_kind="deploy"),
        Move("Charge pilot customers", 0.95, value=10, cost_if_fail=10, reversible=False, irreversible_kind="payment"),
    ]
    for m in moves:
        action, why = decide(m)
        print(f"\n• {m.name}")
        print(f"    p={m.p_success:.0%} value={m.value} cost_if_fail={m.cost_if_fail} reversible={m.reversible}")
        print(f"    → {action}  — {why}")
    print("\nNote: 'Deploy' and 'Charge customers' are auto-gated to you even at 95%")
    print("success — irreversibility overrides expected value. That's the safety line.")


if __name__ == "__main__":
    _demo()
