# Session Handoff Command

`session-handoff` is the durable end-of-session command for Pi-Dev-Ops. It is the
companion to `judge`: where `/judge` asks *"should we build this?"*, `/session-handoff`
answers *"what exactly happened, what shipped, what still works, what is unresolved, and
where does the next agent pick up?"*

It captures:

1. Summary of what was done
2. Where it started
3. Decisions locked + what shipped
4. Key files
5. Running state
6. Verification — how to confirm things still work
7. Deferred + open questions
8. Pick up here
9. Risk notes
10. Handoff quality check

## Where it lives

| CLI | Repo file | Invocation |
|---|---|---|
| Claude Code | `.claude/skills/session-handoff/SKILL.md` | `/session-handoff` |
| Codex CLI | `.agents/skills/session-handoff/SKILL.md` | `$session-handoff` or `/skills` → select `session-handoff` |
| TAO router | `skills/session-handoff/SKILL.md` | intent-routable via `skills_for_intent("handoff")` |
| Shared docs | `.session-handoff/*` | Referenced by both |

## Claude Code

```text
/session-handoff
/session-handoff PR #123
/session-handoff RA-6795 capture-photo hardening
```

## Codex

```text
$session-handoff
$session-handoff PR #123
```

Or run `/skills` and select `session-handoff`.

## Shared reference files

- [`report-template.md`](report-template.md) — the exact handoff structure.
- [`verification-checklist.md`](verification-checklist.md) — what must be present, what must not happen.

## Default behaviour

Read-only. The command must not edit, commit, push, deploy, migrate, or change external
systems unless the user separately asks after the handoff. `automation: manual` keeps it
explicit-invoke (it never auto-injects into generator prompts).
