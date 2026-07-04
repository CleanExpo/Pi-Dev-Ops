---
name: weekly-enhancement-loop
description: "Weekly cross-repo self-improvement loop. Every Monday 02:00 AEST it applies the 8-Claude-Loops method (INGEST / BUILD / COMPOUND + North Star) across every repo in .harness/projects.json, opening review PRs so all projects compound over time. API-mode Opus/Sonnet/Haiku ladder."
owner_role: "Senior PM"
status: "wave-6"
automation: scheduled
intents: improve-system, optimization, ecosystem-monitoring, compound-learning, weekly-enhancement
source: docs/sources/8-claude-loops-to-build-10x-faster.md
---

# Weekly Enhancement Loop

Automates the improve-system method from
`docs/sources/8-claude-loops-to-build-10x-faster.md` (Austin Marchese, "8 Claude
Loops to Build 10x Faster") as one scheduled cross-repo pass. The source buckets
loops into **INGEST → BUILD → COMPOUND**, plus a **North Star** compass. This
skill is the automation of loops 4, 5, 6, 7 and 8 run every Monday 02:00 AEST
against every repo in `.harness/projects.json`, so every project is enhanced on a
fixed cadence rather than only when someone opens a session.

Runner: `scripts/weekly_enhancement_loop.py`. Schedule:
`.github/workflows/weekly-enhancement-loop.yml` (always-on) and
`scripts/launchd/com.piceo.weekly-enhancement-loop.plist` (local Mac fallback).

## Skill-driven loop creation

The source's rule: every loop starts as a skill you run manually and confirm,
then you wrap it in a schedule. This file is that skill. Run it by hand once per
repo before trusting the cron:

```bash
python scripts/weekly_enhancement_loop.py --repo CleanExpo/RestoreAssist --dry-run
```

Only enable the schedule after a dry-run produces a sane review file.

## The loop (per repo)

For each repo in the registry the runner executes the improve-system loop:

1. **Ingest (loops 1–3).** Clone the repo into an isolated `/tmp` workspace
   (never the outer checkout), read the codebase, recent sessions, `WIKI.md`,
   and open Linear items. Surface recurring patterns and gaps — internal alpha,
   not a report. A **Haiku** monitor pass does the cheap scan/enumeration.

2. **Plan (loop 5 approval gate).** An **Opus** planner/orchestrator turns the
   findings into a bounded implementation plan (affected files, sequencing,
   risk, rollback). The plan is the critical-call checkpoint — if the direction
   is wrong here, every later step is wasted.

3. **Build + optimise (loops 4–5).** A **Sonnet** generator applies small,
   verifiable edits. Optimisation targets are objective and measurable (build
   time, bundle size, lint/type errors, dead code, dependency drift). Measure →
   change → re-measure until the metric moves or the iteration/cost cap trips.

4. **Review (loop 5).** A **Sonnet** evaluator reviews the diff for correctness,
   scope, security, and operability before anything leaves the sandbox.

5. **Three-bucket triage (loop 6).** Every proposed change is logged to
   `CHANGELOG` in the repo and bucketed:
   - **auto-approve** — low-risk (formatting, dead-code removal, obvious dep
     bumps, doc fixes): committed to the branch automatically.
   - **need-sign-off** — skill/config/structural/security-touching changes:
     written to the review file as a checkbox list; **never merged by the loop**.
   - **more-context** — the loop cannot decide alone: written to the same review
     file for the operator.

6. **North Star check (loop 8).** Before opening the PR, the Opus orchestrator
   checks the batch against the repo's charter/goals and drops anything that
   does not point at the actual North Star. Drift is surfaced, not shipped.

7. **Ecosystem log (loop 7).** Every run appends a structured result to
   `.harness/enhancement-loop/<date>.jsonl` (repo, models, metrics before/after,
   buckets, branch, PR, cost). This is the run-log that lets the loop monitor
   itself and lets tokens/cost be audited week over week.

## Hard boundaries (do not weaken)

- **Approval gate, not auto-merge.** The loop pushes an `enhance/weekly-<date>`
  branch and opens a PR per repo. It **never merges to `main`**. Monday-morning
  human review is the sign-off. This is loop 5's critical-call checkpoint.
- **Self-modification guard.** Enhancement of `CleanExpo/Pi-Dev-Ops` is allowed
  but the branch/PR must be reviewed by a human — the webhook autonomy poller
  already skips `pidev/` refs, so this loop must not push refs that re-trigger
  it (RA-1182: 43 zombie branches).
- **Isolation.** Work only in `/tmp/pi-ceo-enhance/<repo>`, outside any parent
  git repo, so git never pushes to the wrong remote (RA-1169).
- **Kill-switch.** Honour `TAO_HARD_STOP_FILE`, `TAO_MAX_ITERS`, and
  `TAO_MAX_COST_USD` — same three abort axes as every other TAO loop (RA-1966).
- **Model policy (RA-1099).** Opus only for planner/orchestrator; Sonnet for
  generator/evaluator; Haiku for monitor. The runner passes explicit model IDs;
  it must not let Opus leak into build/scan roles.

## Model ladder — API mode (post-2026-07-08 cutover)

Fable-5 left the Max plan on 2026-07-08, so this loop runs **via the Anthropic
API**, not the Max OAuth subscription. `ANTHROPIC_API_KEY` must be set (GitHub
Actions secret for the always-on path; `~/.config/piceo/enhancement.env` for the
launchd path). Latest models:

| Role | Model ID | Env override |
|------|----------|--------------|
| planner / orchestrator (Opus) | `claude-opus-4-6` | `ENHANCE_MODEL_OPUS` |
| generator / evaluator (Sonnet) | `claude-sonnet-4-6` | `ENHANCE_MODEL_SONNET` |
| monitor / scan (Haiku) | `claude-haiku-4-5-20251001` | `ENHANCE_MODEL_HAIKU` |

Override the IDs via env when Anthropic ships newer point releases — do not
hard-code new pins in code.

## Verification

- [ ] Dry-run against one repo produces a review file with the three buckets.
- [ ] No branch is merged; each repo yields at most one open PR per week.
- [ ] `.harness/enhancement-loop/<date>.jsonl` has one line per repo touched.
- [ ] Opus never appears as generator/monitor in the run-log.
- [ ] Kill-switch file drains the loop mid-run.
