# Tasks: <feature name>

> Derives from `plan.md`. Ordered by dependency. Test task precedes its implementation
> task. `[P]` = safe to parallelise (different files, no shared state). Each task ≤ half
> a day, names exact files, and ends with a runnable verify command.

## Group A — <user story / slice name>
- [ ] A1. <test task> — files: `…` — verify: `npx vitest run <file>`
- [ ] A2. <impl task, depends A1> — files: `…` — verify: `npx vitest run <file>`
- [ ] A3. [P] <independent task> — files: `…` — verify: `…`

**Checkpoint A:** <runnable end-to-end verification for this group — command or manual step>

## Group B — <next slice> (depends: Group A)
- [ ] B1. …

**Checkpoint B:** …

## Coverage (filled at phase 6 — Analyze)
| Acceptance criterion (spec) | Verifying task/checkpoint |
|---|---|
| AC1 | A2 + Checkpoint A |

Orphans found (requirement with no task, task with no requirement): none | <list + fix>

## Converge log (phase 8 — appended post-implementation)
| Date | Gap found (code vs spec) | Disposition (new task / spec amendment) |
|---|---|---|
