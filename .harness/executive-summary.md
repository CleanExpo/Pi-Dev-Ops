# Pi Dev Ops — Executive Summary

_Updated: 2026-04-11 | Sprint 8 in progress | ZTE Score: 60/60_

---

## What It Is

Pi Dev Ops is a Zero Touch Engineering platform that executes engineering work autonomously against any GitHub repository. A developer submits a plain-English brief (or triggers via webhook/cron/Telegram); the system clones the repo, runs Claude Code, self-evaluates the output, and pushes the result — fully unattended.

## Current Status

**ZTE Level 3 — Zero Touch (60/60 leverage points)**

All 12 leverage points at 5/5. 69 features shipped across 8 sprints. Sprint 8 adds: Linear todo auto-poller (autonomy), cron watchdog, CI green (health endpoint fix), deployment parity audit, and DEPLOYMENT.md single source of truth.

## Sprint 8 Shipped (2026-04-11)

- CI green: health endpoint no longer gates on `claude` CLI availability (was failing every CI run)
- `autonomy.py`: Linear todo poller fetches Urgent+High unstarted issues every 5 min, auto-creates sessions
- `cron.py`: startup catch-up fires overdue scan/monitor triggers on container restart; 12h watchdog creates Urgent Linear alert if scheduler goes silent
- `scripts/verify_deploy.py`: commit parity audit compares git HEAD vs Vercel + Railway deployed SHAs
- `DEPLOYMENT.md`: single source of truth for production URLs, env var matrix, rollback procedures

## Cumulative Metrics

| Metric | Value |
|--------|-------|
| ZTE Score | 60/60 |
| Features shipped | 69 |
| Sprints complete | 7 + Sprint 8 in progress |
| MCP tools | 21 |
| Skills loaded | 31 across 7 layers |
| Monitored repos (Pi-SEO) | 10 |
| Evaluator threshold | 8/10 |
| pytest unit tests | 34 |
| Telegram bots | 2 (@piceoagent_bot: dashboard + Railway agentic) |
| Claude Agent SDK PoC | Live (parallel 14-cycle comparison) |
| Autonomy poller | Live (Linear todo → sessions, 5-min interval) |
| CI smoke test | 28/28 checks pass on every push |

## Architecture in One Line

`Linear Todo → autonomy.py poll → sessions.py → PITER → ADW → claude -p → evaluator → push → lessons → Pi-SEO scan → Linear triage`

## Sprint 8 Remaining

1. Agent SDK sessions.py migration (RA-571–576): generator + evaluator calls → `claude_agent_sdk`
2. Post-deploy verification harness (RA-583): `smoke_test.py --target=prod` in CI
3. CLAUDE.md + config.yaml update for SDK architecture (RA-577)
4. Harness doc staleness watchdog — 48h alert if files not regenerated (RA-580)
