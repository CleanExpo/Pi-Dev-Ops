# Pi Dev Ops — Executive Summary

_Updated: 2026-04-08 | Sprint 3 complete | ZTE Score: 60/60_

---

## What It Is

Pi Dev Ops is a Zero Touch Engineering platform that executes engineering work autonomously against any GitHub repository. A developer submits a plain-English brief; the system clones the repo, runs Claude Code, self-evaluates the output, and pushes the result to GitHub — with zero human intervention mid-run.

## Current Status

**ZTE Level 3 — Zero Touch (60/60 leverage points)**

All 12 leverage points score 5/5. The system detects work (GitHub/Linear webhooks, cron triggers), writes structured specs (PITER + ADW templates), executes Claude Code in an isolated sandbox, grades output with a blocking evaluator, retries if below threshold, learns from failures (lessons.jsonl), and pushes to GitHub — fully automated.

## Sprint 3 Outcomes (2026-04-08)

- E2E smoke test: 22/22 checks pass across all subsystems
- Git push retry: 3 attempts with exponential backoff; auth errors hard-stop immediately
- MCP `get_zte_score` now reads `leverage-audit.md` directly (always current)
- PITER priority bug fixed: chore/spike intents now correctly outrank "feature" fallback

## Key Metrics

| Metric | Value |
|--------|-------|
| ZTE Score | 60/60 |
| Active Sessions (max) | 3 concurrent |
| Evaluator threshold | 7/10 |
| Evaluator max retries | 2 (3 total attempts) |
| Clone retry attempts | 3 (2s/4s backoff) |
| Push retry attempts | 3 (2s/4s backoff) |
| Workspace GC TTL | 4 hours |
| Lessons in memory | 18 entries |
| MCP tools available | 11 |
| Skills loaded | 23 across 5 layers |

## Architecture in One Line

`Brief → PITER classify → ADW template → skills inject → lessons inject → claude -p → evaluator → retry-or-push → lessons learn`

## Next Sprint (Sprint 4) Priorities

1. `executive-summary.md` — this file (MCP board notes now functional)
2. Fix `token-budgeter` skill cost values
3. Fix `tao-skills` master index (ceo-mode missing)
4. Dashboard–backend session phase alignment
5. `GET /api/capabilities` endpoint
6. `scripts/smoke_test.py` E2E regression runner
