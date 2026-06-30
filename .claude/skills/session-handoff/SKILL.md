---
name: session-handoff
description: Generate a precise session handoff before stopping, switching terminals, opening a PR, handing work to another agent, or resuming work later. Captures what was done, where it started, decisions locked, files changed, running state, verification steps, deferred questions, and exact pickup point.
argument-hint: "[optional: ticket, branch, PR, feature, repo area, or handoff scope]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---

# /session-handoff — Durable Session Handoff

Generate a clean handoff for the current work session.

This command is read-only by default.

Do not edit files, commit, push, deploy, run migrations, modify tickets, or change external systems unless the user separately asks for that after the handoff.

## Input scope

User supplied handoff scope:

```text
$ARGUMENTS
```

If `$ARGUMENTS` is empty, infer the scope from:

- Current branch
- Git status
- Recent commits
- Current diff
- Recently changed files
- Current conversation context
- Repo guidance in CLAUDE.md
- Agent boundaries in AGENTS.md
- Relevant `.harness/`, `skills/`, `scripts/`, `tests/`, `app/`, `dashboard/`, or `mcp/` state

## Read-only inspection checklist

Inspect what is available without modifying anything:

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

If safe and useful, also inspect:

```bash
git diff
```

Only run tests if the user specifically asks for verification execution. Otherwise, report the verification commands to run.

## Required output

Produce the handoff in this exact structure:

### Session Handoff

#### 1. Summary of what was done

Short, factual summary. Include:

- What task was attempted
- What was completed
- What was partially completed
- What was not touched

#### 2. Where it started

Record the starting context:

- Original user request or ticket
- Starting branch
- Starting files or system area
- Starting problem
- Starting constraints

If the true start is unknown, say `Unknown from available context`.

#### 3. Decisions locked + what shipped

Separate decisions from implementation.

**Decisions locked**

- Decision:
- Reason:
- Evidence:

**What shipped**

- Branch:
- Commit:
- Files:
- Behaviour change:
- User-facing change:
- Internal-only change:

If nothing was committed or pushed, say:

`Nothing shipped yet. Current work is local/session-only.`

#### 4. Key files

| File | Status | Why it matters | Next owner |
|---|---|---|---|

Status must be one of: Created, Modified, Deleted, Read-only inspected, Needs review, Deferred, Unknown.

#### 5. Running state

Record:

- Current branch
- Git working tree state
- Local server state, if known
- Background process state, if known
- Open PR or issue, if known
- Environment assumptions
- Known blockers
- Whether work is safe to stop

Never pretend something is running if you did not verify it.

#### 6. Verification — how to confirm things still work

Provide exact commands, grouped by area:

**Backend**

```bash
python -c "from app.server.main import app"
python -m pytest tests/ -x -q
```

**Dashboard**

```bash
cd dashboard
npx tsc --noEmit
npm run build
```

**Smoke**

```bash
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

**Skill command check**

```text
claude
/session-handoff
```

For Codex:

```text
$session-handoff
```

If a command is not appropriate for this session, mark it `Not applicable` and explain why.

#### 7. Deferred + open questions

Use two separate lists.

**Deferred** — things intentionally not done.

**Open questions** — questions that need a user, owner, maintainer, or future agent decision.

Each item must include:

- Owner:
- Why it matters:
- Blocking or non-blocking:

#### 8. Pick up here

Give the next agent exact continuation steps:

```text
Start here:
1. ...
2. ...
3. ...

Do not redo:
- ...

First command to run:
<command>
```

#### 9. Risk notes

Call out anything that could mislead the next session:

- Unverified assumptions
- Possible stale context
- Failed commands
- Untested code
- External dependency gaps
- Secrets/env assumptions
- Conflicting instructions

#### 10. Handoff quality check

Before finalising, confirm:

- No unsupported shipping claims
- No fake verification
- No hidden "still running" claim
- No missing branch/state summary
- No unclear pickup point
- Deferred work is separated from completed work

End with:

`Handoff complete. Next safe action: <one sentence>.`
