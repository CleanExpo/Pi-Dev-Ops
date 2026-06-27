# Resume From Handoff Command

`resume-from-handoff` is the read-side companion to `session-handoff`. Where
`/session-handoff` produces a durable record of where work stopped, `/resume-from-handoff`
reads that record, verifies the repo still matches it, reconciles any drift, and continues
the work from the documented pickup point — without re-deriving old context.

The trio:

- `/judge` — *should we build this?*
- `/session-handoff` — *what happened and where does the next agent pick up?*
- `/resume-from-handoff` — *given that handoff, verify reality and continue.*

## Where it lives

| CLI | Repo file | Invocation |
|---|---|---|
| Claude Code | `.claude/skills/resume-from-handoff/SKILL.md` | `/resume-from-handoff` |
| Codex CLI | `.agents/skills/resume-from-handoff/SKILL.md` | `$resume-from-handoff` or `/skills` → select `resume-from-handoff` |
| TAO router | `skills/resume-from-handoff/SKILL.md` | intent-routable via `skills_for_intent("resume")` |
| Shared docs | `.resume-from-handoff/*` | Referenced by both |

## Input

`/resume-from-handoff` takes the handoff to resume from as its argument:

- a path to a saved handoff file,
- pasted handoff text, or
- a branch / PR reference.

If no argument is given it looks for the most recent handoff under `.session-handoff/`
(e.g. a `handoffs/` directory) or in the current conversation context. If none is found it
asks for one and stops.

> Tip: `/session-handoff` is read-only and prints its handoff. To make resumption
> automatic, save the handoff output to a file (for example
> `.session-handoff/handoffs/<date>-<scope>.md`) and pass that path to
> `/resume-from-handoff`.

## Behaviour — verify before resuming

Phases 1–3 are **read-only**: load the handoff, verify the repo matches it, and report a
reconciliation verdict (MATCH / MINOR DRIFT / MATERIAL DRIFT / CANNOT RESUME). Only on
MATCH or MINOR DRIFT does Phase 4 resume the actual work — skipping the "do not redo"
list, following "start here", and running the documented first command. On material drift
or a missing branch/commit it stops and surfaces the problem instead of guessing.

See [`reconciliation-checklist.md`](reconciliation-checklist.md) for what must be checked
before resuming.

`automation: manual` keeps it explicit-invoke (it never auto-injects into generator
prompts).
