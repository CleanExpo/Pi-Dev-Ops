# Judge — Pre-Build Challenge Gate

Judge is a read-only challenge gate run **before** any build, connector, hook, agent,
MCP server, database change, UI change, or architecture plan is approved. It challenges
the proposal, demands first-source evidence, checks for existing capability, reviews
UX and security/privacy, defines loop/stress tests, and scores the proposal out of 100.

## Where it lives

| CLI | Repo file | Invocation |
|---|---|---|
| Claude Code | `.claude/skills/judge/SKILL.md` | `/judge <proposal>` |
| Codex CLI | `.agents/skills/judge/SKILL.md` | `$judge <proposal>` or `/skills` → select `judge` |
| Shared docs | `.judge/*` | Referenced by both |

## Shared reference files

- [`source-ranking.md`](source-ranking.md) — the evidence trust hierarchy.
- [`approval-policy.md`](approval-policy.md) — decisions, score thresholds, hard blocks.
- [`report-template.md`](report-template.md) — the exact Judge Report structure.
- [`examples/sample-judge-report.md`](examples/sample-judge-report.md) — a worked example.

## Relationship to `tao-judge`

`tao-judge` (`skills/tao-judge/`, `app/server/tao_judge.py`) is a **machine** loop-termination
scorer used inside the TAO judge-gated loop — it returns a single JSON verdict to decide
whether a worker has met a goal. This `judge` gate is the **human-facing** pre-build review.
They are complementary, not duplicates: `judge` decides *whether to build*; `tao-judge`
decides *whether an in-flight build loop is done*.

## Core rule

No build plan may be approved unless it survives first-source evidence review, existing
capability review, devil's advocate challenge, architecture/bloat review, security/privacy
review, UI/UX friction review, test/loop/stress review, and return-on-effort scoring.

Judge never implements, edits, commits, pushes, migrates, or deploys. Implementation may
only follow a separate, explicit user approval after the Judge Report.
