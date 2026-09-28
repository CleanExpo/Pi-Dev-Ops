---
name: p08-historical-test-receipt
description: "Historical test receipt (converted from evaluation-cases.json P08)"
tags: [needs-scaffold, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Scope that receipt to its original candidate and mark current evidence missing."
---
/plan-to-done Scenario for this planning session: The only passing test report belongs to an older commit.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
