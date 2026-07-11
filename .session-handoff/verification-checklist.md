# Session Handoff Verification Checklist

Use this checklist before trusting a handoff.

## Phase 0 — Gate the tree green (run first)

`/session-handoff` runs `scripts/handoff-loop.sh` before writing the report, and
`/resume-from-handoff` re-runs it before resuming. The handoff is only "READY" when it
exits 0. Gate order: clean bloat → deps → generated-files-current → type → lint → tests →
production build → audits. A gate whose toolchain is absent is SKIPPED (with a reason), not
failed; a real failure ⇒ **BLOCKED** — name the gate, stop, fix, re-run. The healthcheck log
lands in `.handoff-logs/handoff-<ts>.log`; cite it in the handoff.

## Phase 0.5 — Definition of Done & ship classification (run before writing the report)

A green tree is not a finished session. Classify into exactly one state and record it in §1:

- **SHIPPED** — committed, pushed, PR open/merged on a green tip. Record the PR URL in §3.
- **READY-TO-SHIP** — complete + green, no PR yet. §8's first command is the exact
  `merge-gate`-guarded `gh pr create`; session-handoff does not open it.
- **WIP / BLOCKED** — a task unfinished, a gate red, or a surface not demonstrable. Handoff is
  **INCOMPLETE**; §7 lists what remains, §8 is the finish-then-ship path.

Definition-of-Done (every "no" forbids SHIPPED; answer from this-session tool results):

- [ ] Every task/goal the session set out to do is done or explicitly deferred with an owner.
- [ ] Tests actually ran green (Phase 0 exit 0) — not just types compiling; log path cited.
- [ ] `git status` clean and `git stash list` empty — nothing uncommitted belongs in the change.
- [ ] Work is PR'd, or carries the exact ready-to-open command (READY-TO-SHIP).
- [ ] Any user-visible change has a demonstrable outcome (RA-1109), not just HTTP 200 / green CI.

## Must be present

- Summary of what was done
- Starting point
- Locked decisions
- What shipped
- Key files
- Running state
- Verification commands
- Deferred work
- Open questions
- Exact pickup point

## Must not happen

- Do not claim code shipped if it was only drafted.
- Do not claim tests passed unless they were actually run.
- Do not claim a server/process is still running unless verified.
- Do not bury blockers inside general notes.
- Do not mix deferred work with completed work.
- Do not leave the next agent guessing where to resume.

## Minimum acceptable pickup instruction

The handoff must include:

```text
First command to run:
<exact command>
```
