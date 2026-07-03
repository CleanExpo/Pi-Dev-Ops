---
name: nexus
description: Use when dispatching any task to a sub-Fable Claude model (Opus/Sonnet/Haiku subagent, SDK call, or another CLI) that should run at Fable-5-grade discipline — wrap the task in the Nexus Prompt. Also use when a skill or agent asks for "the Nexus Prompt", "nexus wrapper", or a model-calibrated task preamble.
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# nexus — wrap any task in the Nexus Prompt

The Nexus Prompt is the single master preamble that lifts sub-Fable Claude tiers
(Opus / Sonnet / Haiku) toward Fable-5-grade operating behaviour: act-on-enough-info,
scope discipline, a closed verification loop with grounded progress claims, boundary
and turn-ending rules, delegation with fresh-context verifiers, and outcome-first
communication. Distilled from Anthropic's "Prompting Claude Fable 5" doctrine.

The prompt body is the single source of truth in
[`references/NEXUS_PROMPT.md`](references/NEXUS_PROMPT.md); read it there — never
restate or fork it.

## Procedure

1. Read [`references/NEXUS_PROMPT.md`](references/NEXUS_PROMPT.md).
2. Before filling `{TASK}`, check for a prior handoff scoped to this work: invoke
   `resume-from-handoff` (no arguments — it finds the most recent handoff itself). If it
   reports MATCH or MINOR DRIFT, fold its "Pick up here" pickup point and open questions
   into the task instead of re-deriving them from scratch. If it reports MATERIAL DRIFT,
   CANNOT RESUME, or finds no handoff, proceed to fill `{TASK}` (step 3) normally — a
   missing or stale handoff is not a blocker, just a missed shortcut.
   - **Completion criterion:** a handoff lookup was attempted (found-and-folded-in, or
     confirmed absent/stale) before the task is drafted.
3. Replace `{TASK}` with the complete task — include the why ("I'm working on X for Y;
   they need Z. With that in mind: …") and any hard constraints (hands-off surfaces,
   ff-only mandates, output contracts). The wrapper does not carry task context for you.
   - **Completion criterion:** no `{TASK}` placeholder remains; the task states its why
     and constraints.
4. **Tier selection** — decide *before* dispatch, as the dispatching agent, which model
   tier receives the filled prompt. This is a caller-side decision the receiving model
   never sees; it is separate from the prompt body's own "Model calibration" section
   (`references/NEXUS_PROMPT.md`), which tells a model how to behave *once* it is running
   at a given tier, not which tier to pick.
   - **Fable 5:** reserve for `boardroom`'s synthesizer/escalation-arbiter role,
     `judge`/spec-gate decisions, and cross-skill synthesis after an MOA fan-out. Not for
     routine dispatch — this tier is for the moments where the task *is* the judgment
     call, not a task that merely benefits from more care.
   - **Opus 4.8:** single-specialist dispatches carrying real ambiguity — design work,
     architecture-adjacent decisions, security-sensitive changes. Use when the task has
     more than one defensible approach and picking wrong is costly to unwind.
   - **Sonnet 5:** the default execution tier. Routine dev, copy, and dispatch work with
     a clear spec and a known pattern to follow lands here unless one of the other three
     tiers is explicitly warranted.
   - **Haiku 4.5:** mechanical, routine sub-tasks only — lint-fix-style changes,
     single-increment scope, nothing requiring judgment. Escalate to a higher tier after
     2 failed verify-fix cycles, matching this skill's own Haiku calibration in
     `references/NEXUS_PROMPT.md` verbatim.
   - **Completion criterion:** a tier is chosen and named before dispatch (step 5), with
     the reason traceable to one of the four bullets above — not left to the receiving
     model to infer from its own calibration section.
5. Dispatch: pass the filled prompt verbatim as the subagent prompt at the tier chosen in
   step 4, the SDK `system`+user pair, or another CLI — non-Claude-Code harness
   instructions are in [`references/cross-cli.md`](references/cross-cli.md); look them up
   there.
   - **Completion criterion:** the receiving model got the body verbatim — no partial
     paste, no appended show-your-reasoning instructions (`reasoning_extraction` trap).
6. On return, verify the report against the prompt's own contract before trusting it:
   claims grounded in tool results, mandate compliance (e.g. reflog for git mandates),
   scope untouched. Independent spot-check ≥1 claim.
   - **Completion criterion:** at least one claim independently re-verified, or the
     discrepancy reported.
7. Before returning control, write a handoff scoped to the completed task: invoke
   `session-handoff` with the task's scope string as its argument. This runs on the
   dispatching session, not the sub-Fable model — it records what the dispatched task did,
   what shipped, and where a future Nexus call (or a human) picks up next, so step 2's
   lookup has something to find. Skip only if the task was pure research/read-only with
   nothing to hand off (say so explicitly rather than silently omitting the step).
   - **Completion criterion:** `session-handoff` ran and produced a report, or its
     omission was stated with a reason.

## Autonomy contract

Model-invocable by design: any skill or agent dispatching work to a lower tier wraps it
with this skill's prompt — that is how the specialised-skill fleet runs Nexus-calibrated
without per-skill edits. Do not edit `references/NEXUS_PROMPT.md` ad hoc: it is
recalibrated monthly from fresh Anthropic guidance (behaviour-changing deltas only,
≤120-line body cap) via PR. Test/version history: 2nd Brain Wiki `nexus-prompt` page.
