---
name: p11-no-independent-reviewer
description: "No independent reviewer (converted from evaluation-cases.json P11)"
tags: [smoke]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Write the packet and record required independent review as NOT_RUN."
---
/plan-to-done Scenario for this planning session: Only the authoring model is available.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
