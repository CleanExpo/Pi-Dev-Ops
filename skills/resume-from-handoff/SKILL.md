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
handoff text, or a branch / PR reference. If empty, load the latest report under
`docs/session-handoffs/` and its paired `.handoff-logs/handoff-<ts>.log`; fall back to
`.session-handoff/` or the current context. If none is found, ask and stop.

## Phase 1 — Load the handoff (read-only)

Parse summary, starting point, decisions locked + what shipped (branch/commits/files), key
files, running state, verification commands, deferred/open questions, pick-up-here steps,
and risk notes. If the input is not a recognisable handoff, say so and stop.

### Entry-root preflight

Before using any host `worktree` command, prove the current terminal was started
inside a real Git checkout. The historic `~/Pi-CEO/Pi-Dev-Ops` directory is an
operational-data wrapper, not a repository; never initialise Git there and never
ask a host to enter an existing worktree from there.

Use the handoff's declared worktree, or the authoritative repository root, with
the installed launcher:

```bash
pi-ceo-harness --worktree "<handoff worktree>" --check
```

If it reports `ENTRY_READY`, restart the Claude/Codex session through the same
launcher before resuming. `ENTRY_RECOVERED` means the legacy wrapper was safely
redirected to the configured real checkout. `ENTRY_BLOCKED` is a hard stop: record
the supplied path and use the handoff's exact checkout rather than guessing.

## Phase 2 — Verify repo state against the handoff (read-only)

```bash
git branch --show-current
git status --short
git log --oneline -n 12
git diff --stat
```

Check claim by claim: branch present/checked out; claimed commits exist
(`git cat-file -t <sha>`); shipped/key files exist with claimed status; working tree
clean/dirty as implied; PR/issue state (`gh pr view` if available).

Re-run only safe, read-only verification commands in this phase; report pass/fail honestly
and mark unchecked items `NOT CHECKED`. Do not run `scripts/handoff-loop.sh` yet: that script
deletes caches and can regenerate tracked manifests, so it belongs after reconciliation rather
than inside the read-only verification phase.

## Phase 3 — Reconciliation report

Emit a **Resume Reconciliation** before doing any work:

- Verdict: MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME
- State vs handoff: what matches and what changed
- Still-valid pickup instructions
- Now-invalid or changed steps, with the reason
- Blockers

See `.resume-from-handoff/reconciliation-checklist.md`.

Stop conditions (do NOT resume — surface and ask): missing branch/commits; conflicting
uncommitted changes; PR already merged/closed obsoleting the work; a "first command" that
would now be destructive or wrong.

## Phase 4 — Resume the work

Only after MATCH or MINOR DRIFT and after stating the plan:

1. If `scripts/handoff-loop.sh` exists, run it as the first resumed action when doing so will
   not clobber user-owned work. Compare its verdict with the handoff's cited log. A non-zero
   result pauses forward progress until the named gate is repaired; it does not retroactively
   make the read-only reconciliation dishonest.
2. Skip the handoff's "Do not redo" list.
3. Follow "Start here", adjusted for minor drift.
4. Run the "First command to run" or its corrected equivalent.
5. Respect repo gates: run `judge` before building anything new that was not already approved,
   and honour CLAUDE.md / AGENTS.md boundaries.

## Output

End with what was resumed, the first action taken, the next checkpoint, and:
`Resume complete (or paused). Next safe action: <one sentence>.`
