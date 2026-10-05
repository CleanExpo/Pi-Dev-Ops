---
name: p05-feature-versus-product
description: "Feature versus product (converted from evaluation-cases.json P05)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Keep wider gaps visible without automatically expanding approved change scope."
---
/plan-to-done Scenario for this planning session: Only the intake change is requested; unrelated product gaps are discovered.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
