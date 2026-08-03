---
name: prove-the-failure
description: Build a tight, red-capable feedback loop that drives the actual failure path and asserts the exact symptom, before any hypothesis is formed. One command, already run once, deterministic, fast, agent-runnable. Use at the start of any self-healing chain, or whenever something is broken/failing/slow and you are tempted to read the code and guess. First link in the self-healing chain; hands off to `contain`.
---

# prove-the-failure

**This is the core skill. Everything downstream follows mechanically.** With a tight pass/fail signal targeting *this specific failure*, the cause becomes findable. Without one, code inspection is guessing with extra steps.

Adapted from `diagnosing-bugs` Phase 1 (mattpocock/skills). The discipline is his; the gate is ours.

Invest heavily here. Be aggressive. Refuse to give up early.

## Phase 1 — Construct the loop

Try roughly in this order. Stop at the first that goes red.

1. **Failing test** at the right seam (unit, integration, e2e).
2. **Replay the real artifact** — the failing CI log, webhook payload, or event that proves the failure already happened.
3. **CLI invocation** with fixture input, diffing output against known-good.
4. **HTTP script** against a running dev server.
5. **Headless browser script** — drives UI, asserts DOM/console/network.
6. **Throwaway harness** — minimal subset of the system, dependencies mocked.
7. **Differential loop** — same input through old vs new, diff the outputs.
8. **Bisection harness** — automate the state check, hand it to `git bisect run`.

For a failure that has already occurred in production or CI, strategy 2 is usually fastest and is always the most honest: the artifact is evidence, not a simulation.

## Phase 2 — Tighten it

Treat the loop as a product.

- **Faster?** Cache setup, skip unrelated init, narrow scope.
- **Clearer signal?** Assert the exact symptom, not "didn't crash".
- **Deterministic?** Pin time, seed RNG, isolate filesystem, freeze network.

A 30-second flaky loop barely helps. A 2-second deterministic loop is a superpower.

**Non-deterministic failures:** target a higher reproduction rate, not a clean repro. Loop the trigger 100×, parallelise, narrow the timing window. A 50% failure is debuggable; 1% is not.

## Completion — tight, red-capable loop

Succeeds when you have **one command** that you have **already run at least once**, and you paste both the invocation and its output.

- [ ] **Red-capable** — drives the actual failure path and asserts the specific symptom
- [ ] **Deterministic** — same result across runs (or a pinned high rate)
- [ ] **Fast** — seconds, not minutes
- [ ] **Agent-runnable** — no human in the loop
- [ ] **Pasted** — invocation and output are in the record, not described

## Stop conditions

**If a hypothesis is formed before this command exists, stop.** That is the failure this skill prevents. No red-capable command means no `diagnose`.

**If you cannot build a loop,** stop and state exactly what you tried. Request one of: access to a reproducing environment, captured artifacts (CI log, HAR, payload, core dump), or permission for temporary instrumentation. Do not hypothesise without a loop. "I could not build a loop" is a valid, logged outcome — it goes to `incident-memory` like any other.

## Gates

Building a loop is read-and-local work and needs no approval. But a loop that reaches a production host, spends credits, or writes to a production database **is itself a gated action** — reproduce against a preview branch, a fixture, or the captured artifact instead. If the only possible loop touches production, stop and report that; do not build it.

## Next

`contain` — reach a safe state before diagnosing.
