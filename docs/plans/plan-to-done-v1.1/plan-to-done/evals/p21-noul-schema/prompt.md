---
name: p21-noul-schema
description: "Noul schema (converted from evaluation-cases.json P21)"
tags: [typesafe, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Correct the design against official primitive semantics."
---
/plan-to-done Scenario for this planning session: A proposed decision contract assumes Noul has a separate confidence field.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
