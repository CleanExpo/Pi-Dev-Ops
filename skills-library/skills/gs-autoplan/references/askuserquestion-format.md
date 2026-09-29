# AskUserQuestion format (the "preamble" format every step refers to)

Adapted from gstack's shared preamble. The runtime machinery (session-kind
detection, Conductor transport, question tuning, preference hooks, decision and
question logs) is removed. What remains is the decision-brief format itself.

## Transport

- Call AskUserQuestion as a tool_use. If an `mcp__*__AskUserQuestion` variant is
  listed, prefer it.
- If AskUserQuestion is unavailable or the call errors, do NOT silently
  auto-decide and do NOT write the decision into the plan as a substitute. Render
  the same brief as a markdown message (prose fallback, below) as the final
  message of the turn, then STOP and wait for the typed answer.
- A skill that authorizes auto-decisions (only `/gs-autoplan`) answers with the
  recommended option and records it; nothing else auto-decides.

**Prose fallback.** Same information as the tool format, as paragraphs. It MUST
surface: (1) a plain-English ELI10 of the issue and its stakes, first;
(2) `Completeness: X/10` on each choice when options differ in coverage;
(3) the `Recommendation: <choice> because <reason>` line plus `(recommended)` on
that choice. Layout: a `D<N>` title, an explicit reply line listing the offered
selectors, the ELI10, the Recommendation, one paragraph per choice, a closing
`Net:` line.

**Continuation.** Each brief carries a stable label (`D<N>`, or `D<N>.k` in a
split chain). A bare letter maps to the single most recent unanswered brief; if
more than one is open, ask which one it answers.

**One-way / destructive confirmations in prose.** Require an explicit typed
confirmation, state plainly what is irreversible, and never proceed on a vague
reply.

## Format

```
D<N> — <one-line question title>
Project/branch/task: <1 short grounding sentence using the current branch>
ELI10: <plain English a 16-year-old could follow, 2-4 sentences, name the stakes>
Stakes if we pick wrong: <one sentence on what breaks, what user sees, what's lost>
Recommendation: <choice> because <one-line reason>
Completeness: A=X/10, B=Y/10   (or: Note: options differ in kind, not coverage — no completeness score)
Pros / cons:
A) <option label> (recommended)
  ✅ <pro — concrete, observable, ≥40 chars>
  ❌ <con — honest, ≥40 chars>
B) <option label>
  ✅ <pro>
  ❌ <con>
Net: <one-line synthesis of what you're actually trading off>
```

D-numbering: first question in a skill invocation is `D1`; increment yourself.

ELI10 is always present, in plain English, not function names. Recommendation is
ALWAYS present. Keep the `(recommended)` label on exactly one option.

Completeness: use `Completeness: N/10` only when options differ in coverage.
10 = complete, 7 = happy path, 3 = shortcut. If options differ in kind, write:
`Note: options differ in kind, not coverage — no completeness score.`

Pros / cons: use ✅ and ❌. Minimum 2 pros and 1 con per option when the choice is
real; minimum 40 characters per bullet. Hard-stop escape for one-way/destructive
confirmations: `✅ No cons — this is a hard-stop choice`.

Neutral posture: `Recommendation: <default> — this is a taste call, no strong
preference either way`; `(recommended)` STAYS on the default option.

Effort both-scales: when an option involves effort, label both human-team and
CC time, e.g. `(human: ~2 days / CC: ~15 min)`.

## Handling 5+ options — split, never drop

AskUserQuestion caps every call at 4 options. With 5+ real options, never drop,
merge or silently defer one to fit: batch into ≤4-groups (coherent alternatives)
or split per-option (independent scope items, the default when unsure):
sequential `D<N>.k` calls, each with its ELI10, Recommendation, kind-note and
buckets **A) Include, B) Defer, C) Cut, D) Hold** (stop chain, discuss); a
`D<N>.final` validates the assembled set; for N>6 fire a `D<N>.0` meta-question
first.

## Self-check before emitting

- [ ] D<N> header present
- [ ] ELI10 paragraph present (stakes line too)
- [ ] Recommendation line present with concrete reason
- [ ] Completeness scored (coverage) OR kind-note present (kind)
- [ ] Every option has ≥2 ✅ and ≥1 ❌, each ≥40 chars (or hard-stop escape)
- [ ] (recommended) label on one option (even for neutral posture)
- [ ] Dual-scale effort labels on effort-bearing options (human / CC)
- [ ] Net line closes the decision
- [ ] You are calling the tool, not writing prose, unless the fallback applies
- [ ] If you had 5+ options, you split (or batched into ≤4-groups); none dropped

## Voice

- Lead with the point. Say what it does, why it matters, and what changes for the builder.
- Be concrete. Name files, functions, line numbers, commands, outputs and real numbers.
- Tie technical choices to user outcomes: what the real user sees, loses, waits for, or can now do.
- Be direct about quality. Bugs matter. Edge cases matter. Fix the whole thing, not the demo path.
- The user has context you do not: domain knowledge, timing, relationships, taste.
  Cross-model agreement is a recommendation, not a decision. The user decides.

## Completeness Principle — Boil the Ocean

AI makes completeness cheap, so the complete thing is the goal. Recommend full
coverage (tests, edge cases, error paths). The only thing out of scope is
genuinely unrelated work (rewrites, multi-quarter migrations); flag that as
separate scope, never as an excuse for a shortcut.

## Search Before Building

- **Layer 1** (tried and true) — don't reinvent. **Layer 2** (new and popular) —
  scrutinize. **Layer 3** (first principles) — prize above all.
- **Eureka:** when first-principles reasoning contradicts conventional wisdom,
  name it: "EUREKA: Everyone does X because they assume [assumption]. But
  [evidence] suggests that's wrong here. This means [implication]."

## Completion Status Protocol

When completing a skill workflow, report status using one of:
- **DONE** — completed with evidence.
- **DONE_WITH_CONCERNS** — completed, but list concerns.
- **BLOCKED** — cannot proceed; state blocker and what was tried.
- **NEEDS_CONTEXT** — missing info; state exactly what is needed.

Escalate after 3 failed attempts, uncertain security-sensitive changes, or scope
you cannot verify. Format: `STATUS`, `REASON`, `ATTEMPTED`, `RECOMMENDATION`.
