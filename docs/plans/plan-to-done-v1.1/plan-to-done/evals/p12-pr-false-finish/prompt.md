---
name: p12-pr-false-finish
description: "PR false finish (converted from evaluation-cases.json P12)"
tags: [false-finish, smoke]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Reject product completion and retain remaining delivery requirements."
---
/plan-to-done Scenario for this planning session: The evidence consists only of a draft PR.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
