# Pi Dev Ops — Executive Summary

_Updated: 2026-04-16 | Sprint 12 active | ZTE v2: 85/100_

---

## What It Is

Pi Dev Ops is a Zero Touch Engineering platform that executes engineering work autonomously against any GitHub repository. A developer submits a plain-English brief (or triggers via webhook/cron/Telegram); the system clones the repo, runs Claude Code via the Agent SDK, self-evaluates the output with a confidence-weighted evaluator, and pushes the result — fully unattended.

## Current Status

**ZTE v2 Level — 85/100 | Sprint 12 | 98+ features shipped**

Swarm mode activated (board vote 15 Apr 2026). Rate limit: 3 autonomous PRs/day, lifts after 20 consecutive green supervised merges. Prompt caching enabled (ENABLE_PROMPT_CACHING_1H). Security hardening sprint complete (RA-1003–1032, 16 PRs merged).

## Sprint 12 Active (2026-04-16 → 6 May 2026)

- **Swarm activation:** `TAO_SWARM_SHADOW=0` deployed. Railway env var and `TAO_PASSWORD` in `.env.local` still required for builder to fire autonomously.
- **NotebookLM KB build (RA-822/823/824):** 5-criteria knowledge bases for RestoreAssist, Synthex, CleanExpo — in review.
- **Open PRs:** #22 (persona evaluator), #24/#25 (security hardening batch 3/4), #30 (Routine tracker).
- **Next board:** 6 May 2026 — Enhancement Review (RA-949).

## Sprint 11 Complete (2026-04-14)

Gemini automation layer live (2 Scheduled Actions: Google Cloud Next '26 briefing + daily calendar digest). First autonomous PR pushed. main.py decomposed 922L → 11 focused route modules. NotebookLM entity ranking complete.

## Sprint 10 Complete (2026-04-14)

BVI Cycle 24 baseline. ZTE v2 Section C wired (C4 live, C2 wired via session-outcomes.jsonl). Scanner false-positive audit (28 exclusions). CCW-CRM quality 50→90.

## Cumulative Metrics

| Metric | Value |
|--------|-------|
| ZTE v2 Score | 85/100 |
| Features shipped | 98+ |
| Sprints complete | 11 (Sprint 12 active) |
| MCP tools | 21 |
| Skills loaded | 33 |
| Monitored repos (Pi-SEO) | 11 |
| Evaluator threshold | 8.5/10 (confidence-weighted) |
| pytest unit tests | 46 |
| Claude Agent SDK | Production (TAO_USE_AGENT_SDK=1) |
| Autonomy poller | Live (Linear todo → sessions, 5-min interval) |
| Supabase tables | 6 |
| Prompt caching | Enabled (ENABLE_PROMPT_CACHING_1H=1) |

## Architecture in One Line

`Linear Todo → autonomy.py poll → sessions.py → scan → plan_discovery → PITER → ADW → claude_agent_sdk → confidence evaluator → push → lessons → Pi-SEO scan → Linear triage → board_meeting (9 personas)`
