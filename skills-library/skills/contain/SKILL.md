---
name: contain
description: Reach a safe state before diagnosing. Halt the affected job, revert to last known good, or stop the loop — containment, never a fix. Records what was contained and what was deliberately left alone. Use immediately after `prove-the-failure`, or any time a failure is actively recurring and the bleeding must stop first.
---

# contain

**Containment is not repair.** The goal is to stop the failure recurring while you still understand nothing about its cause. A fix applied here is a guess applied at the worst possible moment.

Resist the pull to fix. You have a red loop and no diagnosis. Anything that looks like a repair right now is a coincidence waiting to be mistaken for understanding.

## Phase 1 — Choose the smallest sufficient action

In ascending order of blast radius. Take the first that reaches safety.

1. **Do nothing** — the failure is not recurring and nothing is degrading. Record this as the containment decision. It is a real choice and often the right one.
2. **Stop the loop** — disable the schedule, pause the cron, unqueue the job.
3. **Halt the affected job** — cancel the in-flight run only.
4. **Revert to last known good** — roll back the deployment or the commit that introduced it.
5. **Isolate the surface** — take the affected route, feature flag, or integration out of the path.

**Prefer reversible containment over thorough containment.** Disabling a schedule is trivially undone. A revert is not.

## Phase 2 — Record the boundary

Write both halves. The second half is the one people skip and the one that matters later.

- **Contained:** what you stopped, how, and how to undo it
- **Deliberately left alone:** what you could have stopped and chose not to, with the reason

The "left alone" list is what a reviewer checks when the failure recurs somewhere adjacent. Without it, the next responder cannot tell the difference between a considered decision and an oversight.

## Completion

- [ ] The failure is no longer actively recurring, **or** "not recurring" is recorded as the finding
- [ ] The containment action is named, with its exact undo
- [ ] The deliberately-left-alone list is written, with reasons
- [ ] No repair was attempted

## Stop conditions

**Containment that spends money or mutates production stops for a human.** Reverting a production deploy, disabling a live integration, and rolling back a database are all gated — propose them, do not perform them. Disabling a schedule in a repo, cancelling a CI run, and stopping a local loop are inside the fence.

**If the only sufficient containment is a gated action,** stop and report: the symptom, the red loop, the proposed containment, and its undo. A human decides. Do not downgrade to a weaker containment just to stay inside the fence — say plainly that the safe action is gated.

## Next

`diagnose` — root cause, against the loop.
