---
name: afk-agent
description: Run agents unattended with stop guards and notifications.
---

# AFK Agent

## The AFK Contract
1. Bounded runtime (max N minutes)
2. Bounded cost (max N tokens)
3. No silent failure
4. No premature exit (stop guards)
5. Notification on completion

## Stop Guards
Intercept exit attempts. Verify completion criteria before allowing stop.

## Overnight-loop guardrails (Ralph Wiggum, Pocock 2026-07)
For unattended overnight runs, extend the AFK Contract with:
- Iteration cap: bound iterations too, not just runtime/tokens (items 1-2) — backstop against never terminating.
- Append-only progress file: each iteration appends learnings ("append", never "update") — the agent's memory across context resets.
- One small feature per iteration: never batch; output quality degrades as context fills.
- Green-CI gate: typecheck + tests pass inside each iteration before its commit — one commit per iteration localises breakage.
- Completion sentinel: emit an explicit token (e.g. `PROMISE COMPLETE`); the runner greps it to exit early and fires the completion notification (item 5).

[[pocock-ralph-wiggum-overnight-loops-2026-07-14-ingest]]
