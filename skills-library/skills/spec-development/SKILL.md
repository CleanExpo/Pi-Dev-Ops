---
name: spec-development
description: Use when starting ANY non-trivial development work — a feature, integration, refactor, or bugfix bigger than one file — BEFORE writing code. Runs the spec-driven pipeline (constitution → specify → clarify → judge → plan → tasks → analyze → implement → converge) so intent is locked before implementation. Also invoked by /sdd, "spec this", "spec-driven", "write the spec first", or when a task arrives as a vague goal rather than a defined change.
argument-hint: "<the feature/change to develop, or a path to an existing spec dir to resume>"
---

# spec-development — the spec IS the source of truth

Spec-driven development for every build: capture the **what/why** as an executable
spec, refine it until unambiguous, gate it, then derive plan → tasks → code from it.
Adapted from GitHub spec-kit; integrated with this Library's existing skills instead
of duplicating them. Code that disagrees with the spec is a bug in one of them —
decide which, then fix that one.

## Phase map (run in order; resume at the first artifact that doesn't exist)

Artifacts live in `docs/specs/<YYYY-MM-DD>-<slug>/` in the target repo (create it;
respect an existing repo convention if `specs/` or `.specify/` already exists there).

### 0. Constitution — govern before you specify
The constitution is the repo's standing law: `CLAUDE.md` + `AGENTS.md` + `DESIGN.md`
+ `.claude/rules/*` where they exist. Read them FIRST; every later phase must obey
them. Only if a repo has none, create `docs/CONSTITUTION.md` from
[`references/constitution-template.md`](references/constitution-template.md).
Never fork a second constitution beside an existing CLAUDE.md.
- **Done when:** you can state the 3-5 constraints that will most shape this feature.

### 1. Specify — the what and why, zero tech stack
Write `spec.md` from [`references/spec-template.md`](references/spec-template.md):
user stories, functional requirements, Given/When/Then acceptance criteria,
non-goals, evidence tags. No frameworks, no schema, no file paths — that is plan
material. For decision-grade depth on a big feature, delegate this phase to `/spm`
and save its output as `spec.md`; for a small change fill the template directly.
Every factual claim about the existing system carries an evidence tag:
`[VERIFIED file:line]`, `[INFERENCE]`, or `[UNCONFIRMED]`.
- **Done when:** spec.md has ≥1 user story per affected persona, testable acceptance
  criteria, explicit non-goals, and zero implementation detail.

### 2. Clarify — kill ambiguity before it compounds
Interrogate the spec: walk every requirement asking "could two competent engineers
build different things from this line?" Record each resolution in a
`## Clarifications` section (question → answer → date). For high-stakes or fuzzy
scope, run `/grill-me` on the spec and fold its resolutions in. Ask the human only
questions that change the build; batch them in one round.
- **Done when:** no `[UNCONFIRMED]` tag remains on a load-bearing requirement and
  every open question has an answer or an explicit deferral in Clarifications.

### 3. Judge gate — challenge before you plan
Run `/judge` against spec.md (devil's advocate, existing-capability overlap,
return-on-effort /100). Record verdict + score at the top of spec.md.
Score <70 → reduce scope and re-run once; still <70 → stop, report to the human.
- **Done when:** spec.md carries a judge verdict ≥70 (or the human overrode it, noted).

### 4. Plan — the how, derived from the spec
Write `plan.md` from [`references/plan-template.md`](references/plan-template.md):
tech choices + rationale (cite the constitution when it decides), architecture
touch-points, data-model deltas, API contracts, migration/rollout strategy, risks.
Read the code you're about to modify — every touched file listed with `[VERIFIED]`.
Reject over-engineering: anything the spec doesn't require gets cut here.
- **Done when:** every requirement in spec.md maps to a plan section, and every plan
  section maps back to a requirement (no orphan engineering).

### 5. Tasks — dependency-ordered, test-first, parallel-marked
Write `tasks.md` from [`references/tasks-template.md`](references/tasks-template.md):
small tasks (≤ half a day each), ordered by dependency, test task BEFORE its
implementation task, `[P]` on tasks safe to run in parallel (different files, no
shared state), exact file paths, a checkpoint (runnable verification) after each
user-story group.
- **Done when:** tasks cover 100% of plan.md, each has files + a verify command, and
  the first checkpoint is reachable without finishing the whole list.

### 6. Analyze — cross-artifact consistency (cheap, catches drift)
Diff the three artifacts against each other: requirement with no task? task with no
requirement? plan section contradicting a clarification? acceptance criterion no
checkpoint verifies? List findings in `tasks.md ## Coverage`; fix before building.
- **Done when:** the coverage table shows every acceptance criterion → verifying task.

### 7. Implement — tasks in order, oracle-verified
Execute tasks.md top to bottom on a feature branch (TDD where the repo mandates it —
constitution rules win). Run each task's verify command; run the checkpoint at each
group boundary. Big builds: hand tasks.md to `/execute-goal` or subagents (wrap
sub-Fable dispatches with `/nexus`), one task-group per agent, `[P]` groups
concurrently. A task is done when its verify command passes — not before. Never mark
the spec's acceptance criteria met without running them.
- **Done when:** all checkpoints green, full repo gates green (type-check, tests,
  lint), PR opened referencing the spec dir. Do not merge without the human.

### 8. Converge — brownfield truth-sync (also entry point for drifted repos)
After implementation (or when adopting a spec onto existing code): audit code vs
spec/plan/tasks; every gap becomes either a new task appended to tasks.md or a spec
amendment (with a Clarifications entry saying why intent changed). Keep artifacts
alive: behaviour change → spec change, same PR.
- **Done when:** zero known code↔spec disagreements, or each is a filed task.

## Rules that override convenience
- Phases are ordered; skipping one requires the human's explicit say-so, recorded in
  the spec. A bugfix may collapse 1-6 into a single short spec.md — but it exists.
- The spec never contains implementation; the plan never invents requirements.
- Evidence tags are mandatory in spec.md and plan.md ([[fabel-build-method]] posture:
  a claim without evidence is `[UNCONFIRMED]`, and load-bearing `[UNCONFIRMED]` blocks
  phase 3).
- Artifact files are committed with the code they govern — same repo, same PR.

## Companions (delegate, don't duplicate)
`/spm` (decision-grade specify), `/grill-me` (clarify), `/judge` (gate),
`/execute-goal` (implement), `/nexus` (sub-model dispatch), `superpowers:writing-plans`
and `superpowers:test-driven-development` (implementation discipline),
`pi-dev-linear-contract` (if tasks flow to Linear: one issue per task-group, existing
markers only).
