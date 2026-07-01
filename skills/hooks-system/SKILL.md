---
name: hooks-system
description: Use when adding lifecycle hooks or safety guardrails to a project — the 6 hook types plus the starter guardrail hookset (danger-word block, scope-lock, draft-only).
---

# Hooks System

A hook fires before/after a tool runs and votes on whether it's allowed — a bouncer for
agents. Lives in `.claude/settings.json`, applies to every agent in the project (an agent
cannot tell itself to ignore a hook). Install `rm -rf`-class guards at USER level so every
new project inherits them.

## 6 hook types
1. PreToolUse — block dangerous commands before they run
2. PostToolUse — log every action
3. Stop — enforce completion criteria
4. SubagentStop — track parallel completion
5. PreCompact — back up context before compaction
6. SessionStart — load the prior session's handoff

## Starter guardrail hookset (install these three first)
The "agent deleted my project" insurance for anything running unattended.

1. **Pre-bash danger-word block** — before any shell command, scan for `rm -rf`,
   `drop database` / `drop table`, `git push --force`, `sudo`, `> /dev/`. On match, BLOCK and
   require explicit human approval. Prevents ~90% of destructive-agent incidents.
2. **Scope-lock** — block any write outside the project folder (desktop, home, anywhere
   off-repo). Catches "the agent decided to reorganise your whole computer."
3. **Draft-only (content agents)** — block any tool call that would send / publish / post /
   email; force output to land as a file in `/drafts/` first. You stay the publish button.

Adjacent gates worth adding: an approval gate on `git commit` (no commit without a human
"go"), a pre-edit fact-check on sensitive files (`.env`, prod config, `package.json`) that
shows the diff first, and a network-block for offline-only agents.

## Rules
- Silence defaults to REJECT, never approve — an unhandled hook must block, not pass.
- Keep it to ~3 hooks; >5 approvals/session means you've recreated the typing job.
- "Agent did nothing" almost always = a hook blocked it silently → read the hook log.
- If a guard is universal (danger words), put it in user-level settings, not per-project.
