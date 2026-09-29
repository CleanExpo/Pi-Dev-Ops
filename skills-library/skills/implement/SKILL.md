---
name: implement
description: Full build pipeline. Use when ready to write code after planning. Injects structured implementation protocol into the current session.
disable-model-invocation: true
---

Implement: $ARGUMENTS

## Protocol

### Phase 1: Plan
- If no plan exists, delegate to `/plan` first. Wait for the plan before coding.
- If a plan exists in `.claude/PROGRESS.md` or the conversation, use it.

### Phase 2: Build
- Create a TodoWrite checklist from the plan steps.
- For each step:
  1. Read the relevant file(s) before modifying.
  2. Make the change. One logical change per edit.
  3. Mark the todo item complete immediately.
- Write tests alongside implementation, not after.

### Phase 3: Verify
- Run `pnpm type-check` (or project equivalent).
- Run relevant tests: `npx vitest run <path>` or `npx playwright test <path>`.
- Run `git diff --stat` to confirm only intended files changed.

### Phase 4: Commit
- Stage specific files (not `git add .`).
- One commit per logical unit of work with a descriptive message.

### Phase 5: Clean Up
- Update `.claude/PROGRESS.md` with what was completed.
- Consider `/compact` if context is heavy.
