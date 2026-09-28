---
name: p14-deployment-false-finish
description: "Deployment false finish (converted from evaluation-cases.json P14)"
tags: [false-finish, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Require post-deployment user outcome evidence."
---
/plan-to-done Scenario for this planning session: A deployment exists but the user workflow is unverified.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
