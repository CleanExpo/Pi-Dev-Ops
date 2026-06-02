---
name: senior-engineer-workflow
description: Use for non-trivial Pi-Dev-Ops builds that need senior software engineer discipline: scoped plan, bounded subagents, minimal context, tests, independent review, and evidence before moving to the next build.
version: 1.0.0
---

# Senior Engineer Workflow

## Trigger

Use this skill whenever a task asks to build, fix, refactor, ship, audit, or autonomously execute more than a trivial one-file change.

## Prime directive

Do not move to the next build until the current build is finalised or explicitly marked blocked with evidence. Senior engineering means small scope, strong verification, no bloat, and no invented success.

## Model policy

Use Anthropic/Claude Code workflow discipline as the reference methodology, but do not depend on external Anthropic API keys. Route execution through the approved OpenAI-compatible provider layer using GPT-5.5-class and Kimi 2.5-class models.

## Loop

1. Triage
   - Classify intent: feature, bug, chore, spike, hotfix, audit.
   - Identify the repo, ticket, risk, and human-approval boundaries.
   - If scope is unclear, choose the safest narrow interpretation and proceed; ask only if ambiguity changes side effects.

2. Context pack
   - Read only relevant files.
   - Load relevant skills.
   - Identify existing tests and commands before editing.
   - Set a budget: max changed files, max agents, max turns, max wall time.

3. Plan gate
   - State the minimal implementation plan.
   - List expected files and verification commands.
   - If there is no test or probe path, create one or stop as blocked.

4. Implementation
   - One lane at a time.
   - No drive-by refactors.
   - No secret changes, destructive migrations, main pushes, or external-facing releases without explicit approval.
   - New unrelated discoveries become follow-up tickets or notes, not scope creep.

5. Verification
   - Run the smallest relevant test first.
   - Then run the project type-check/lint gate where available.
   - For endpoint/UI work, run a real probe or browser check.
   - Keep exact tool output as evidence.

6. Independent review
   - Use a separate reviewer agent or review pass from the implementer.
   - Check diff scope, security, error handling, tests, and bloat.
   - If review fails, fix and re-run verification.

7. Finalise
   - Create or update run evidence under `.harness/workflows/runs/`.
   - Validate evidence with:
     `python .harness/workflows/senior_engineer_workflow.py validate <manifest> <evidence>`
   - Mark final state: complete, blocked, or rolled back.
   - Only then select the next build.

## Operational runner

Use the installed gate runner when starting or closing a non-trivial build:

```bash
python .harness/workflows/senior_engineer_workflow.py init \
  --intent feature \
  --risk medium \
  --expected-path 'app/server/**' \
  --required-command 'python -m pytest tests/test_provider_router.py -q'

python .harness/workflows/senior_engineer_workflow.py status <manifest> <evidence>
python .harness/workflows/senior_engineer_workflow.py validate <manifest> <evidence>
```

The validator rejects unresolved placeholders, missing connection mapping, failed or missing required-command evidence, same-person implementer/reviewer, denied-path edits, changed-file budget overruns, and final states outside `complete`, `blocked`, or `rolled back`.

## Dynamic workflow usage

Use Claude Code Dynamic Workflows when a task needs many subagents or a reusable orchestration script. Do not use them for simple one-shot fixes.

Best fits:
- codebase-wide bug sweeps;
- large migrations;
- cross-checked research;
- hard architecture plans drafted from multiple angles;
- multi-repo portfolio consistency audits.

## Model routing

- Kimi 2.5/worker: long-context context packs, cheap classification, formatting, mechanical checks.
- GPT-5.5/specialist: implementation and normal senior code execution.
- GPT-5.5/senior reviewer: architecture, security, high-risk plans, final decision review.
- Kimi 2.5/challenger: independent cross-check, alternative plan, long-context critique.

Use the expensive senior model where judgment matters, not for every token.

## Done means evidence exists

A build is not done because an agent says it is done. It is done when evidence exists:

- what changed;
- why it changed;
- exact tests/checks run;
- independent review result;
- blockers/follow-ups;
- final state.
