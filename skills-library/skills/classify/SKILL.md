---
name: classify
description: The gate in the self-healing chain. Decides whether a diagnosed failure may proceed to an automated fix, by asking two questions — is this a known pattern in incident memory, and how wide is the blast radius. Known and low-radius may proceed; novel or high-radius stops and reports with the diagnosis attached. Also holds the chain's circuit breaker. Use after `diagnose`, before any repair is designed.
---

# classify

**This is the gate. Its default answer is stop.**

Two questions decide it, and both must pass. Either one failing halts the chain and produces a report instead of a repair.

## Phase 0 — Circuit breaker, checked first

Before classifying anything, count remediations completed in the trailing window.

**If remediations in the last 24 hours ≥ 3, the chain halts entirely.** Not this failure — the whole loop. Write the breaker trip to `incident-memory`, notify the founder, and stop.

A system repairing itself repeatedly is not healthy, it is failing repeatedly and hiding it behind successful repairs. The breaker exists to make that visible rather than smooth.

The breaker is reset by a human, never by the chain.

## Phase 1 — Known or novel

Query `incident-memory` for the diagnosed cause.

**Known** requires all of:
- [ ] A prior entry with the **same cause**, not merely the same symptom
- [ ] That entry's fix was **verified green**, not merely applied
- [ ] Its adversarial review **passed**

Same symptom with a different cause is **novel**. This is the most common misclassification and the most expensive: it produces a confident fix aimed at last month's problem.

**Novel** if the diagnosis is unproven. An unproven cause cannot match a known pattern, because you do not yet know what it is.

## Phase 2 — Blast radius, assessed explicitly

Answer both in writing. Not "low" — the actual answer.

**What else changes if this fix runs?**
Files, callers, shared modules, schema, config, env, scheduled jobs, other repos.

**What could that trigger?**
Downstream consumers, data migrations, cache invalidation, permission changes, anything that fires on deploy.

**High blast radius** if any of:
- Touches a production host, branch, or database on the fence's list
- Spends money or provisions a paid resource
- Changes a schema, a migration, or a permission
- Alters shared code with more than one caller outside its own module
- Modifies CI, deploy config, or a scheduled workflow
- Changes anything on the fence's self-modification list

**Low blast radius** requires: single module, no callers outside it, no schema, no config, no production surface, fully reversible by `git revert`.

Unsure is **high**. The word "just" appearing in your own reasoning ("it just changes one line") is a signal to re-check, not to proceed.

## Decision

| Known | Blast radius | Outcome |
|---|---|---|
| Yes | Low | **Proceed** to `propose-fix` |
| Yes | High | **Stop.** Report with diagnosis attached |
| No | Low | **Stop.** Report with diagnosis attached |
| No | High | **Stop.** Report with diagnosis attached |

Three of four outcomes are stop. That is correct and deliberate.

## Completion

- [ ] Breaker checked and not tripped
- [ ] Known/novel decided, with the matching entry cited or its absence stated
- [ ] Both blast-radius questions answered in writing
- [ ] Decision recorded with its reason
- [ ] If stopped: the report carries the full diagnosis, not a summary of it

## Stop conditions

**Stopping is the normal outcome, not a failure of the chain.** A stop with an attached diagnosis is more valuable than an automated fix, because a human reads a diagnosis in a minute and reviews a diff in twenty.

Never widen "known" to make a fix eligible. If you find yourself arguing that a different cause is close enough, the answer is novel.

## Next

`propose-fix` if proceeding. Otherwise `incident-memory`, then report and stop.
