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
2. Replace `{TASK}` with the complete task — include the why ("I'm working on X for Y;
   they need Z. With that in mind: …") and any hard constraints (hands-off surfaces,
   ff-only mandates, output contracts). The wrapper does not carry task context for you.
   - **Completion criterion:** no `{TASK}` placeholder remains; the task states its why
     and constraints.
3. Dispatch: pass the filled prompt verbatim as the subagent prompt (pick the model tier
   per the prompt's own calibration section), the SDK `system`+user pair, or another CLI —
   non-Claude-Code harness instructions are in [`references/cross-cli.md`](references/cross-cli.md);
   look them up there.
   - **Completion criterion:** the receiving model got the body verbatim — no partial
     paste, no appended show-your-reasoning instructions (`reasoning_extraction` trap).
4. On return, verify the report against the prompt's own contract before trusting it:
   claims grounded in tool results, mandate compliance (e.g. reflog for git mandates),
   scope untouched. Independent spot-check ≥1 claim.
   - **Completion criterion:** at least one claim independently re-verified, or the
     discrepancy reported.

## Autonomy contract

Model-invocable by design: any skill or agent dispatching work to a lower tier wraps it
with this skill's prompt — that is how the specialised-skill fleet runs Nexus-calibrated
without per-skill edits. Do not edit `references/NEXUS_PROMPT.md` ad hoc: it is
recalibrated monthly from fresh Anthropic guidance (behaviour-changing deltas only,
≤120-line body cap) via PR. Test/version history: 2nd Brain Wiki `nexus-prompt` page.
