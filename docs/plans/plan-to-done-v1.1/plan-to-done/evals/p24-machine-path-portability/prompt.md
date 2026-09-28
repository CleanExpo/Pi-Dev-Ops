---
name: p24-machine-path-portability
description: "Machine path portability (converted from evaluation-cases.json P24)"
tags: [full]
max_turns: 40
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Agent, TodoWrite]
expected_outcome: "Use host resolution and write portability checks; do not copy machine-specific assumptions."
---
/plan-to-done Scenario for this planning session: The draft assumes one absolute MacBook home path on every host.

Write the planning packet into `docs/plans/` only. Finish with the operator brief
(Written · Planning status · Coverage gaps · Decisions · Next) as your final message.
