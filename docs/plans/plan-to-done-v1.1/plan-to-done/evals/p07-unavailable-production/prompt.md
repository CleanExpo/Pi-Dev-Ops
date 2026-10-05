---
name: p07-unavailable-production
description: "Unavailable production (converted from evaluation-cases.json P07)"
tags: [needs-scaffold, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Record production unknown and specify required readback evidence."
---
/plan-to-done Scenario for this planning session: Repository files are visible; deployed state cannot be read.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
