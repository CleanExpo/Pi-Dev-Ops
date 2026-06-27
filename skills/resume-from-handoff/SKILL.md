---
name: resume-from-handoff
description: Resume work from a session handoff (/resume-from-handoff). Reads the latest handoff, verifies current repo state against it (read-only), reconciles drift, then continues the work from the documented pickup point without re-deriving old context. Verification is mandatory before any work resumes.
owner_role: Tier-Architect (handoff resumption; verify-then-resume)
status: active
automation: manual
---

# resume-from-handoff — Resume From a Session Handoff

Read-side companion to `session-handoff`. Pick up work where a previous session left off,
using a `session-handoff` report as the source of truth.

Completes the trio: `judge` decides *whether to build*; `session-handoff` records *what
happened and where the next agent picks up*; `resume-from-handoff` *verifies reality
against that handoff and continues the work*.

**Hard rule — verify before you resume.** Phases 1–3 are read-only. Do not edit, commit,
push, deploy, migrate, or run any mutating command until Phase 2 verification is complete
and Phase 3 reconciliation is reported. On material drift or a missing branch/commit, STOP
and surface before resuming.

## Input

Handoff to resume from is supplied as `$ARGUMENTS`: a path to a handoff file, pasted
handoff text, or a branch / PR reference. If empty, look for the most recent handoff under
`.session-handoff/` or in the current context; if none is found, ask and stop.

## Phase 1 — Load the handoff (read-only)

Parse summary, starting point, decisions locked + what shipped (branch/commits/files), key
files, running state, verification commands, deferred/open questions, pick-up-here steps,
and risk notes. If the input is not a recognisable handoff, say so and stop.

## Phase 2 — Verify repo state against the handoff (read-only)

```bash
git branch --show-current
git status --short
git log --oneline -n 12
git diff --stat
```

Check claim by claim: branch present/checked out; claimed commits exist
(`git cat-file -t <sha>`); shipped/key files exist with claimed status; working tree
clean/dirty as implied; PR/issue state (`gh pr view` if available). Re-run only safe,
read-only verification commands; report pass/fail honestly; mark unchecked items
`NOT CHECKED`.

## Phase 3 — Reconciliation report

Emit a **Resume Reconciliation** with a verdict — MATCH / MINOR DRIFT / MATERIAL DRIFT /
CANNOT RESUME — plus what matches, what changed since the handoff, still-valid vs
now-invalid pickup steps, and blockers. See `.resume-from-handoff/reconciliation-checklist.md`.

Stop conditions (do NOT resume — surface and ask): missing branch/commits; conflicting
uncommitted changes; PR already merged/closed obsoleting the work; a "first command" that
would now be destructive or wrong.

## Phase 4 — Resume the work

Only after MATCH or MINOR DRIFT and after stating the plan: skip the "Do not redo" list;
follow "Start here" (adjusted for minor drift); run the "First command to run" (or its
corrected equivalent); respect repo gates (run `judge` before building anything new not
already approved; honour CLAUDE.md / AGENTS.md boundaries).

## Output

End with what was resumed, the first action taken, the next checkpoint, and:
`Resume complete (or paused). Next safe action: <one sentence>.`
