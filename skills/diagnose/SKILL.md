---
name: diagnose
description: Find root cause by running the red loop from `prove-the-failure` and changing one variable at a time — never by reading the code and reasoning about it. Outputs a written cause with file and line evidence. Use after containment, before any repair is designed.
---

# diagnose

**Diagnose against the loop, not against a reading of the code.** A cause derived from reading is a hypothesis wearing a conclusion's clothes. A cause is proven when you can turn the loop red and green at will by changing the thing you claim is responsible.

## Phase 1 — Confirm the loop is measuring the right failure

Run it. Observe.

- [ ] It produces the reported failure mode, not a nearby different one
- [ ] It reproduces consistently, or at the pinned rate
- [ ] The exact symptom is captured — error text, wrong value, timing

If the loop is red for a different reason than the report, you have found a second failure. Stop and split them.

## Phase 2 — Minimise

Shrink to the smallest scenario still going red. Remove inputs, callers, config, data, and steps one at a time, rerunning after each cut. Keep only what is load-bearing.

Done when removing any remaining element turns the loop green.

## Phase 3 — Hypothesise, then rank

Generate 3–5 hypotheses **before testing any**. Each must be falsifiable and predict a direction:

> "If X is the cause, then changing Y turns the loop green, and changing Z makes it worse."

Rank them. Cheap-and-likely first.

## Phase 4 — Instrument, one variable at a time

Each probe tests exactly one ranked prediction.

1. **Debugger or REPL** where available — one breakpoint beats ten logs.
2. **Targeted logs** at the boundary that distinguishes two hypotheses.
3. Never "log everything and grep".

Tag every debug log uniquely (`[DEBUG-a4f2]`) so cleanup is one grep.

## Phase 5 — Prove it

The cause is proven when you can **turn the loop red and green on demand** by toggling the claimed cause, and no other change is required.

Correlation is not enough. If the loop goes green when you change two things, you have not finished.

## Completion — a written cause

- [ ] **Cause stated in one sentence**, in plain language
- [ ] **File and line evidence** — the exact location, quoted
- [ ] **Toggle demonstrated** — loop goes red and green by changing that thing alone
- [ ] **Rejected hypotheses listed**, each with what ruled it out
- [ ] **All debug instrumentation removed**

The rejected list matters. It is the cheapest thing to write now and the most expensive to reconstruct later, and `classify` uses it to judge novelty.

## Stop conditions

**No red loop, no diagnosis.** If `prove-the-failure` did not complete, go back. Do not proceed on a described failure.

**If the cause cannot be proven by toggle,** say so and report the strongest hypothesis as *unproven*, with what would prove it. An unproven cause is a valid outcome — it goes to `incident-memory` and it forces `classify` to treat the failure as novel.

## Next

`classify` — known or novel, and how wide the blast radius is.
