# SPM Command

`/spm` is the Senior Project Manager command for Pi-Dev-Ops. It converts a rough user
request into a decision-grade `spec.md` before implementation.

## Command chain

```text
/judge <idea>
/spm <task>
/goal <completion condition>
/session-handoff
/resume-from-handoff
```

## Purpose

The command prevents vague, bloated, unsupported builds. It forces:

- Project inspection
- Specialist review
- Judge-style challenge
- Existing capability review
- UX review
- Security review
- Verification planning
- Stress testing
- Acceptance criteria
- Goal-ready completion condition

## Where it lives

| CLI | Repo file | Invocation |
|---|---|---|
| Claude Code | `.claude/skills/spm/SKILL.md` | `/spm <task>` |
| Codex CLI | `.agents/skills/spm/SKILL.md` | `$spm <task>` or `/skills` → select `spm` |
| TAO router | `skills/spm/SKILL.md` | intent-routable via `skills_for_intent("spm")` |
| Shared docs | `.spm/*` | Referenced by both |

## Default behaviour

Read-only. It does not implement code unless the user separately approves implementation.

## Claude Code

```text
/spm Build a new session dashboard
```

## Codex

```text
$spm Build a new session dashboard
```

or run `/skills` then select `spm`.

## Relationship to other commands

```text
/judge = Should we do this?
/spm = What exactly should be built?
/goal = Build until done.
/session-handoff = Record where we are.
/resume-from-handoff = Restart cleanly.
```

## Shared reference files

- [`spec-template.md`](spec-template.md) — the SPM Spec structure.
- [`agent-board.md`](agent-board.md) — the specialist review lenses.
- [`goal-template.md`](goal-template.md) — how to write the follow-on `/goal`.
- [`verification-template.md`](verification-template.md) — proof to define before building.
