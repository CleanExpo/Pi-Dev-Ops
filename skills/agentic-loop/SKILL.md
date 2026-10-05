---
name: agentic-loop
description: Infinite self-correcting iteration until completion criteria met. Use when a task needs an open-ended, self-correcting loop that keeps iterating until explicit completion criteria are met, such as an overnight or unattended run, a stop guard that blocks the agent from quitting early, a completion sentinel like PROMISE COMPLETE, or Ralph Wiggum style loops with an iteration cap, an append-only progress file, one small feature per iteration, and a green-CI gate before each commit.
---

# Agentic Loop

Two-prompt system: task prompt + stop guard.
Agent works -> tries to stop -> guard checks criteria -> not met -> continues.

## Safety Rails
- max_iterations: 20
- max_tokens: 200000
- max_runtime_minutes: 60
- Detect oscillation (fix A breaks B) after 3 iterations

## Overnight-loop guardrails (Ralph Wiggum, Pocock 2026-07)
- Iteration cap: `max_iterations` above is the backstop against never terminating — keep it.
- Append-only progress file: each iteration appends learnings ("append", never "update") — memory across context resets.
- One small feature per iteration: never batch ("do as many as you fancy" recreates the context bloat the loop exists to avoid).
- Green-CI gate: typecheck + tests pass inside the iteration before its commit; broken commits blind the next fresh context.
- Completion sentinel: prompt outputs an explicit token (e.g. `PROMISE COMPLETE`); the loop greps it and exits early rather than relying on the stop guard alone.

[[pocock-ralph-wiggum-overnight-loops-2026-07-14-ingest]]
