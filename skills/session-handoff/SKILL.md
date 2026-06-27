---
name: session-handoff
description: Durable session handoff (/session-handoff). Generate a precise handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming later. Read-only — captures what was done, where it started, decisions locked, what shipped, key files, running state, verification commands, deferred/open questions, exact pickup point, risk notes, and a handoff quality check.
owner_role: Tier-Architect (end-of-session handoff; read-only reporter)
status: active
automation: manual
---

# session-handoff — Durable Session Handoff

Review/report only — `/session-handoff` never edits, commits, pushes, deploys, migrates,
modifies tickets, or changes external systems. It produces a handoff so another terminal
or agent can resume without rereading the whole conversation. Any mutation may only follow
a separate, explicit user request after the handoff.

Companion to `judge`: `/judge` decides *whether to build*; `/session-handoff` records
*what happened and where the next agent picks up*. Distinct from `tao-judge` (machine
loop-termination scorer).

## Input scope

Handoff scope is supplied as `$ARGUMENTS` (a ticket, branch, PR, feature, or repo area).
If empty, infer scope from the current branch, git status, recent commits, current diff,
recently changed files, conversation context, and the CLAUDE.md / AGENTS.md guidance.

## Read-only inspection

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

Only run tests if the user explicitly asks for verification execution; otherwise report
the commands to run. Do not modify anything.

## Required output — Session Handoff

Produce a handoff with this exact structure (see `.session-handoff/report-template.md`):

1. Summary of what was done (attempted / completed / partial / not touched)
2. Where it started (request, branch, files, problem, constraints; `Unknown from available context` if unclear)
3. Decisions locked + what shipped (separate decisions from implementation; if nothing committed/pushed, say `Nothing shipped yet. Current work is local/session-only.`)
4. Key files (table; Status ∈ Created / Modified / Deleted / Read-only inspected / Needs review / Deferred / Unknown)
5. Running state (never claim a process is running unless verified)
6. Verification — exact commands (backend / dashboard / smoke / skill check)
7. Deferred + open questions (two separate lists, each with Owner / Blocking / Why)
8. Pick up here (`Start here` steps, `Do not redo`, and an explicit `First command to run`)
9. Risk notes (unverified assumptions, failed commands, stale context, secrets/env gaps)
10. Handoff quality check

End with: `Handoff complete. Next safe action: <one sentence>.`

## Quality rules

- Do not claim tests passed unless they were actually run.
- Do not claim anything shipped unless commit/push/merge evidence exists.
- Do not claim a process is running unless verified.
- Clearly separate completed work from deferred work.
- Always provide the first command the next agent should run.
