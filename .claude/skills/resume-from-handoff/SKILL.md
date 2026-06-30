---
name: resume-from-handoff
description: Resume work from a session handoff. Reads the latest handoff, verifies current repo state against it, reconciles any drift, then continues the work from the documented pickup point without re-deriving old context. Verification is read-only and mandatory before any work resumes.
argument-hint: "[optional: path to a handoff file, pasted handoff, branch, or PR]"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, Write
---

# /resume-from-handoff — Resume From a Session Handoff

Pick up work where a previous session left off, using a `session-handoff` report as the
source of truth. This is the read-side companion to `/session-handoff`.

**Hard rule — verify before you resume.** Phases 1–3 are read-only. Do not edit, commit,
push, deploy, run migrations, or run any mutating command until Phase 2 verification is
complete and the Phase 3 reconciliation is reported. If the repo has drifted materially
from the handoff, STOP and surface it before resuming.

## Input

The handoff to resume from:

```text
$ARGUMENTS
```

`$ARGUMENTS` may be: a path to a handoff file, pasted handoff text, or a branch / PR
reference. If empty, look for the most recent handoff under `.session-handoff/`
(e.g. a `handoffs/` directory or a saved report), or in the current conversation
context. If none can be found, ask the user to provide the handoff and stop.

## Phase 1 — Load the handoff (read-only)

Parse the handoff and extract:

- Summary of what was done
- Starting point
- Decisions locked + what shipped (branch, commits, files)
- Key files and their claimed status
- Running state
- Verification commands
- Deferred + open questions
- Pick up here (start-here steps, do-not-redo list, first command to run)
- Risk notes

If the input is not a recognisable handoff, say so and stop.

## Phase 2 — Verify repo state against the handoff (read-only)

Confirm the repo actually matches what the handoff claims. Use read-only inspection:

```bash
git branch --show-current
git status --short
git log --oneline -n 12
git diff --stat
```

Check, claim by claim:

- **Branch** — is the handoff's branch present and checked out (or available)?
- **Commits** — do the claimed shipped commits exist? (`git cat-file -t <sha>`, `git log`)
- **Files** — do the "what shipped" / "key files" exist with the claimed status?
- **Working tree** — is it clean/dirty as the handoff's running state implies?
- **Open PR/issue** — still open/merged as stated? (`gh pr view` if available)

Re-run the handoff's **verification commands** only if they are safe and read-only
(type-checks, `import` smoke checks, test suites). Report pass/fail honestly — never fake
a result. Mark anything you could not check as `NOT CHECKED`.

## Phase 3 — Reconciliation report

Produce this before doing any work:

### Resume Reconciliation

- **Verdict:** MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME
- **State vs handoff:** what matches, what changed since the handoff (new commits, moved branch, dirty tree, merged PR, deleted files)
- **Still-valid pickup instructions:** which "start here" steps still apply
- **Now-invalid / changed steps:** steps the drift has obsoleted, with why
- **Blockers:** anything that prevents a clean resume

Stop conditions (do NOT resume — surface and ask):

- The handoff's branch or claimed commits are missing
- The working tree has conflicting uncommitted changes
- The PR was already merged/closed in a way that obsoletes the work
- The "first command to run" would now be destructive or wrong

## Phase 4 — Resume the work

Only after Phase 3 reports MATCH or MINOR DRIFT (and you have stated your plan):

1. Skip everything in the handoff's **Do not redo** list.
2. Follow the **Start here** steps, adjusted for any minor drift noted in Phase 3.
3. Run the handoff's **First command to run** (or the corrected equivalent).
4. Respect the repo's normal gates — e.g. run `/judge` before building anything new that
   was not already approved in the handoff; honour `CLAUDE.md` / `AGENTS.md` boundaries.

Keep the user informed: state what you are resuming, what you are skipping, and why.

## Output

End with a short status:

- What was resumed
- First action taken
- Next checkpoint

`Resume complete (or paused). Next safe action: <one sentence>.`
