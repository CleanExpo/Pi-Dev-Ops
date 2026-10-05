---
name: p15-mandatory-skipped-test
description: "Mandatory skipped test (converted from evaluation-cases.json P15)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Record incomplete evidence, not pass."
---
/plan-to-done Scenario for this planning session: A required security test was skipped.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
