---
name: judge
description: Mandatory pre-build challenge gate (/judge). Run before approving or building any feature, connector, automation, agent, hook, MCP server, UI change, database change, or architecture plan. Read-only — performs first-source evidence review, devil's advocate critique, existing-capability review, UX review, security/privacy review, test/stress review, and return-on-effort scoring out of 100.
owner_role: Tier-Architect (pre-build challenge gate; read-only reviewer)
status: active
automation: manual
machine_runnable: true
---

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

Decision rules (bounded development floor 85/100; promotion floor 95/100; target 100/100):

- **APPROVE EXPERIMENT at 85–94** permits only the named reversible local development scope
  with separate explicit user/project authority, a concrete test plan, and no hard block.
  It is not ordinary build/promotion approval. Apply `.judge/approval-policy.md`.
- **APPROVE BUILD requires an earned 95–100 and no hard block.** Existing callers and
  promotion requests retain 95; no numerical pass approves push, activation, or release.
- 0–69 = REJECT; 70–84 = REDUCE SCOPE. Below 85, reshape the development scope before proceeding.
- At 85–99, name each remaining non-blocking gap, owner, closure action, and required evidence
  before its dependent stage. Only clear_problem, reuse_existing, ux_clarity, and testability
  deductions qualify; missing/unsupported evidence and mandatory findings stay blocking.
- Security, privacy, billing/spend, workspace trust, authority, isolation, rollback,
  irreversibility and `must_fix` blockers prevent either stage at every score.

## Convergence — develop at 85, promote at 95, pursue 100

Iterate: score → anchor gaps to first-source evidence → close blockers, gather evidence,
reduce scope or bloat → re-score. A qualifying development scope can stop at 85–94 and improve
through separately authorised local implementation. Promotion must earn 95+ with its gap plan.
The quality target remains a real 100; never inflate scores or fabricate passed tests.
The machine development stage produces a preparation packet and stops before the uncontained
SDK builder, workspace mutation, test execution, Git, shipping, and runtime activation.

A 100 is valid only when all criteria for the judged stage are satisfied:
- **Real data:** every present-state claim is SUPPORTED by first-source evidence; no unresolved
  evidence gap is hidden in the score.
- **Cache and bloat reviewed:** no unnecessary duplication, dead code, or stale copy remains
  in the proposed scope.
- **True and correct:** claims of verification reflect checks actually executed and observed.
- **No open gap or blocker:** all mandatory review findings and scored quality gaps are closed.

**Evidence timing:** a concrete test plan can satisfy pre-build testability. Mark future tests
`PLANNED`, never passed; do not award execution evidence for them. Completion and release still
require the applicable checks to run on the actual candidate and pass before those claims.

**Honesty rail:** report the earned score and exact remaining gaps even when 100 is unreachable.
Reshape blocked scope or report the blocker and recovery evidence. A fabricated 100 is a gate
failure, not a pass.

Record each iteration — score, gaps closed, evidence added, bloat removed — so the path to 100
is auditable, not asserted.

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

Judge remains read-only by default. Separately requested implementation requires an approved
experimental local scope at 85+ or an ordinary build/promotion scope at 95+, with all hard
guards and required user/project authority. A score alone is not authority.
