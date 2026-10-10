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

Decision rules (build floor 95/100; target 100/100):

- **APPROVE BUILD requires an earned score of 95–100 and no hard block.** Apply
  `.judge/approval-policy.md`; the score covers only the named scope and checked evidence.
- 0–69 = REJECT; 70–94 = REDUCE SCOPE or APPROVE EXPERIMENT. **0–94 is NOT BUILD APPROVED.**
  An experiment needs its own bounded scope and explicit authority; it cannot bypass a blocker.
- At 95–99, list every remaining non-blocking gap, its closure action, owner, and evidence
  required before any dependent stage. Continue pursuing 100; never round up or invent it.
- Security, privacy, billing/spend, workspace trust, authority, and other mandatory `must_fix`
  blockers prevent approval regardless of score. A numerical pass does not authorise
  implementation, activation, push, or release; retain the separate user and project gates.

## Convergence — clear blockers, earn 95, keep pursuing 100

Iterate: score → anchor each gap to first-source evidence → close blockers, gather evidence,
reduce scope or bloat → re-score. A qualifying 95–99 may proceed through the existing approval
process with its explicit gap-closure plan; the target remains a real 100.

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
