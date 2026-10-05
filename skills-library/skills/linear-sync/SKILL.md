---
name: linear-sync
description: Turn audit and review findings into Linear issues in the right project, and define how builder agents pull work from Linear and keep building until the backlog is empty. Use when the user asks to send findings to Linear, sync tasks, or kick off autonomous building from Linear.
version: 1.0.0
metadata:
  hermes:
    tags: [linear, tasks, sync, automation]
    category: launch
---

# Linear Sync

## When to Use
The user wants findings to become tracked work in Linear automatically, and wants agents to work through that backlog. Trigger on "push to Linear", "sync to Linear", "send these to my board", or as the hand-off step of `/ship-it`.

## Prerequisites
The Linear connector/MCP must be connected (`hermes` MCP config) with access to the target workspace. GitHub and the hosting (Vercel) connectors should also be connected so status can round-trip.

## Procedure

### Push (findings → Linear)
1. Read the latest `.hermes/audits/audit-*.md` and `review-*.md`.
2. Map findings to the correct Linear PROJECT (match by product name; if ambiguous, ask the user once and remember the mapping in memory for next time).
3. For each finding create one Linear issue using the connected Linear tools:
   - Title: short and concrete.
   - Description: what, where (file/URL), why it matters, suggested fix — copied from the finding.
   - Priority: CRITICAL → Urgent/High, WARNING → Medium, SUGGESTION → Low.
   - Labels: the lens/source (`pm`, `growth`, `engineer`, `design`, `build-state`, `security`).
   - A machine tag in the description, e.g. `[hermes:build]`, on issues that are safe for an agent to build autonomously; omit it on anything needing a human decision (pricing, legal, irreversible).
4. **De-duplicate**: before creating, search existing issues; update rather than duplicate. Never create the same finding twice across runs.

### Pull (Linear → builders)
The parent Hermes agent watches Linear and dispatches; child agents build. The loop:
1. Parent pulls issues tagged `[hermes:build]` that are unblocked and unassigned, newest-critical first.
2. For each, spawn a child builder subagent **inside a sandbox** (agent-sandbox-skill / E2B) — never on production.
3. The builder works to a definition of done it agrees up front (one feature per task), writes/keeps tests, then opens a PR. It moves the Linear issue across states: `Todo → In Progress → In Review (PR open)`.
4. A separate skeptical reviewer (launch-review engineer lens) checks the PR against the issue's done-criteria before it can move to Done.
5. On merge + production deploy, the issue moves to Done automatically (GitHub/Vercel status round-trip).
6. Repeat until no `[hermes:build]` issues remain unblocked. Use `/goal` so an agent doesn't quit early; the Kanban board's auto-block-on-incomplete-exit catches silent failures.

## Pitfalls
- Anything irreversible or business-judgment (going live with real payments, deleting data, pricing, legal copy) must NOT carry `[hermes:build]` — it waits for a human. This is enforced by the self-improvement-charter.
- Without de-duplication, repeated audits flood the board. Always search first.
- Builders that aren't sandboxed can damage production — sandbox is not optional.

## Verification
Sync is correct when each finding maps to exactly one issue in the right project with the right priority, and no duplicates exist. The build loop is healthy when every issue that reaches Done has a merged PR, a passing test, and is live in production — verified by connector status, not by the agent's say-so.
