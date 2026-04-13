# Pi Dev Ops — Executive Summary

_Updated: 2026-04-14 | Sprint 10 active | ZTE v2: 81/100_

---

## What It Is

Pi Dev Ops is a Zero Touch Engineering platform that executes engineering work autonomously against any GitHub repository. A developer submits a plain-English brief (or triggers via webhook/cron/Telegram); the system clones the repo, runs Claude Code via the Agent SDK, self-evaluates the output with a confidence-weighted evaluator, and pushes the result — fully unattended.

## Current Status

**ZTE v2 Level — 81/100**

85 features shipped across 10 sprints. Sprint 9 delivered the Karpathy enhancement layer: confidence-weighted evaluator, plan variation discovery, CEO Board 9-persona governance, Scout Agent intel loop, Supabase observability, and BVI framework. Sprint 10 is running MARATHON-4 — the first 6-hour autonomous self-maintenance session.

## Sprint 10 Active (2026-04-14)

- **MARATHON-4 (RA-588):** First 6-hour autonomous self-maintenance run — session `0b689abd83ad` In Progress since 17:51 AEST Apr 14
- **SDK Canary Phase A:** 10% traffic rate (`AGENT_SDK_CANARY_RATE=0.1`), 24h observation window
- **BVI Baseline:** Cycle 24 first reading establishing business velocity baseline
- **Fixes shipped this session:** max-sessions ghost-session bug, phase-3 SDK branch check, Dockerfile non-root user (pidev uid 1001), analyse_lessons 20h cooldown

## Sprint 9 Complete (2026-04-13)

The Karpathy enhancement layer: 10 Karpathy optimisations + 10 Gap Audit items. Highlights:
- Confidence-weighted evaluator with three-tier routing (auto-accept / human-review / retry)
- Plan variation discovery — 3-variant selection before generator runs
- CEO Board 9 personas wired into automated board meetings
- Scout Agent: autonomous external intel loop (Monday cron)
- Incident history RAG: prior lessons injected into every session context
- Supabase gate_checks table live; all observability tables wired

## Cumulative Metrics

| Metric | Value |
|--------|-------|
| ZTE v2 Score | 81/100 |
| Features shipped | 85 |
| Sprints complete | 9 + Sprint 10 active |
| MCP tools | 21 |
| Skills loaded | 33 across 7 layers |
| Monitored repos (Pi-SEO) | 10 |
| Evaluator threshold | 8/10 (confidence-weighted) |
| pytest unit tests | 46 |
| Telegram bots | 2 (@piceoagent_bot: dashboard + Railway agentic) |
| Claude Agent SDK | Production (TAO_USE_AGENT_SDK=1, all paths) |
| Autonomy poller | Live (Linear todo → sessions, 5-min interval) |
| Supabase tables | 6 (gate_checks, alert_escalations, heartbeat_log, triage_log, workflow_runs, claude_api_costs) |
| Primary board metric | BVI (Business Velocity Index), Cycle 24+ |

## Architecture in One Line

`Linear Todo → autonomy.py poll → sessions.py → plan_discovery → PITER → ADW → claude_agent_sdk → confidence evaluator → push → lessons → Pi-SEO scan → Linear triage → board_meeting (9 personas)`
