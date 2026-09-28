---
name: p04-missing-handoff
description: "Missing handoff (converted from evaluation-cases.json P04)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Expose the required missing handoff and its interface/ownership obligations."
---
/plan-to-done Scenario for this planning session: Admin intake is planned but the required technician handoff is absent.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
