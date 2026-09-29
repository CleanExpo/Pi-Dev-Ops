# Goal Template

Use this after `/spm` produces an accepted spec.

```text
/goal Implement the accepted SPM spec for <task>. Completion condition: <files/behaviours exist>; <verification commands pass>; <acceptance criteria are satisfied>; no unrelated files are changed; no secrets are added; no destructive operations are performed; if blocked by missing credentials, external service access, or destructive migration approval, stop and produce /session-handoff instead.
```

A strong goal must include:

- One measurable end state
- Proof command or inspection method
- Files or behaviours that must exist
- Verification commands
- Constraints
- Stop condition
- Handoff condition

Bad goal:

```text
/goal Build the feature properly.
```

Good goal:

```text
/goal Implement the accepted SPM spec for the session dashboard. Completion condition: the dashboard shows active sessions, completed sessions, and failed sessions; empty/loading/error states exist; `cd dashboard && npx tsc --noEmit` passes; no unrelated files changed; stop and produce /session-handoff if blocked by missing API credentials.
```
