---
name: p09-engineering-omission
description: "Engineering omission (converted from evaluation-cases.json P09)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Account for all engineering categories with justified applicability."
---
/plan-to-done Scenario for this planning session: The draft omits concurrency, migration and recovery.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
