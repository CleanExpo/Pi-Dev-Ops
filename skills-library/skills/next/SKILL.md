---
name: next
description: Task transition. Use after completing a task to determine and prepare for the next one. Reads PROGRESS.md and Linear.
disable-model-invocation: true
---

## Protocol

### Step 1: Save Current State
Write to `.claude/PROGRESS.md`:
- What was just completed
- Files modified
- Decisions made
- Any follow-up items

### Step 2: Identify Next Task
1. Read `.claude/PROGRESS.md` for pending tasks.
2. Read `git log --oneline -5` for recent context.
3. Check Linear for Todo/In Progress issues assigned to the team.
4. Present the next task and ask for confirmation.

### Step 3: Prepare Context
- If the next task is **related** to the current work → suggest `/compact` to preserve relevant context.
- If the next task is **unrelated** → suggest `/clear` to free all context (biggest token saver).

State: "Ready. Next task: [description]. Context [recommendation]."
