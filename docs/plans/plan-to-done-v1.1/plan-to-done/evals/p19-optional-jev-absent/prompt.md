---
name: p19-optional-jev-absent
description: "Optional Jev absent (converted from evaluation-cases.json P19)"
tags: [typesafe, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Finish independent planning with current selector/reviewer methods."
---
/plan-to-done Scenario for this planning session: The TypeSafe runtime is unavailable.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
