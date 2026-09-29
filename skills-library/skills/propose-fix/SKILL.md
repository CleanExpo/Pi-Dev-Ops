---
name: propose-fix
description: Produce the repair as a diff plus a regression test, never applied directly. Bounded to three attempts, each materially different, then it stops and reports the diagnosis rather than the error. Use only after `classify` returns proceed.
---

# propose-fix

**The output is a proposal, not a change.** A diff and a test, both reviewable, neither applied. Application happens after `adversarial-review` passes and `verify` runs — not here.

## Phase 1 — Regression test first

Write the test before the fix, and only if a **correct seam** exists.

A correct seam exercises the real failure pattern as it occurs at the call site. A shallow seam that mocks past the bug produces false confidence and is worse than no test.

If no correct seam exists, that finding is itself the important output. Record it and propose the architectural change that would create one — do not fake a test against a seam that cannot fail.

1. Turn the minimised repro from `diagnose` into a failing test.
2. **Watch it fail.** Paste the output.
3. Confirm it fails for the diagnosed reason, not an adjacent one.

## Phase 2 — Smallest sufficient diff

The fix addresses the **proven cause**, not the symptom and not the surrounding code you would like to improve.

- No refactoring alongside the fix. Two changes in one diff cannot be reviewed or reverted independently.
- No opportunistic cleanup, however tempting.
- No new abstraction for a single call site.

Every changed line traces to the diagnosed cause. If a line does not, remove it.

## Phase 3 — Attempt bound

**Three attempts maximum.** Each must try a **materially different approach** — not the same idea with adjusted parameters.

| Attempt | Requirement |
|---|---|
| 1 | The direct fix at the diagnosed cause |
| 2 | A different mechanism or a different layer — must be describable as "instead of X, do Y" |
| 3 | Last, materially different again |

Retrying the same approach with a tweaked value is **not** a second attempt. If you cannot describe how attempt N differs in kind from N−1, you have not made one.

After three, **stop and report the diagnosis, not the error.** The diagnosis is the durable finding; the failed attempts are context. "Three approaches failed, here is the proven cause and why each failed" is a good outcome and is logged as such.

**Giving up is a valid, logged outcome.** It goes to `incident-memory` with the same weight as a success.

## The distinction from R3 — read this before retrying anything

These are different rules and conflating them breaks both.

| | Retrying a **denied** action | Retrying a **failed repair** |
|---|---|---|
| What happened | The fence refused it — money, production, or self-modification | A proposed fix did not work |
| Rule | **Terminal.** Never retry, never route around it. A second attempt freezes the agent. | **Permitted, bounded.** Up to three materially different attempts. |
| Why | A refusal is a decision. Persistence must not erode it. | A failure is information. Iteration is how it gets used. |
| Who clears it | Founder only, creating a new record | Nobody — the bound is self-enforcing |

The rules do not overlap. **A denied action was never attempted; a failed repair was attempted and did not work.** If a fence denial occurs during a repair attempt, that denial is terminal and the attempt bound does not license retrying it — stop and report.

## Completion

- [ ] Regression test written, **run, and observed failing** (output pasted)
- [ ] Diff produced, smallest sufficient, every line traced to the cause
- [ ] Nothing applied — this is a proposal
- [ ] Attempt number recorded, and how it differs in kind from the previous
- [ ] If bound exhausted: diagnosis reported, not the error

## Stop conditions

**Nothing is applied here.** If a step requires writing to the working tree beyond a scratch branch, stop.

**A fix that spends money or mutates production is proposed only.** It never proceeds automatically regardless of what `classify` returned.

## Next

`adversarial-review` — a different model, a fresh session, no access to this reasoning.
