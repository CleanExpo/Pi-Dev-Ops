# Using the Nexus Prompt outside Claude Code

`references/NEXUS_PROMPT.md` is plain text with one placeholder (`{TASK}`). Any harness that
accepts a system prompt or a pasted preamble can run it. Replace `{TASK}`; change nothing else.

## Claude Code
Invoke the `nexus` skill, or wrap a subagent: pass the prompt body with `{TASK}` filled as the
agent prompt (model: sonnet/haiku for lower tiers). The skill is model-invocable — agents and
other skills reach it autonomously.

## Codex CLI
This repo follows the shared-skill convention (`.agents/skills/` mirrors `skills/` for `judge`,
`spm`, `session-handoff`). Use `$nexus`-style invocation where wired, or:
`codex "$(sed "s/{TASK}/<task>/" skills/nexus/references/NEXUS_PROMPT.md)"`.
Policy reminder: Codex is precision-only — never in autonomous loops (feedback-anthropic-first).

## Gemini CLI / Copilot CLI / Cursor / any other agent CLI
Two options, in preference order:
1. **AGENTS.md / GEMINI.md layer** — paste the prompt body (without the `TASK:` footer) into the
   project's agent-instructions file; the CLI loads it as standing doctrine.
2. **Per-invocation** — shell substitution as in the Codex example, or paste as the first message.

## API / SDK (any provider)
Send the prompt body as the `system` parameter and the task as the first user message. For
Claude models: works on Opus/Sonnet/Haiku 4.x; on Fable 5 it is mostly redundant (the behaviours
are native) but harmless.

## Invariants (all harnesses)
- Keep the body verbatim — it is calibrated as a unit; partial pastes lose the loop.
- Never append "show/explain your reasoning" instructions (`reasoning_extraction` refusal trap
  on Fable-tier models).
- Version lives in the header line; the monthly recalibration updates this file via PR.
