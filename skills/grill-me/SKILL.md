---
name: grill-me
description: Run a relentless one-question-at-a-time interview on a sketch or plan until every branch of the decision tree resolves into either a decision, a rabbit hole, or an explicit no-go. Use when the user wants to stress-test a fat-marker sketch before any code is written, or asks to be "grilled", "interviewed", or to "stress-test" a plan. Adapted from Matt Pocock's /grill-me (mattpocock/skills) and combined with Shape Up's appetite + fidelity discipline.
---

# /grill-me — Nexus shaping interviewer

## When to invoke

- User just produced (or asked you to produce) a fat-marker sketch in `2nd-brain/Sketches/`.
- User says "grill me", "interview me", "stress-test this plan", "find the rabbit holes".
- You are about to write code AND there is no corresponding grill transcript in `2nd-brain/Grills/`. Stop and grill first.

## Core procedure (DO NOT DEVIATE)

1. **Read the sketch.** Locate the relevant file in `2nd-brain/Sketches/`. If none exists, refuse to grill and produce a sketch first. The sketch is the input — you cannot grill an idea that hasn't been sketched.
2. **Identify the decision tree.** Every place in the sketch that says "TBD", every connection line without a defined protocol, every affordance without a defined trigger, every rabbit hole — these are the leaves to resolve.
3. **Walk the tree dependency-first.** A decision that gates other decisions is asked first. Never ask a leaf question before its parent is resolved.
4. **Ask one question at a time.** Never bundle. Never list 5 things and ask the user to address them. One question per turn.
5. **Recommend an answer.** Every question carries your best recommendation with a one-sentence rationale. The user can take the recommendation by saying "default" or override with their own answer.
6. **Convert ambiguity into one of three terminal states** for each branch:
   - **DECIDED** — the user gave an answer (or accepted your recommendation).
   - **RABBIT HOLE** — known unknown the user explicitly defers ("decide later"). Goes into the sketch's `RABBIT HOLES:` section.
   - **NO-GO** — explicit scope exclusion ("not doing that"). Goes into the sketch's `NO-GOS:` section.
7. **If a question can be answered by exploring the codebase, explore the codebase instead.** Don't ask the user something `grep` could answer. (This rule is Matt's, and it's load-bearing.)
8. **Stop when the tree is fully resolved.** Every leaf is DECIDED, RABBIT HOLE, or NO-GO. Then write the transcript.

## Output format — write to `2nd-brain/Grills/NN-<slug>.md`

```markdown
---
type: grill
component: <slug matching the sketch>
sketch: ../Sketches/NN-<slug>.md
status: in-progress | resolved
created: YYYY-MM-DD
---

# Grill transcript — <component>

## Q1: <one-line question>
**My recommendation:** <one sentence + rationale>
**Phill's answer:** <verbatim>
**Resolution:** DECIDED | RABBIT HOLE | NO-GO

## Q2: ...

---

## Final state

**Decided:**
- ...

**Rabbit holes (to be revisited):**
- ...

**No-gos (explicitly excluded):**
- ...

**Appetite (Shape Up time budget):** 1d | 3d | 1w | 2w | 6w

**Next step:** promote to `Pitches/NN-<slug>.md`
```

## Pacing

- Sessions typically run 30-60 minutes / 15-50 questions (per Matt Pocock).
- A grill that resolves in <5 questions means the sketch wasn't fat-marker enough — go back and re-sketch with more abstraction.
- A grill that's stuck >50 questions means the sketch is too big — break it into sub-sketches.

## What grill-me is NOT

- **Not a code review.** That's `/code-review`.
- **Not a PRD writer.** The PRD/pitch is downstream — only after the grill resolves.
- **Not a brainstorm.** Brainstorm produces options; grill picks between them.
- **Not optional.** If you're tempted to skip the grill because you "know what to build," that's exactly when you most need it.

## Hard rules

1. **Never ask >1 question per turn.** Bundling is the dominant failure mode.
2. **Never accept "TBD" without a follow-up.** If the user says "TBD," ask "should this be a RABBIT HOLE (defer) or a NO-GO (exclude)?"
3. **Never write code during a grill.** Code is downstream. The grill's only output is the transcript markdown.
4. **Always recommend an answer.** "I don't know" is not a valid recommendation. Take a position, then let the user override.
5. **Respect context budget.** The user has a token ceiling. Long-winded preambles burn it. Each Q+A should fit in <300 tokens of agent output.

## Provenance

Adapted from:
- [mattpocock/skills /grill-me SKILL.md](https://github.com/mattpocock/skills/blob/main/skills/productivity/grill-me/SKILL.md)
- [Shape Up — Chapter 4: Find the Elements](https://basecamp.com/shapeup/1.3-chapter-04) (fat marker sketch + breadboarding)
- [Shape Up — Chapter 3: Set Boundaries](https://basecamp.com/shapeup/1.2-chapter-03) (appetite + fidelity discipline)
