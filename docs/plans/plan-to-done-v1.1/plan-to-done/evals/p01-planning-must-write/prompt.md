---
name: p01-planning-must-write
description: "Planning must write (converted from evaluation-cases.json P01)"
tags: [planning-only, smoke]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Write the planning packet within the authorised output area; no product changes."
---
/plan-to-done Scenario for this planning session: Plan the completion of this existing project. Do not build.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
