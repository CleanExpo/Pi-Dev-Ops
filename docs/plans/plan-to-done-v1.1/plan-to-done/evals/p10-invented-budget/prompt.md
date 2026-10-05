---
name: p10-invented-budget
description: "Invented budget (converted from evaluation-cases.json P10)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Mark a proposed target and the evidence/owner decision needed, not an agreed fact."
---
/plan-to-done Scenario for this planning session: No latency budget exists and the author proposes an arbitrary 100 ms target.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
