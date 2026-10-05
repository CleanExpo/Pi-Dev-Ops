---
name: p13-ci-false-finish
description: "CI false finish (converted from evaluation-cases.json P13)"
tags: [false-finish, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Keep release/outcome evidence missing."
---
/plan-to-done Scenario for this planning session: CI passed but nothing was deployed.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
