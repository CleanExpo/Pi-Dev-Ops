# Why Pi-CEO Keeps Saying "Done" When It Isn't

**A diagnostic deep-dive into the autonomous research-and-build loop**

Date: 2026-06-07
Scope: Pi-Dev-Ops orchestration repo (the engine), designed for registry-wide application across all portfolio projects
Author: prepared for Phill McGurk

---

## How to read this document

Every claim about your code below is backed by a real `file:line` reference so you can verify it yourself. Nothing here is inferred from documentation alone — it was read from the actual source in your `Pi-CEO` working folder. The evidence index at the end lists every reference in one place.

The investigation covered the parts of the system that decide *what to build* and *when it is finished*: the brief decomposer, the plan-discovery scorer, the judge that terminates the loop, the gap detector, the project registry, and the PM scoper.

---

## Executive summary — the one missing element

Your system has no model of what "complete" means for a project. It only knows what "complete" means for the **brief you handed it**.

Every decision point in the loop is *brief-relative* or *ticket-relative*. The decomposer splits your brief. The plan scorer ranks plans against your brief. The judge declares `GOAL_MET` when the handed-in goal's tests pass. None of them ever consult an independent, authoritative statement of what the finished project must contain. So when your brief under-specifies — and every brief under-specifies — the missing piece is never turned into a task, never worked, never tested, and never looked for by the judge.

The result is exactly your symptom: **the system truthfully reports "done" on the scope it was given, you discover a missing piece, it apologises, and the cycle repeats.** It isn't lying and it isn't broken. It is faithfully completing an incomplete instruction set, because nothing in the architecture computes the *complete* instruction set.

The missing element, stated precisely:

> A machine-checkable **Definition of Done per project** (a requirements / capability spec), plus a **coverage reconciler** that diffs that spec against the real codebase and emits the missing work as tasks — and a judge whose terminal gate is *spec coverage*, not *per-task goal*.

The rest of this document proves the gap, shows the four specific leak points, and lays out a prioritized way to close it across the whole portfolio.

---

## Part 1 — How the loop actually works today

The autonomous build path is a clean `plan → work → judge → repeat` loop. Walking it in order:

**Step 1 — A brief is decomposed into tasks.**
`app/server/orchestrator.py:60` — `_decompose_brief(brief, n_workers, repo_url, workspace)`. The prompt instructs the model to "Split the following brief into between 3 and 8 sub-tasks … that together implement the full brief." The operative assumption is in that last phrase: the brief is treated as the *full* statement of work. The function's only input describing *what to build* is `brief`. There is no second input representing the project's intended end-state.

The fallback is telling. If decomposition fails, `app/server/orchestrator.py` (end of `_decompose_brief`) returns `[brief] * n_workers` — literally N copies of the same brief. Scope can only ever be as complete as the brief; the system has no other source to widen it from.

**Step 2 — Plans are generated and scored.**
`app/server/agents/plan_discovery.py:138` — `_score_plan(brief, plan)` scores a plan variant 0–10. The prompt is formatted from `brief[:800]` and `plan[:1200]` only. `discover_best_plan` (`plan_discovery.py:286`) generates several variants and keeps the highest-scoring one. This optimises *plan quality relative to the brief*. If the brief omits a requirement, the best of N plans still omits it — the scorer has no way to know the requirement exists.

**Step 3 — The judge decides "done."**
`app/server/tao_judge.py` — `judge(goal, workspace, state, …)` returns a `JudgeVerdict(done, reason, score, next_action_hint)`. The prompt (`_build_prompt`, `tao_judge.py:67`) scores whether "the worker has met the goal," using only `goal`, `last_test_output`, `last_diff`, and `notes`. The decisive rule is explicit: `done=true ONLY when reason='GOAL_MET' and tests pass.` The verdict is goal-versus-state. The "goal" is the task brief from Step 1 — i.e. a slice of the original, possibly incomplete, brief.

**Step 4 — The loop terminates on that verdict.**
`app/server/tao_loop.py` — `run_until_done(...)` iterates one worker step at a time and stops when the judge says `GOAL_MET` (or a kill-switch axis trips: `MAX_ITERS`, `MAX_COST`, `HARD_STOP`). Termination reason `GOAL_MET` means "the goal we were given is satisfied" — never "the project is whole."

Each step is individually sound. The flaw is at the seams: scope enters once, as a human brief, and is never reconciled against an independent definition of completeness.

---

## Part 2 — The four leak points

Each of these is a place where missing scope can pass through undetected.

**Leak 1 — The decomposer trusts the brief as total scope.**
`orchestrator.py:60`. "…sub-tasks that together implement the full brief." There is no requirements input, so the union of sub-tasks can never exceed the brief. *Anything you didn't say is structurally invisible.*

**Leak 2 — The plan scorer optimises the wrong quantity.**
`plan_discovery.py:138`. It measures *how good a plan is for a brief*, not *how much of the project a plan covers*. Picking the best of several incomplete plans yields a polished but still-incomplete plan, with a high score that reads as confidence.

**Leak 3 — The judge has no project-level definition of done.**
`tao_judge.py:67`. `done=true` requires `GOAL_MET` + passing tests. Both are evaluated against the handed-in goal. A narrowly-scoped goal with green tests produces a fully confident "done" — the most direct generator of your symptom.

**Leak 4 — Gap detection only finds gaps a human already wrote down.**
`swarm/gap_detector.py:1` and its `GAP_WIKI_PAGES` list (`gap_detector.py:24`) scan exactly two hardcoded wiki pages (`tech-drops-q2-2026.md`, `operational-priorities-q2-2026.md`) for `## Action queue` tables and file up to `GAP_TICKETS_PER_RUN = 3` Linear tickets from rows a person authored. This is a transcription mechanism, not a discovery mechanism. It cannot derive a missing requirement from a target end-state; it can only re-file gaps you already enumerated by hand.

Net effect: there is no path anywhere in the system that answers the question *"Given what this project is supposed to be, what is still missing?"* That question is never asked, so it is never answered, so you end up asking it manually — every time.

---

## Part 3 — The registry confirms it

The portfolio registry is `.harness/projects.json` — 11 projects. Each entry carries: `id`, `repo`, `stack`, `deployments`, `linear_project_id`, `linear_team_id`, `scan_priority`, `scan_schedule`, and (for 7 of 11) a `business_charter` path.

What it records is **where each project lives and how to route findings** — repo, stack, deployment URLs, Linear IDs. What it does *not* record is **what each project must contain to be considered complete**. There is no `required_capabilities`, no acceptance criteria, no definition-of-done field anywhere in the schema. A repo-wide search for machine-readable completeness specs (`definition.of.done`, `required_capabilities`, `spec_coverage`, `acceptance.criteria` as a checkable file) returns nothing in the live tree.

The closest existing artifact is `business_charter` (e.g. `.harness/business-charters/restoreassist-charter.md`, `.harness/business-charters/PI-CEO-STANDARD.md`) — but these are **prose narratives**, not checkable requirements. A human can read one and judge completeness; the loop cannot, because there is no parser turning charter prose into pass/fail checks the judge can evaluate.

So the registry — the one natural home for a portfolio-wide Definition of Done — currently has a hole exactly where that definition belongs.

---

## Part 4 — Why your existing guardrails don't catch this

You have already built genuinely strong honesty machinery. It's worth being clear about *why it's necessary but not sufficient*, so you don't conclude the fix is "more of the same."

- **The "Manual verification" PR gate** (your `CLAUDE.md` honesty contract) proves a *change* works — endpoint returns 200, tests green, feature reachable. It verifies the task that was done. It is structurally incapable of verifying a task that was *never created*. Absence of a requirement is invisible to a gate that inspects present changes.

- **The judge** (`tao_judge.py`) is the right primitive aimed at the wrong target. It's a clean single-scalar termination gate — but it terminates on per-goal satisfaction, so it inherits whatever scope error the brief introduced upstream.

- **The PM scoper** (`swarm/pm_scoper.py`) *does* generate acceptance criteria — `_run_grounded_research` (`pm_scoper.py:183`) produces "3–5 acceptance criteria" per ambiguous ticket. But it scopes **tickets that already exist**; it sharpens known work. It never asks whether a ticket *should* exist. It's downstream of the gap, not a fix for it.

- **The gap detector** (`gap_detector.py`) transcribes human-authored action queues, as shown in Leak 4.

Every one of these operates *inside* a scope that a human defined. None of them can widen that scope from an authoritative model of the finished product, because that model doesn't exist yet. That is the single thing to add — not another verifier of work-as-given.

---

## Part 5 — The missing architecture

Three linked components, designed to live in the registry so they apply to all 11 projects uniformly.

**Component A — A Definition of Done per project (machine-checkable).**
A spec, stored alongside or referenced from `.harness/projects.json`, expressing the intended end-state as *checkable* requirements rather than prose. Each requirement should be verifiable by a probe the system can actually run, for example:

- *Capabilities*: "client portal supports password reset" → an integration test or route-existence check.
- *Surfaces*: required API routes / pages exist and return non-error.
- *Schema*: required tables/columns exist (you already have Supabase introspection via MCP).
- *Integrations*: required external wiring present (Stripe webhook registered, Linear project mapped, etc.).
- *Tests*: named test files/suites exist and pass.

The point is that each requirement carries a *probe*, so "is this done?" becomes a function the machine can evaluate, not a judgement a human must make. Your `business_charter` files are the natural prose source to *derive* the first draft of these specs from.

**Component B — A coverage reconciler.**
A periodic job (sibling to `gap_detector`, but driven by the spec instead of wiki pages) that, per project:

1. Loads the Definition of Done.
2. Runs each requirement's probe against the real codebase / deployment.
3. Computes `spec − reality` — the set of unmet requirements.
4. Emits each unmet requirement as a Linear ticket in the correct project (you already have the routing table in `projects.json` and the Linear MCP tools).

This is the piece that makes the system *self-extending*: it generates the steps, stages and builds itself by diffing intent against reality, which is precisely the behaviour you described wanting ("identify the required steps, stages, builds, engineering required for all my projects").

**Component C — Re-point the judge's terminal gate at coverage.**
Change the loop's stopping condition from per-task `GOAL_MET` to *project DoD coverage met*. Concretely: `tao_loop.run_until_done` keeps using `tao_judge` for per-iteration progress, but the **loop only declares the project done when the coverage reconciler reports 100% (or an agreed threshold) of the Definition of Done satisfied**. A green per-task judge becomes a *necessary* condition, never a *sufficient* one.

How the three change the flow:

```
TODAY:   brief ─▶ decompose ─▶ work ─▶ judge(goal) ─▶ "done"  (scope = brief)

PROPOSED: DoD(project) ─┐
          brief ────────┼▶ decompose ─▶ work ─▶ judge(task)
                        │                          │
                        └───── coverage reconciler ◀┘
                                     │
                          spec − reality = new tasks
                                     │
                        done ONLY when coverage ≥ threshold
```

The brief becomes a *seed*, not the *boundary*. The boundary is the Definition of Done.

---

## Part 6 — Prioritized roadmap

Ordered so each phase delivers verifiable value and de-risks the next. This targets the engine (Pi-Dev-Ops) first because every other project inherits the capability once it exists there.

**Phase 0 — Make the gap visible (days).**
Add one project's Definition of Done as a machine-readable file and write a read-only coverage report (no ticket-filing yet). Pick one project with a clear end-state. Goal: prove the spec format and probes work, and *see* the delta the system is currently blind to. Success metric: the report surfaces at least one real missing item you'd otherwise have found manually.

**Phase 1 — Close the loop on one project (1–2 weeks).**
Wire the coverage reconciler to file Linear tickets for unmet requirements (reuse `projects.json` routing + Linear MCP). Keep it behind a dry-run flag first, exactly like the swarm's shadow mode. Success metric: tickets generated for real gaps, zero duplicates against existing tickets (mirror `gap_detector`'s dedupe).

**Phase 2 — Re-point the judge (1 week).**
Make `tao_loop` consult coverage as the terminal gate. Per-task judge stays as the inner progress signal. Success metric: a deliberately under-scoped brief no longer terminates as "done" — the loop continues and generates the missing tasks itself.

**Phase 3 — Generalise across the registry (2–3 weeks).**
Add Definition-of-Done specs for all 11 projects, seeded from the `business_charter` prose where it exists. Run the reconciler portfolio-wide on a schedule. Success metric: a single daily report shows, per project, percentage of Definition of Done met and the outstanding list.

**Phase 4 — Self-authoring specs (ongoing).**
Let the system *propose* additions to a project's Definition of Done from research (it already has deep-research and web tooling), with human approval — so the definition of "complete" itself improves over time instead of going stale. Keep approval human: this is the one place where letting the machine widen its own success criteria unsupervised would re-introduce the exact problem.

---

## A note on framing

You said the system "should know" how to identify required steps and stages on its own. The honest position is that an LLM-driven loop *cannot* reliably do that from a brief alone — not because your build is deficient, but because "what's missing" is unknowable without an explicit statement of "what complete looks like." Humans have the same limitation; we just carry an implicit spec in our heads and notice the gap after the fact. Your frustration is the system lacking that implicit spec. The fix is to make it explicit and machine-checkable. Once the Definition of Done exists, the "find the missing somethings" behaviour you want falls out almost for free — it becomes a set difference, run on a schedule.

---

## Evidence index

| Claim | Reference |
|---|---|
| Brief decomposer; "implement the full brief"; `[brief]*n` fallback | `app/server/orchestrator.py:60` (`_decompose_brief`), call site `:288` |
| Plan variants scored against brief only | `app/server/agents/plan_discovery.py:138` (`_score_plan`), `:286` (`discover_best_plan`) |
| Judge prompt uses only goal/test/diff/notes; `done` requires `GOAL_MET`+tests | `app/server/tao_judge.py:67` (`_build_prompt`), `judge()` |
| Loop terminates on judge verdict / kill-switch axes | `app/server/tao_loop.py` (`run_until_done`) |
| Gap detector scans 2 hardcoded wiki pages, files ≤3 tickets/run | `swarm/gap_detector.py:1`, `:24` (`GAP_WIKI_PAGES`), `GAP_TICKETS_PER_RUN` |
| Registry fields — no definition-of-done / required-capabilities | `.harness/projects.json` (11 projects; fields: id, repo, stack, deployments, linear ids, scan_priority, business_charter×7) |
| Business charters are prose, not checkable | `.harness/business-charters/PI-CEO-STANDARD.md`, `restoreassist-charter.md` |
| PM scoper generates acceptance criteria for *existing* tickets only | `swarm/pm_scoper.py:183` (`_run_grounded_research`), `:202` |
| Honesty / manual-verification contract | `CLAUDE.md` (Senior-Agent Honesty Contract section) |
