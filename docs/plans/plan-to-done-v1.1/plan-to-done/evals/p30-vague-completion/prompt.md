---
name: p30-vague-completion
description: "Vague completion (converted from evaluation-cases.json P30)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Replace vague phrases with scoped journeys, interface obligations and observable acceptance cases."
---
/plan-to-done Scenario for this planning session: The plan says improve UX and wire everything together.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
