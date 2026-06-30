---
name: review-command
description: /review specialised command skill. Use when the operator asks for /review, review, code review, launch review, or "check this before ship" and needs one de-duplicated, evidence-backed review packet instead of fixes or secondary work.
owner_role: Guardian
status: wave-review
intents: review, code-review, launch-review, pre-merge-review
---

# review-command

A specialised `/review` command lane. It turns a broad review request into one focused, evidence-backed review packet and stops before fixing.

## Overview

`/review` is the command for judgement, not implementation. It removes noisy branches by selecting the right review lenses, collecting concrete evidence, ranking findings, and producing a short go/no-go packet. It does not patch code, redesign screens, open new vendors, deploy, contact clients, or merge PRs.

Use this as the direct command wrapper around [`launch-review`](../launch-review/SKILL.md), [`agentic-review`](../agentic-review/SKILL.md), [`tier-evaluator`](../tier-evaluator/SKILL.md), and [`leverage-audit`](../leverage-audit/SKILL.md). For PR/diff review discipline, also apply the same evidence-first standard as `requesting-code-review`. If the ask is specifically about launch readiness, keep `launch-review` as the primary judge. If the ask is about a branch or PR, keep `agentic-review` and `tier-evaluator` as the primary judges.

## When to Use

- `/review`
- "review this"
- "check before ship"
- "is this ready?"
- "review the PR"
- "review the product"
- "what are the blockers?"
- The review step after `/northstar`, `/ship-it`, or `priority_path_router` selects a lane.

Do not use this when the user has already approved fixes and asked to implement. Then route to `ship-chain`, `tao-loop`, `launch-enhance-debloat`, or the relevant build skill.

## Command Contract

1. **Scope the review target**
   - Current branch/worktree if no target is named.
   - PR URL/number if supplied.
   - Product URL if the ask is launch/user-facing readiness.
   - Repo docs/skills if the ask is knowledge or pathway quality.

2. **Collect evidence before judgement**
   - Git state: branch, diff/stat, recent commits.
   - Tests/builds relevant to the touched stack.
   - Existing audit outputs in `.harness/audits/` where present.
   - Live checks/PR checks when reviewing a PR.

3. **Fan out to the minimum useful lenses**
   - Launch/product readiness: `launch-review`.
   - Code quality: `agentic-review`.
   - Spec/task compliance: `tier-evaluator`.
   - Leverage/priority: `leverage-audit`.
   - Security/design only when the target actually touches those surfaces.

4. **Return one de-duplicated packet**
   - Verdict: `PASS`, `PASS_WITH_WARNINGS`, or `BLOCKED`.
   - Top 3 blockers/warnings only, unless the user asks for full detail.
   - Each finding cites file/URL/check and the lens that found it.
   - Suggested next lane: fix, ship, ticket, or stop.

5. **Stop before changing code**
   - Review only; never fixes.
   - If fixes are required, name the smallest next PR lane and wait for go.

## Noise Removal Rules

Defer anything that does not affect the review verdict:

- New vendor/platform suggestions.
- Broad redesigns not tied to a concrete launch blocker.
- Historical background that does not change the current branch/product state.
- Documentation-only cleanup unless the review target is docs/knowledge quality.
- Extra research when current repo, tests, and PR checks already decide the verdict.

## Output Shape

Write or return:

```md
# Review packet

Verdict: PASS | PASS_WITH_WARNINGS | BLOCKED
Target: <branch/pr/url/repo>
Evidence: <commands/checks/files inspected>

## Top findings
1. [CRITICAL/WARNING/SUGGESTION] <finding> — <location> — <lens>

## Required next lane
- <ship/fix/ticket/stop>
```

If writing to disk, use `.harness/audits/review-<YYYY-MM-DD>.md`.

## Safety Boundaries

- Review only; never fixes.
- Never opens new vendors or accounts.
- Never changes production env, DB, billing, secrets, deploy settings, or client comms.
- Never merges PRs as part of `/review`; merging belongs to the PR workflow after explicit operator go.
- Redact secrets in quoted logs.

## Verification Checklist

- [ ] The target is explicit.
- [ ] Evidence was collected from live repo/PR/build state.
- [ ] Findings are de-duplicated and ranked.
- [ ] Every blocker cites a concrete file, URL, command, or check.
- [ ] No code, config, DB, deploy, or client-facing side effects were performed.
