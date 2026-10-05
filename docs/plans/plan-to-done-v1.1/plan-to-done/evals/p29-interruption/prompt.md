---
name: p29-interruption
description: "Interruption (converted from evaluation-cases.json P29)"
tags: [needs-scaffold, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Resume the same plan identity with revalidated sources and existing document references."
---
/plan-to-done Scenario for this planning session: Planning stops mid-packet and resumes with a new model session.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
