---
name: verify
description: Run the loop from `prove-the-failure` and confirm red goes green, then hold a cooldown before any further action is permitted. Use after `adversarial-review` returns PASS, before `immunise`.
---

# verify

**Green is a measurement, not a belief.** The only evidence that counts is the same loop that proved the failure, run again, now passing — and passing *because of the fix*, not alongside it.

## Phase 1 — Prove the loop still catches the failure

Before trusting green, confirm the loop can still go red. Revert the fix, run the loop, watch it fail.

- [ ] Loop is red **without** the fix
- [ ] Loop is green **with** the fix
- [ ] No other change is present in the working tree

A loop that is green with and without the fix proves nothing. This is the positive control, and skipping it is how a fix that changed nothing gets marked verified.

## Phase 2 — Run the full check

- [ ] The original loop, unmodified, now passes
- [ ] The regression test passes
- [ ] The regression test still fails when the fix is reverted
- [ ] Existing tests around the change still pass
- [ ] No debug instrumentation remains

## Phase 3 — Cooldown

**No further action for the cooldown window.** Not `immunise`, not another repair, not a related cleanup.

Default: **30 minutes**, or one full cycle of the affected scheduled job, whichever is longer.

The cooldown exists because a fix that breaks something adjacent usually reveals it on the next scheduled run, not immediately. Chaining straight into the next action means the breakage lands inside the next repair and the two become indistinguishable.

During cooldown: watch. Do not act.

- [ ] Cooldown elapsed
- [ ] Affected job ran at least once, or its next run is confirmed scheduled
- [ ] No new failure appeared in the window

## Completion

- [ ] Red-without-fix demonstrated (output pasted)
- [ ] Green-with-fix demonstrated (output pasted)
- [ ] Regression test verified in both directions
- [ ] Cooldown observed and clean

Paste both outputs. A claim of green without its output is not a verification, and this chain treats it as an unverified claim regardless of how confident the wording is.

## Stop conditions

**If the loop is still red, the fix failed.** Return to `propose-fix`, consuming one attempt from its bound of three. Do not adjust the loop to make it pass — modifying the loop to accommodate the fix inverts the entire chain.

**If a new failure appears during cooldown,** stop. Do not repair it inside this chain. Start a new chain at `prove-the-failure`, and record the adjacency — two failures in one window is a circuit-breaker signal.

## Next

`immunise` — stop it recurring.
