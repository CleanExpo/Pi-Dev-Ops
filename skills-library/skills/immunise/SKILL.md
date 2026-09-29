---
name: immunise
description: Add the check, test, or workflow guard that stops this failure recurring. May propose a fence change; may never apply one. Use after `verify` passes and its cooldown has elapsed.
---

# immunise

**A fix repairs this instance. An immunisation makes the class impossible.** Without this step the chain is a treadmill: the same failure returns, gets diagnosed again, and the cost is paid every time.

Ask one question: **what would have caught this before it shipped?**

## Phase 1 — Choose the cheapest guard that would have caught it

In ascending order of cost. Take the first that would actually have fired.

1. **A test** — the regression test from `propose-fix` may already be sufficient. If so, say so and stop; that is a complete immunisation.
2. **A lint or type rule** — catches the class at author time.
3. **A CI check** — catches it before merge.
4. **A workflow guard** — a required check, a branch protection rule, a job precondition.
5. **A fence predicate** — catches it at execution, for the class the fence exists to stop.

Test the guard against the failure. **A guard that would not have fired is not an immunisation**, however sensible it looks. Prove it: apply the guard to the pre-fix state and watch it catch the failure.

## Phase 2 — The fence carve-out

**`immunise` may propose a fence change. It may never apply one.**

Fence rule files — `fence.json`, the classifier, the hook registration, `denials.jsonl`, `HARD_STOP`, and the constitution corpus — are on the self-modification list. Touching them **freezes the agent on the first attempt**, not the second. There is no bounded-retry allowance here and no "the fix requires it" exception.

This is not friction to be worked around. A self-healing chain that can widen its own fence is not fenced — it is a system that repairs its way out of its constraints, one justified step at a time. The whole point of the chain is that it stops at the same two gates as everything else.

So the output for a fence-class immunisation is **a proposed diff to `fence.json`, in the report, unapplied.** A human applies it. Say plainly that this is the recommendation and why the chain cannot perform it.

## Completion

- [ ] Guard chosen, at the cheapest level that would have fired
- [ ] **Guard proven** — applied to the pre-fix state and observed catching the failure
- [ ] Guard applied, **or** proposed-and-unapplied if it touches the fence or a gated surface
- [ ] If the regression test was sufficient, that is stated rather than padded with a redundant second guard

## Stop conditions

**No fence application. Ever. First attempt is terminal.**

**A guard that touches CI, deploy config, or branch protection is a production surface** — propose it, do not apply it.

**If no guard would have caught this,** say so. That is an honest and important finding: it means the class is currently undetectable, which is architectural information worth more than a guard that gives false comfort.

## Next

`incident-memory` — write it down so `classify` can read it.
