---
name: resume-from-handoff
description: Resume work from a session handoff. Reads the latest handoff, verifies current repo state against it, reconciles drift, then continues from the documented pickup point without re-deriving old context. Verification is read-only and mandatory before any work resumes.
---

# resume-from-handoff — Resume From a Session Handoff

Pick up work where a previous session left off, using a `session-handoff` report as the
source of truth. Read-side companion to `session-handoff`.

**Hard rule — verify before you resume.** Phases 1–3 are read-only. Do not edit, commit,
push, deploy, migrate, or run any mutating command until Phase 2 verification is complete
and Phase 3 reconciliation is reported. If the repo has drifted materially from the
handoff, STOP and surface it before resuming.

## Input

```text
$ARGUMENTS
```

`$ARGUMENTS` may be a path to a handoff file, pasted handoff text, or a branch / PR
reference. If empty, look for the most recent handoff under `.session-handoff/` or in the
current context. If none can be found, ask for it and stop.

## Phase 1 — Load the handoff (read-only)

Parse the handoff and extract: summary, starting point, decisions locked + what shipped
(branch/commits/files), key files, running state, verification commands, deferred + open
questions, pick-up-here steps (start here / do not redo / first command), risk notes. If
the input is not a recognisable handoff, say so and stop.

## Phase 2 — Verify repo state against the handoff (read-only)

```bash
git branch --show-current
git status --short
git log --oneline -n 12
git diff --stat
```

Check, claim by claim:

- Branch present / checked out
- Claimed commits exist (`git cat-file -t <sha>`, `git log`)
- "What shipped" / "key files" exist with claimed status
- Working tree clean/dirty as the running state implies
- Open PR/issue state (`gh pr view` if available)

Re-run the handoff's verification commands only if safe and read-only. Report pass/fail
honestly; mark anything unchecked as `NOT CHECKED`.

## Phase 3 — Reconciliation report

### Resume Reconciliation

- Verdict: MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME
- State vs handoff (what matches, what changed since)
- Still-valid pickup instructions
- Now-invalid / changed steps (with why)
- Blockers

Stop conditions (do NOT resume — surface and ask): missing branch/commits, conflicting
uncommitted changes, PR already merged/closed in a way that obsoletes the work, or a
"first command" that would now be destructive or wrong.

## Phase 4 — Resume the work

Only after MATCH or MINOR DRIFT, and after stating your plan:

1. Skip everything in the handoff's "Do not redo" list.
2. Follow "Start here", adjusted for any minor drift.
3. Run the "First command to run" (or its corrected equivalent).
4. Respect repo gates — run `judge` before building anything new not already approved;
   honour CLAUDE.md / AGENTS.md boundaries.

State what you are resuming, what you are skipping, and why.

## Output

End with: what was resumed, first action taken, next checkpoint, and:

`Resume complete (or paused). Next safe action: <one sentence>.`
