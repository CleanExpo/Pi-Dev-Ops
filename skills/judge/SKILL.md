---
name: judge
description: Mandatory pre-build challenge gate (/judge). Run before approving or building any feature, connector, automation, agent, hook, MCP server, UI change, database change, or architecture plan. Read-only — performs first-source evidence review, devil's advocate critique, existing-capability review, UX review, security/privacy review, test/stress review, and return-on-effort scoring out of 100.
owner_role: Tier-Architect (pre-build challenge gate; read-only reviewer)
status: active
automation: manual
---

# judge — First Evidence Challenge Gate

Review only — `/judge` never builds, edits, commits, pushes, migrates, or deploys.
It challenges the proposal before any build work starts. Implementation may only
follow a separate, explicit user approval after the Judge Report.

This is the human-facing pre-build gate. It is distinct from `tao-judge`, the
machine loop-termination scorer used inside the TAO judge-gated loop: `judge`
decides *whether to build*; `tao-judge` decides *whether an in-flight loop is done*.

## Input

Judge the proposal supplied as `$ARGUMENTS` (a feature, idea, ticket, branch, PR,
spec, or plan). If empty, inspect the current branch, recent diffs, open planning
files, TODOs, and repo context, then ask what should be judged.

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

## Evidence ranking

1. Official vendor docs
2. Official SDK/API references
3. Official changelogs
4. Repo source code
5. Tests, CI, logs, traces, schemas, migrations
6. Standards/specs
7. Known expert material
8. Blogs/videos/social only as discovery leads
9. LLM memory is never enough

Unsupported claims must be labelled `UNSUPPORTED`. Do not hide uncertainty.
See `.judge/source-ranking.md` and `.judge/approval-policy.md`.

## Required repo inspection (read-only)

Before judging, inspect the current branch, git status, relevant planning docs,
existing skills/hooks/agents/MCP config/scripts/tests, similar existing features,
existing approval/validation/evidence systems, and current README / CLAUDE.md /
AGENTS.md instructions. Do not modify files.

## Score

Score out of 100:

| Category | Weight |
|---|---:|
| First-source evidence | 25 |
| Clear user/business problem | 20 |
| Reuse of existing capability | 15 |
| Security/privacy safety | 15 |
| UX clarity | 10 |
| Testability | 10 |
| Cost/control simplicity | 5 |

Decision rules:

- 0–69 = REJECT
- 70–84 = REDUCE SCOPE or APPROVE EXPERIMENT
- 85–100 = APPROVE BUILD

## Required output — Judge Report

Produce a Judge Report with this exact structure (see `.judge/report-template.md`):

1. Proposal being judged
2. Decision (REJECT / REDUCE SCOPE / APPROVE EXPERIMENT / APPROVE BUILD)
3. Score
4. First-source evidence table (status: SUPPORTED / PARTIAL / UNSUPPORTED / CONFLICTING / NOT CHECKED)
5. What already exists
6. Devil's advocate objections
7. Architecture and bloat risks
8. Security, privacy, and permission risks
9. UI/UX missing elements
10. Loop testing and stress testing
11. Smallest safe version
12. Final recommendation

Do not produce implementation code unless the final decision is APPROVE BUILD and
the user separately asks to implement.
