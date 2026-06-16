# The Decision Mathematics — getting honestly close to autonomous

**The equations the Senior PM / Board should run to choose the next move and reach ~98% — and the honest truth about what math can and can't do.**

Date: 2026-06-07 · Runnable proof: `scripts/board_decision.py`

---

## The one hard truth about "40% → 98%"

You can't multiply your way from a 40%-capable model to a 98%-autonomous system with a clever algorithm. The ~40% is the *model's raw ability* to complete a complex task correctly. No equation on top adds capability the base model doesn't have.

What math **can** do is make a system of unreliable steps behave reliably — by catching and retrying failures, and by choosing moves wisely. That genuinely reaches ~98%, but it is **98% verified-correct work with a human gate at the irreversible moments**, not 98% unsupervised completion of anything. That distinction is the whole game, and confusing the two is what's kept you in the circle.

---

## Equation 1 — why long autonomous runs fail (the compounding law)

A chain of `n` steps, each succeeding with probability `p`, succeeds end-to-end with probability `p^n`.

- 15 steps at 90% each → `0.9^15 = 20.6%`.

This is why "let it run the whole build unattended" collapses: even *good* per-step reliability compounds to near-zero over a real project. Your "40%" is this law. **Without a verifier, more steps = more failure, faster.**

## Equation 2 — the lever that actually reaches 98% (verification + retry)

Wrap each step in a *true* check and allow bounded retries. The step only fails if every attempt fails:

`effective_p = 1 − (1 − p)^(attempts)`

- 90% step, 2 retries → `1 − 0.1^3 = 0.999`.
- Now `0.999^15 = 98.5%`.

The jump from 21% to 98% came entirely from **verification + retry — not a smarter model.** This is the mathematical justification for everything we built: the gauge (`coverage_check`) is the multiplier. Critically, *you cannot retry what you can't detect* — without a real check, you don't know a step failed, so Equation 1 stands and you stay at 21%.

## Equation 3 — why a second, independent reviewer pays off

Two independent checks (e.g. tests + a clean-context reviewer) with catch rates `c1, c2` have combined miss `(1−c1)(1−c2)`:

- two checks at 80% catch → combined catch `1 − 0.2·0.2 = 96%`.

Independent verification stacks fast. One mediocre check plus one independent mediocre check beats one great check. (They must be *independent* — the same model reviewing itself does not count; the research is clear that self-review is biased.)

## Equation 4 — choosing the next move (expected value)

For each candidate move:

`EV = P(success)·Value − P(failure)·Cost`

Pick the move with the highest EV toward the finish line. Drop moves with `EV ≤ 0`. This is how the Board "predicts and selects the next move" — not magic, just expected value over your stated goals.

## Equation 5 — act, verify, or escalate (thresholds + the hard gate)

EV alone is not enough — a high-EV move you can't undo is still dangerous. So:

1. **Hard constraint first:** if a move is *irreversible* (deploy, payment, delete, send, publish) → **escalate to human, regardless of EV.** This overrides everything. It's the safety line.
2. Otherwise, by calibrated success probability `p`:
   - `p ≥ 0.85` → proceed automatically
   - `0.55 ≤ p < 0.85` → verify first (run a check to raise confidence), then proceed
   - `p < 0.55` → escalate or research

(Thresholds are tunable from your own data.) `board_decision.py` runs exactly this — and in the demo, "Deploy" and "Charge customers" get gated to you even at 95% success, because irreversibility beats EV.

## Equation 6 — calibration (the prerequisite everyone skips)

Every probability above is worthless if the model's confidence is miscalibrated. Measure it with the Brier score over logged predictions vs. outcomes:

`Brier = mean((p_predicted − outcome)²)` — lower is better; 0 is perfect.

If the Brier score is high, the system's "I'm 90% sure" is a lie, and every EV is garbage-in. **Calibrate first** (log predictions, compare to reality), then trust the thresholds. This is also the mathematical definition of "stop giving me false positives": a calibrated system *knows when it's probably wrong* and escalates instead of claiming done.

## Equation 7 — the completeness metric (redefining "98%")

Define project completeness as a scalar:

`C = verified_requirements / total_requirements`

where "verified" means an *executable probe passed* (what `coverage_check` computes), and UNKNOWNs are excluded from the numerator. The loop's objective is to drive `C → 1.0`. Your "98%" target should be **`C = 0.98` verified coverage**, with the last step a human go/no-go — a real, measurable finish line, not a feeling.

---

## What's real vs. overkill (so you don't chase the wrong math)

- **Real, high-value, implement now:** Equations 1–7. They're cheap, robust, and directly attack false positives and bad sequencing. `board_decision.py` already runs the core.
- **Overkill / avoid:** heavy reinforcement-learning planners, Monte-Carlo Tree Search (LATS), Graph-of-Thoughts. The research is explicit — they're expensive, fragile, and production-prohibitive, and their gains are mostly relative to each other, not to simple EV + verification. Don't let anyone sell you "we need MCTS to predict the next move." You don't.

---

## Your role, stated mathematically

You said you thought you were "just providing the pathway." You're right, and the math makes the division clean and honest:

- **You supply:** the *Value* and the *finish line* (`C`'s definition — what "done" means per project; you said these are already implied in your projects), and the *go/no-go* on the hard-gated irreversible moves.
- **The math supplies:** the *sequencing* (Equation 4, highest-EV next move), the *act/verify/escalate* decision (Equation 5), and the *honest stop* (Equations 2, 6 — verify, retry, and escalate when uncertain).

That is the system following your pathway without getting off task: it maximises expected value toward *your* finish line, subject to *your* safety gate, and tells you the truth (calibrated) at every step. You stop being the bottleneck not by understanding the code, but because the system stops needing you to catch its lies — the math catches them.

---

## The one line

The path from 40% to 98% is not a smarter model or a fancier algorithm. It is: **verify every step (Eq 2), review independently (Eq 3), pick moves by expected value (Eq 4) under a hard human gate for irreversible actions (Eq 5), on calibrated probabilities (Eq 6), driving measured coverage to 0.98 (Eq 7).** Every piece is cheap, runnable today, and already started. The multiplier was never the model — it's the gauge.
