---
name: design-pressure-test
description: Before writing code for a non-trivial feature or change, spawn an Opus subagent to pressure-test the proposed approach — challenge the design, surface alternatives, find architectural mistakes that would be expensive to undo. Use when the user asks for a non-trivial implementation and you've formed a plan but haven't started coding. Catches the wrong-architecture trap that opus-adversary can only spot after the work is done.
---

# Design pressure-test (pre-implementation review)

`opus-adversary` catches bugs in code you wrote. This skill catches mistakes in code you haven't written yet — when fixing them is free.

The cheapest bug is the one you don't write because Opus told you the design was wrong before you started.

## When to invoke

- You've sketched an implementation plan for a non-trivial feature (new module, new endpoint, schema change, integration, refactor of >100 lines)
- You're about to start writing code that will commit you to an architecture
- The change has *design* surface, not just *implementation* surface
- The user gave a vague brief and you've made assumptions about scope, shape, or contract

## When NOT to invoke

- Bug fixes with a known cause and a localised patch
- Trivial features (renames, copy changes, single-function additions)
- Following an existing pattern in the codebase exactly
- After you've already started writing code (use `opus-adversary` instead)
- When the user has explicitly approved a specific design — they don't want it re-litigated

## How to run it

Spawn an `Agent` call with `subagent_type: "Plan"` and `model: "opus"`. The Plan subagent type is purpose-built for design feedback.

Prompt template:

```
You are pressure-testing a design I'm about to implement. No code has been
written yet. Your job is to find what's wrong with the plan
before I commit to it. Be skeptical, not agreeable.

## Problem
<one paragraph: what the user actually needs>

## Proposed approach
<bullet list: the design you're about to implement>

## Constraints / context
<existing patterns to follow, related code, performance/scale needs>

## Your job
1. Find architectural mistakes — the kind that are expensive to undo once code exists
2. Identify scope I've gotten wrong (over-engineered or under-scoped)
3. Surface a meaningfully different approach if one exists, with a sentence on the tradeoff
4. Flag any contract / API / schema decision I'd regret in 6 months
5. Call out missing requirements I should clarify with the user before starting
6. Identify hidden coupling: what does this design assume about other parts of the system that may not hold?

For each concern, cite a file/symbol if relevant. End with a verdict:
PROCEED / PROCEED WITH CHANGES / RECONSIDER + one sentence why.
Be terse. No preamble.
```

## Handling the output

- **PROCEED** — start coding.
- **PROCEED WITH CHANGES** — incorporate the changes into your plan, then code.
- **RECONSIDER** — stop. Either redesign, or surface the disagreement to the user with both options and let them decide. Do not silently override Opus and proceed; the user should know there was friction.

If the verdict surfaces missing requirements (item 5), **ask the user before continuing**. That's the highest-value output of this skill — catching ambiguity before code locks it in.

## When to combine with adversarial-review

For high-stakes designs (auth flows, payment flows, migrations, data-handling architecture):
1. Run `design-pressure-test` first (Opus, free)
2. If Opus says PROCEED or PROCEED WITH CHANGES, then optionally run `/codex:adversarial-review --background` on the eventual diff before merging

Do **not** run Codex on raw plans — it's wired for code review, not design review, and Plus quota is too tight.

## Lifecycle coverage

Pair with the other skills for full coverage:
- `design-pressure-test` → before code is written
- `opus-adversary` → after code is written, before push
- `adversarial-review` → high-stakes only, before merge
- `parallel-delegate` → when implementing — split independent work concurrently
