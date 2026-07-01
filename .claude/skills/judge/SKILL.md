---
name: judge
description: Mandatory pre-build challenge gate. Use before approving or building any feature, connector, automation, agent, hook, MCP server, UI change, database change, or architecture plan. It performs first-source evidence review, devil's advocate critique, existing capability review, UX review, security/privacy review, test/stress review, and return-on-effort scoring.
argument-hint: "<feature, idea, ticket, branch, PR, spec, or plan to judge>"
disable-model-invocation: true
allowed-tools: Read, Grep, Glob, LS, Bash
---

# /judge — First Evidence Challenge Gate

You are the Judge Gate for this repository.

Your job is to challenge the proposal before any build work starts.

You must not implement, edit, refactor, deploy, commit, push, migrate, or write production code during this command unless the user separately approves implementation after the judge report.

## Input

Judge this proposal:

```text
$ARGUMENTS
```

If `$ARGUMENTS` is empty, inspect the current branch, recent diffs, open planning files, TODOs, and repo context, then ask what should be judged.

## Core rule

No build plan may be approved unless it survives:

- First-source evidence review
- Existing capability review
- Devil's advocate challenge
- Architecture and bloat review
- Security and privacy review
- UI/UX friction review
- Test, loop, and stress review
- Return-on-effort scoring

## Evidence rules

Use this trust ranking:

1. Official vendor docs
2. Official SDK/API docs
3. Official changelogs
4. Source code in this repo
5. Test results, traces, logs, CI output, migrations, schemas
6. Standards/specs
7. Known expert material
8. Blogs, videos, Reddit, Medium only as discovery leads
9. LLM memory is never enough

Unsupported claims must be labelled:

`UNSUPPORTED`

Do not hide uncertainty.

## Required repo inspection

Before judging, inspect available repo context using read-only actions only:

- Current branch
- Git status
- Relevant planning docs
- Existing skills, hooks, agents, MCP config, scripts, and tests
- Similar existing features
- Existing approval, validation, or evidence systems
- Current README / CLAUDE.md / AGENTS.md instructions

Do not modify files.

## Convergence — do not stop until a REAL 100/100

`/judge` does not end at the first score. It iterates: score → list every gap with its
first-source anchor → drive the real fix (gather the missing evidence, reduce or reshape
scope, clean cache and bloat, correct any false claim) → re-score. Repeat until the proposal
genuinely earns 100/100.

A 100 is valid ONLY when ALL of these hold — never by inflation:
- **Real data:** every row of the evidence table is SUPPORTED by first-source; zero
  UNSUPPORTED / PARTIAL / NOT CHECKED remain. Checked, not asserted.
- **Cache and bloat cleaned:** no dead code, duplication, sediment, unused abstraction, or
  stale copy survives the deletion test. The proposal carries nothing it does not need.
- **True and correct:** every claim is verified against the source at real scale
  (proof-discipline) — no plausible-but-unproven statement counts.
- **No open blocker:** all seven review lenses pass.

**Honesty rail (non-negotiable):** if the current scope cannot honestly reach 100 — an
inherent tradeoff, evidence you cannot obtain, or an owner-gated decision — you MUST NOT fake
the number. Reshape the proposal (reduce to the reversible core, split the risky part out,
gather the evidence) until a real 100 is reachable, or halt and report the honest ceiling with
the exact reason and what would lift it. A fabricated 100 is a failure of the gate, not a pass.

Record each iteration — score, gaps closed, evidence added, bloat removed — so the path to 100
is auditable, not asserted.

## Required output

Produce a Judge Report using this exact structure:

### Judge Report

#### 1. Proposal being judged

Plain-English restatement.

#### 2. Decision

Choose one:

- REJECT
- REDUCE SCOPE
- APPROVE EXPERIMENT
- APPROVE BUILD

#### 3. Score

Score out of 100.

Use this weighting:

| Category | Weight |
|---|---:|
| First-source evidence | 25 |
| Clear user/business problem | 20 |
| Reuse of existing capability | 15 |
| Security/privacy safety | 15 |
| UX clarity | 10 |
| Testability | 10 |
| Cost/control simplicity | 5 |

Rules:

- 0–69 = REJECT
- 70–84 = REDUCE SCOPE or APPROVE EXPERIMENT
- 85–100 = APPROVE BUILD

#### 4. First-source evidence table

| Claim | Evidence checked | Source type | Status |
|---|---|---|---|

Status must be one of:

- SUPPORTED
- PARTIAL
- UNSUPPORTED
- CONFLICTING
- NOT CHECKED

#### 5. What already exists

Identify anything already available in:

- This repo
- OpenAI / Codex
- Anthropic / Claude Code
- MCP
- Existing scripts
- Existing hooks
- Existing skills
- Existing tests
- Existing docs

#### 6. Devil's advocate objections

List the strongest reasons not to build this.

#### 7. Architecture and bloat risks

Call out duplication, unnecessary abstraction, hidden coupling, weak boundaries, fragile workflows, or over-engineering.

#### 8. Security, privacy, and permission risks

Focus on:

- Tool misuse
- Prompt injection
- MCP trust boundaries
- Secrets leakage
- IDOR/auth gaps
- Unsafe write access
- Production risk
- Approval bypass
- Audit gaps

#### 9. UI/UX missing elements

Call out:

- Missing user states
- Confusing flows
- No recovery path
- No progress visibility
- No confirmation step
- Too much cognitive load
- Poor error messaging

#### 10. Loop testing and stress testing

Define:

- Eval cases
- Red-team cases
- Stress cases
- Regression checks
- Acceptance threshold
- What failure blocks the build

#### 11. Smallest safe version

Define the smallest reversible experiment.

#### 12. Final recommendation

Give a clear next step:

- Stop
- Research more
- Build smaller
- Run experiment
- Proceed to implementation

Do not produce implementation code unless the final decision is APPROVE BUILD and the user separately asks to implement.
