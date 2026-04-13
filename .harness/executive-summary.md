# Pi Dev Ops — Executive Summary

_Updated: 2026-04-14 | Sprint 11 active | ZTE v2: 84/100 (projected 85+ after next scan)_

---

## What It Is

Pi Dev Ops is a Zero Touch Engineering platform that executes engineering work autonomously against any GitHub repository. A developer submits a plain-English brief (or triggers via webhook/cron/Telegram); the system clones the repo, runs Claude Code via the Agent SDK, self-evaluates the output with a confidence-weighted evaluator, and pushes the result — fully unattended.

## Current Status

**ZTE v2 Level — 84/100 (projected 85+ after next scan)**

89 features shipped across 10 sprints. Sprint 9 delivered the Karpathy enhancement layer. Sprint 10 is driving ZTE v2 from 84 → 90: Section C data collection wired (C4 live at 4/5, all exclusions set for 5/5 on next scan), session-outcomes.jsonl wired for C2, CCW-CRM quality fix pushed, carsi hardcoded credential removed, Synthex error leakage fix in progress.

## Sprint 11 Active (2026-04-14)

- **⚠️ Hard deadline:** RA-818 (Gemini Scheduled Action — Google Cloud Next '26 briefing) must be live before April 22.
- **Gemini automation layer (RA-816–819):** Dedicated Google account → notebooklm-mcp-cli → 2 Gemini Scheduled Actions. All in Review, awaiting manual account setup.
- **Dep health PRs (RA-843):** 4 branches ready to merge (carsi/DR-NRPG/Synthex/unite-group). Merge triggers C4 → 5/5 on next scan.
- **Synthex major CVEs (RA-844):** 10 remaining CVEs requiring major version migrations (@supabase/ssr → stripe → zustand etc.).
- **MARATHON-4 (RA-588):** First 6-hour autonomous self-maintenance run — carries from Sprint 10, still In Progress.

## Sprint 10 Complete (2026-04-14)

89 features shipped across 10 sprints. All Sprint 10 targets delivered:
- ZTE v2 C4 security → 5/5 projected (28 exclusions + carsi credential fix + RA-786 error leakage)
- All 4 dep health branches pushed (0 → 80+ projected across portfolio)
- BVI Cycle 24 baseline established. ZTE 84 → 85 (after next scan) → 90 (C1+C2+C3 when Railway sessions flow).

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
| ZTE v2 Score | 84/100 (projected 85+ after next scan) |
| Features shipped | 94 |
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
