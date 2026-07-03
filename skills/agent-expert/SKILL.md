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

## Skill-process lessons

If the lesson is about a **skill's own process or instructions** — its `SKILL.md`
was unclear, missing a step, contradicted itself, or its guidance is what caused
the mistake — rather than about the task's domain content, add one extra field:
`applies_to_skill`, set to that skill's exact folder name under `skills/` (e.g.
`"agent-expert"`, `"skill-authoring-standard"`). Omit this field entirely for
ordinary domain lessons (a code bug, an infra misconfiguration, a business-logic
error) — it is optional and skill-scoped lessons are the minority case.

Example — a domain lesson (no `applies_to_skill`):

```json
{"ts": "2026-07-03T02:00:00Z", "source": "architecture-review", "category": "security", "lesson": "Webhook signature verification must use hmac.compare_digest, not ==.", "severity": "warn"}
```

Example — a skill-process lesson (`applies_to_skill` set):

```json
{"ts": "2026-07-03T02:00:00Z", "source": "linear-task-processor", "category": "process", "applies_to_skill": "skill-authoring-standard", "lesson": "The review-checklist.md line-count cap (200 lines) doesn't say whether YAML frontmatter counts toward the limit — two agents interpreted this differently in the same week. Clarify in the checklist itself.", "severity": "warn"}
```

`scripts/scan_skill_lessons.py` reads this field to detect when a skill's own
instructions need a fix — see that script for the threshold and PR flow.
