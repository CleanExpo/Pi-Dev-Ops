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

Decision rules (HARD LINE — 100/100 is the only build bar):

- **APPROVE BUILD requires a real 100/100** — every mandatory criterion in the Convergence
  section satisfied, no exceptions. There is no 85 pass. 85–99 is not "good enough"; it is a
  list of gaps to close.
- 0–99 = **NOT APPROVED.** Do not build. Iterate per Convergence (close every gap, re-score)
  until a real 100 is earned, or — if 100 is honestly unreachable at this scope — halt and
  report the honest ceiling with the exact blocker (never approve below 100, never inflate).
- Intermediate labels REJECT (0–69) / REDUCE SCOPE / APPROVE EXPERIMENT (70–99) describe the
  *iteration state* only; none of them authorise a production build. Only a real 100 does.

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
