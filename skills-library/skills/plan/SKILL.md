---
name: plan
description: Architecture planning with deep reasoning. Use for "plan", "design", "architect", "how should we build". Read-only, structured plan output. Runs in a forked context with Opus.
context: fork
agent: Explore
model: opus
---

Plan: $ARGUMENTS

## Protocol

1. Read `.claude/ARCHITECTURE.md` and `.claude/STANDARDS.md` if they exist.
2. Use `grep`/`glob` to understand existing patterns in the relevant area.
3. Read only the files directly relevant to the planned change.
4. Do NOT write any code. Only produce a plan.

## Output Format

- **Objective**: 1 sentence — what this achieves
- **Files to change**: `filepath` + what changes and why (max 10 files)
- **Steps**: numbered, dependency-ordered implementation steps
- **Reuse**: existing functions/utilities to leverage (with file paths)
- **Tests**: specific test cases needed
- **Risk**: what could break, and how to mitigate

**UNDER 350 words total.** The plan should be actionable without re-reading the codebase.
