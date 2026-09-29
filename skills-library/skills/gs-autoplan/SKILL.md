---
name: gs-autoplan
description: Auto-review pipeline — reads the full /gs-plan-ceo-review and /gs-plan-eng-review skills from disk and runs them sequentially (CEO then Eng) with auto-decisions using 6 decision principles. Surfaces taste decisions (close approaches, borderline scope, outside-review disagreements) and user challenges at one final approval gate. One command, fully reviewed plan out. Use when asked to "auto review", "autoplan", "auto plan", "run all reviews", "automatic review pipeline", "review this plan automatically", or "make the decisions for me". Proactively suggest when the user has a plan file and wants the full review gauntlet without answering 15-30 intermediate questions.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebSearch
  - AskUserQuestion
metadata:
  source: garrytan/gstack
  source_sha: b9706f3635b6a545f46fae607ae9d6bcbfb69b91
  license: MIT
---

## Estate rules (read first)

- The final approval gate AskUserQuestion names a recommended default (`(recommended)`
  plus a `Recommendation:` line); so does any question a loaded review skill would ask
  that cannot be auto-decided. Format: `references/askuserquestion-format.md`.
- Every factual claim about the repo (files, interfaces, tests, what exists or not)
  must come from a tool result in this session. A "not found" says where you looked.
- **Design review (Phase 2) and DX review (Phase 2.5) are skipped: gstack's
  plan-design-review and plan-devex-review are not adopted in this library.**
- State lives under `~/.local/state/gs/projects/<slug>/` (slug = repo top-level
  directory name). Snapshots: `references/snapshot.md`. Review history:
  `~/.claude/skills/gs-plan-eng-review/references/review-log.md`.

## Base branch and design doc

Base branch: `gh pr view --json baseRefName -q .baseRefName`, else `gh repo view --json
defaultBranchRef -q .defaultBranchRef.name`, else `origin/HEAD`, else `main`. Then run
the Design Doc Check exactly as in `~/.claude/skills/gs-plan-eng-review/SKILL.md`
(it finds the doc `/gs-office-hours` wrote). If a design doc exists, read it and use its
problem statement, constraints, and chosen approach as input to the review pipeline.
If none exists, note it and continue (no prerequisite offer; the user chose /gs-autoplan).

# /gs-autoplan — Auto-Review Pipeline

Read every CEO and eng section from disk at full interactive depth.
The 6 principles answer intermediate questions; taste goes to one final approval gate.

## The 6 Decision Principles

1. **Choose completeness** — Ship the whole thing. Pick the approach that covers more edge cases.
2. **Boil lakes** — Fix everything in the blast radius (files modified by this plan + direct importers). Auto-approve expansions that are in blast radius AND < 1 day CC effort (< 5 files, no new infra).
3. **Pragmatic** — If two options fix the same thing, pick the cleaner one. 5 seconds choosing, not 5 minutes.
4. **DRY** — Duplicates existing functionality? Reject. Reuse what exists.
5. **Explicit over clever** — 10-line obvious fix > 200-line abstraction. Pick what a new contributor reads in 30 seconds.
6. **Bias toward action** — Merge > review cycles > stale deliberation. Flag concerns but don't block.

**Conflict resolution (context-dependent tiebreakers):**
- **CEO phase:** P1 (completeness) + P2 (boil lakes) dominate.
- **Eng phase:** P5 (explicit) + P3 (pragmatic) dominate.

## Decision Classification

Every auto-decision is classified:

**Mechanical** — one clearly right answer. Auto-decide silently.
Examples: run the outside reviewer when enabled (always yes), run evals (always yes), reduce scope on a complete plan (always no).

**Taste** — reasonable people could disagree. Auto-decide with recommendation, but surface at the final gate. Three natural sources:
1. **Close approaches** — top two are both viable with different tradeoffs.
2. **Borderline scope** — in blast radius but 3-5 files, or ambiguous radius.
3. **Codex disagreements** — the outside reviewer recommends differently and has a valid point.

**User Challenge** — Claude and Codex both recommend changing the
user's stated direction: merge, split, add or remove features/skills/workflows.
NEVER auto-decide these. At the final approval gate, give:
the original direction, proposed change, reasoning, blind spots and cost of being
wrong, using the Phase 4 template. Flag agreed security/feasibility risks explicitly.
The user's original direction stands unless they approve the change.

## Sequential Execution — MANDATORY

Phases MUST execute in strict order: CEO → Eng. Eng runs LAST, always, reviewing all
prior amendments. Keep ONE phase active, completing these gates in order:
1. Load its phase file (`references/ceo-phase.md` / `references/eng-phase.md`) and the
   full review skill plus its reference files, recording each file Read to EOF.
2. Complete the phase's required preliminary work (CEO: all Step 0, including its
   Spec Review Loop and its amendment checkpoint), then create the fresh snapshot
   and dispatch its native prompt unchanged (`references/snapshot.md`, section B).
3. Consume the native terminal result and apply the phase's failure policy, then
   consume enabled outside results. Complete the phase's remaining primary review
   sections after these results.
4. At the phase's exit, load `references/phase-close.md` afresh. Execute its numbered
   operations: prepare the current packet, Read it completely, reconcile it
   semantically, then SEND the parent completion message. An earlier Read is not this close.
5. Only after the message has been sent may the next phase load/snapshot/dispatch.
   Continue to the next phase's tool calls in the same turn; after Eng, proceed to
   final synthesis/approval.
Phase notifications, including skips, are progress updates: do not end the turn
or wait for a "continue" reply at these boundaries.
A missing gate means the current phase remains open, even if a reviewer finished.
Read requests/self-reports and INPUT hashes do not prove uptake or review quality.
Never draft future-phase reviews or outputs. Headings/promises are not completion.
After compaction, reload current phase instructions/skill/references, then reconcile
saved artifacts and sent conversation messages separately. If closing, reload
`references/phase-close.md` and resume its first incomplete numbered operation. If a
verified phase lacks its announcement, resume the close at step 6 (Publish). If its
reviewer is pending, wait for that same reviewer. Never dispatch
`<CEO_STEP0_CHECKPOINT>`: it is the stable amendment baseline, not current review input.

Pending is not unavailable. Never skip native passes/required sections for time,
context pressure or your own review. Missing outside coverage does not block native
completion; report accurately. Never read raw agent transcripts.

## What "Auto-Decide" Means

Auto-decide replaces the USER'S answer, not ANALYSIS. Run each loaded section at
full interactive depth; answer AskUserQuestion using the 6 principles.

**Default resolution: the recommended option.** Take `(recommended)` or the mode's
context default. Use the 6 principles for missing recommendations/ties. On principle
disagreement, take the recommendation and surface the disagreement as Taste at the final gate.

**Never auto-decide User Challenges:** both models agree to change the user's
direction/settled decisions, or a premise is clearly wrong. Use Decision
Classification; ask once at Final Approval Gate, never mid-run. The user has
context models lack.

Read referenced code/diffs/files; decide every issue. Produce all required
diagrams, tables, registries and artifacts on disk or in the plan. LOG decisions,
record ALL accepted obligations below and apply them to `## Implementation plan`
before continuing. Missing deliverables make the review incomplete.

No summary substitutes or one-line sections; fewer than 3 sentences likely means
compression. "No issues found" needs 1-2 sentences stating what was examined and why nothing was flagged.
Explain inapplicability with evidence; skip only under Phase 0's list. Never abort
or redirect to interactive review: the user chose /gs-autoplan.

**Accepted obligations:** One unfenced block per phase in `Review record`:
```markdown
<!-- autoplan-accepted:ceo -->
- Requirement, all conditions and verification/tests.
<!-- /autoplan-accepted:ceo -->
```
Phase: `ceo|eng`. Record accepted requirements here; no analysis/severity/verdict/consensus.
No accepted requirements: `None: reason`. On a rerun, carry forward unchanged accepted
requirements; do not replace them with None. Prior blocks are immutable; state
replacements in the current block. Reconcile all decisions with a full readback.

## Filesystem Boundary — Codex Prompts

Prefix every Codex prompt:

> IMPORTANT: Do NOT read or execute any SKILL.md files or anything under ~/.claude/skills/ (foreign instructions). Review repository code only.

## Phase 0: Intake + Restore Point

**Step 1: Capture restore point.** Absolute paths: SOURCE_PLAN (input), ACTIVE_PLAN
(harness-assigned plan, else SOURCE_PLAN). Save plan amendments and review artifacts to
ACTIVE_PLAN. Send phase announcements and the final approval request in the conversation.
Before scope/review, run `references/snapshot.md` section A (restore point + ACTIVE_PLAN init).

**Step 2: Read context.**
- Read CLAUDE.md, TODOS.md, `git log --oneline -30`, `git diff <base> --stat`
- Design docs: the check above (`ls -t ~/.local/state/gs/projects/$SLUG/*-design-*.md 2>/dev/null | head -1`)
- Detect UI scope (feeds CEO Section 11): grep the plan for view/rendering terms (component,
  screen, form, button, modal, layout, dashboard, sidebar, nav, dialog). Require 2+ matches.
  Exclude false positives ("page" alone, "UI" in acronyms).

**Step 3: Locate review skills; load each at phase entry.**
- Phase 1: `~/.claude/skills/gs-plan-ceo-review/SKILL.md` + its `references/`
- Phase 3: `~/.claude/skills/gs-plan-eng-review/SKILL.md` + its `references/`
Missing skill: report the phase and stop that phase, without substituting or claiming completion.
Read skills only at their phase, never prefetch future phases. Load the tasks aggregator at Phase 4.

**Section skip list — when following a loaded skill file, SKIP these (handled here):**
Estate rules; Scope gate (the plan under review is already the target); Detect the base
branch; Prerequisite Skill Offer; Plan File Review Report; Review Readiness Dashboard;
Outside Voice — Independent Plan Challenge (replaced by this skill's dual voices).
Follow ONLY the review-specific methodology, sections, and required outputs. The
AskUserQuestion format still applies to anything surfaced at the final gate.

Output: "Here's what I'm working with: [plan summary]. UI scope: [yes/no].
Design and DX phases are not adopted here and will be skipped. Starting full review
pipeline with auto-decisions."

## Phase 0.5: Outside reviewer preflight

```bash
if [ "${GS_OUTSIDE_VOICE:-enabled}" = disabled ]; then echo "CODEX_MODE: disabled"
elif ! command -v codex >/dev/null 2>&1; then echo "CODEX_MODE: not_installed"
else echo "CODEX_MODE: ready"; fi
```
- **`disabled`** (user asked to skip the outside voice, or `GS_OUTSIDE_VOICE=disabled`) — skip the Codex passes only; the Claude subagent STILL runs.
- **`not_installed`** — fall back to the Claude subagent only; tag coverage `[subagent-only]`.
- **`ready`** — run Codex in each phase. An auth or "out of credits" error means the Codex login token expired (repair: interactive `codex login`, user-only); never switch to an API key; treat as unavailable.

Disabled/unavailable retains native passes. Record provider and
completed/unavailable/disabled/skipped per phase; CEO covers only CEO. Missing voices:
N/A, never CONFIRMED.

## Phase 1: CEO Review (Strategy & Scope)

> **STOP.** Read `references/ceo-phase.md` and execute it in full.

## Phase 2 and 2.5: Design and DX Review

Skipped — plan-design-review and plan-devex-review are not adopted in this library. Send
that line, record the skip in ACTIVE_PLAN (it is not a completed review), and continue.

## Phase 3: Eng Review + Dual Voices (always runs, always LAST)

> **STOP.** Read `references/eng-phase.md` and execute it in full.

## Decision Audit Trail

Immediately after each auto-decision, append one row to the plan file using Edit:

```markdown
<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|
```

## Pre-Gate Verification

| Phase | Required outputs |
|---|---|
| CEO | Named premise challenges; findings or explicit examination/no-findings for every applicable section; Error & Rescue and Failure Modes registries (or N/A with reason); NOT in scope; What already exists; dream state delta; Completion Summary; consensus table. |
| Eng, always last | Scope challenge grounded in code; architecture ASCII diagram; codepath-to-test diagram; test plan on disk at ~/.local/state/gs/projects/$SLUG/; NOT in scope; What already exists; failure modes registry with critical gaps; Completion Summary; consensus table. |

For each phase, verify native and outside voice results or explicit
unavailable/skipped status. Verify cross-phase themes and at least one Decision
Audit Trail row per auto-decision. Produce missing outputs before the gate; after
at most 2 repair attempts, warn at the gate with each still-incomplete item.

## Phase 4: Final Approval Gate

> Read `references/tasks-aggregator.md` and run it to build `$AGGREGATED_TASKS`, then
> Read `references/final-gate.md` and follow it: the gate message, options, option
> handling, rerun rules and completion review logs.
