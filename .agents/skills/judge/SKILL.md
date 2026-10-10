---
name: judge
description: Mandatory pre-build challenge gate. Use before approving or building any feature, connector, automation, agent, hook, MCP server, UI change, database change, or architecture plan. Performs first-source evidence review, devil's advocate critique, existing capability review, UX review, security/privacy review, test/stress review, and return-on-effort scoring.
---

# judge — First Evidence Challenge Gate

Run this skill before any build, implementation, connector, hook, agent, MCP server, database change, UI change, or architecture plan is approved.

Judge this proposal:

```text
$ARGUMENTS
```

## Hard rule

Do not build. Do not edit. Do not commit. Do not push. Do not deploy.

This is a read-only pre-build review.

## Required review passes

- First-source evidence review
- Existing capability review
- Devil's advocate challenge
- Architecture and bloat review
- Security and privacy review
- UI/UX friction review
- Test, loop, and stress review
- Return-on-effort scoring

## Evidence ranking

Use first-source evidence wherever possible:

1. Official docs
2. Official SDK/API references
3. Official changelogs
4. Repo source code
5. Tests, CI, logs, traces, schemas, migrations
6. Standards/specs
7. Known expert material
8. Blogs/videos/social only as discovery

LLM memory is not evidence.

Unsupported claims must be marked `UNSUPPORTED`.

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

## Output format

### Judge Report

1. Proposal being judged
2. Decision
3. Score
4. First-source evidence table
5. What already exists
6. Devil's advocate objections
7. Architecture and bloat risks
8. Security, privacy, and permission risks
9. UI/UX missing elements
10. Loop testing and stress testing
11. Smallest safe version
12. Final recommendation
