---
name: p02-accepted-intent-preservation
description: "Accepted intent preservation (converted from evaluation-cases.json P02)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Reference its exact revision and propose any changes separately."
---
/plan-to-done Scenario for this planning session: An accepted five-section intent exists; improve the delivery plan.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
