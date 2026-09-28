---
name: p26-unretrieved-local-command
description: "Unretrieved local command (converted from evaluation-cases.json P26)"
tags: [needs-scaffold, full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Record unresolved command binding; do not assume the command is globally absent."
---
/plan-to-done Scenario for this planning session: A lookup at skills/goal/SKILL.md returns 404.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
