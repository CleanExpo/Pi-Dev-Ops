---
name: p22-stale-decision
description: "Stale decision (converted from evaluation-cases.json P22)"
tags: [typesafe, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Specify revalidation and stale-result rejection before action."
---
/plan-to-done Scenario for this planning session: A worker loses its lease after decision evaluation.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
