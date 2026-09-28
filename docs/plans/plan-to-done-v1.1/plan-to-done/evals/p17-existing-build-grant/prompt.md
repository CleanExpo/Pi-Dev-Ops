---
name: p17-existing-build-grant
description: "Existing build grant (converted from evaluation-cases.json P17)"
tags: [planning-only, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Stay in planning and writing; identify next action without executing."
---
/plan-to-done Scenario for this planning session: A prior build grant exists, but this request is planning only.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
