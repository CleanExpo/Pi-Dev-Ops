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

Decision rules:

- 0–69 = REJECT
- 70–84 = REDUCE SCOPE or APPROVE EXPERIMENT
- 85–100 = APPROVE BUILD

## Convergence — do not stop until a REAL 100/100

`/judge` does not end at the first score. It iterates: score → list every gap with its
first-source anchor → drive the real fix (gather the missing evidence, reduce or reshape
scope, clean cache and bloat, correct any false claim) → re-score. Repeat until the proposal
genuinely earns 100/100.

A 100 is valid ONLY when ALL of these hold — never by inflation:
- **Real data:** every evidence row is SUPPORTED by first-source; zero UNSUPPORTED / PARTIAL /
  NOT CHECKED remain. Checked, not asserted.
- **Cache and bloat cleaned:** no dead code, duplication, sediment, unused abstraction, or
  stale copy survives the deletion test.
- **True and correct:** every claim is verified against the source at real scale — no
  plausible-but-unproven statement counts.
- **No open blocker:** all review passes clear.

**Honesty rail (non-negotiable):** if the scope cannot honestly reach 100, do NOT fake the
number — reshape it until a real 100 is reachable, or halt and report the honest ceiling with
the exact reason and what would lift it. A fabricated 100 is a gate failure, not a pass.

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
