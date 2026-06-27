# Session Handoff Verification Checklist

Use this checklist before trusting a handoff.

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
