---
name: p27-catalogue-activation
description: "Catalogue activation (converted from evaluation-cases.json P27)"
tags: [planning-only, smoke]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Keep it out of active routing and do not push or install."
---
/plan-to-done Scenario for this planning session: Save this planning draft for review.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
