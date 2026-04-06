---
name: agent-expert
description: Act-Learn-Reuse cycle for agent improvement over time.
---

# Agent Experts

## The Cycle
1. ACT - Execute the task
2. LEARN - Extract lessons (patterns, pitfalls, context, tools, conventions)
3. REUSE - Inject relevant lessons into next task

Store lessons in .harness/lessons.jsonl. Inject top 5 most relevant per task.
