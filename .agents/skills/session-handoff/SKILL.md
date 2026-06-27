---
name: session-handoff
description: Generate a precise handoff before stopping, changing terminals, handing work to another agent, opening a PR, or resuming later. Captures summary, starting point, locked decisions, shipped work, key files, running state, verification, deferred questions, and exact pickup point.
---

# session-handoff — Durable Session Handoff

Use this skill to produce a session handoff.

This is read-only by default.

Do not edit files, commit, push, deploy, migrate, create tickets, or modify external systems during this skill unless the user separately asks after the handoff.

## Scope

Handoff scope:

```text
$ARGUMENTS
```

If no scope is provided, infer it from the current repo, branch, diff, recent commits, open task context, and available guidance files.

## Inspect first

Use read-only inspection:

```bash
git branch --show-current
git status --short
git log --oneline -n 8
git diff --stat
git diff --name-only
```

Read relevant project guidance:

- CLAUDE.md
- AGENTS.md
- README.md
- Relevant `.harness/` files
- Relevant `skills/` files
- Relevant test or script files

Do not modify anything.

## Required output

### Session Handoff

#### 1. Summary of what was done

Summarise: what was attempted, what was completed, what is partial, what was not touched.

#### 2. Where it started

Record: original request/ticket/PR/branch, starting problem, starting files, starting constraints, unknowns.

#### 3. Decisions locked + what shipped

**Decisions locked** — for each: Decision / Reason / Evidence.

**What shipped** — for each: Branch / Commit / Files / Behaviour change / Verification status.

If nothing was committed or pushed, state: `Nothing shipped yet. Current work is local/session-only.`

#### 4. Key files

| File | Status | Why it matters | Next owner |
|---|---|---|---|

Statuses: Created, Modified, Deleted, Read-only inspected, Needs review, Deferred, Unknown.

#### 5. Running state

Include: branch, working tree, servers/processes known to be running, PR/issue state if known, environment assumptions, blockers, whether safe to stop.

Do not claim something is running unless verified.

#### 6. Verification — how to confirm things still work

Give exact commands.

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

**Skill check**

```text
$session-handoff
```

Mark anything not applicable.

#### 7. Deferred + open questions

**Deferred** — for each: Item / Owner / Blocking / Why deferred.

**Open questions** — for each: Question / Owner / Blocking / Why it matters.

#### 8. Pick up here

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

List: untested assumptions, failed commands, stale context risks, missing evidence, external dependencies, secrets/env assumptions.

#### 10. Handoff quality check

Confirm: completed vs deferred is clear; shipped vs local-only is clear; verification is not faked; next command is explicit; no unresolved blocker is hidden.

End with:

`Handoff complete. Next safe action: <one sentence>.`
