---
name: resume
description: Snapshot recovery. Use at session start, after compaction, or when resuming previous work. Restores state from PROGRESS.md and snapshots.
disable-model-invocation: true
---

## Protocol

### Step 1: Read State
1. Read `.claude/PROGRESS.md` for current tasks and decisions.
2. Read `.claude/snapshots/last-task.md` if it exists.
3. Read `git log --oneline -10` for recent commits.
4. Read `git diff --name-only HEAD~3` for recently modified files.

### Step 2: Verify Environment
- Run `pnpm type-check 2>&1 | grep "error TS" | wc -l` to check for errors.
- Check current branch: `git branch --show-current`.

### Step 3: Report
Brief status (under 80 words):
- Current branch and recent commits
- Active/pending tasks from PROGRESS.md
- Any type errors detected
- Ask what to work on next.

**Do NOT re-read all previous files.** Only read state files.
