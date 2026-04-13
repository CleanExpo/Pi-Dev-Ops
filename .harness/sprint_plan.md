# Pi Dev Ops — Sprint Plan

_Sprint 11 active | 2026-04-14 | ZTE v2: 84/100 (projected 85+ after next scan) | 95 features shipped_

---

## Sprint 11 — Active (2026-04-14)

**Theme:** Gemini Automation Layer + Dep Health + ZTE v2 → 90

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-839 | Urgent | Sprint 11 deadline alert — RA-818 before April 22 | **Done** |
| RA-816 | Urgent | Google account for Gemini automation (primary account used) | **Done** |
| RA-817 | Urgent | notebooklm-mcp-cli v0.5.23 on Mac Mini | **Done** |
| RA-818 | Urgent | Gemini Scheduled Action — Google Cloud Next '26 daily briefing | **Done** |
| RA-819 | Urgent | Gemini Scheduled Action — daily calendar and email digest | **Done** |
| RA-843 | High | Dep health PRs merged — carsi, DR-NRPG, Synthex, unite-group | **Done** |
| RA-844 | High | Synthex CVE migrations — 6 done (supabase/ssr, nodemailer, zustand, tailwind-merge, lucide-react, date-fns); stripe/ts/eslint/jest deferred | **Done** |
| RA-588 | High | MARATHON-4: first 6-hour autonomous self-maintenance run | **In Progress** |

**Remaining:** MARATHON-4 completion · carsi `ADMIN_PASSWORD` (DigitalOcean, developer action required)

---

## Sprint 10 — Complete (2026-04-14)

**Theme:** MARATHON-4 + BVI Baseline + ZTE v2 Section C

| Issue | Priority | Title | Status |
|-------|----------|-------|--------|
| RA-814 | High | BVI First Baseline — Cycle 24 snapshot | **Done** |
| RA-815 | High | Harness doc regeneration — sprint_plan.md + feature_list.json | **Done** |
| RA-834 | High | Scanner false-positive audit — 28 exclusions added to config.py | **Done** |
| RA-835 | High | carsi hardcoded admin password removed | **Done** |
| RA-672 | High | ZTE v2 Section C — C4 live (4/5), C2 wired (session-outcomes.jsonl) | **Done** |
| RA-690 | High | CCW-CRM code quality 50→90 | **Done** |
| RA-786 | High | Synthex error message leakage — 107 API routes | **Done** |

---

## Sprint 9 — Complete (2026-04-13)

**Theme:** Karpathy Enhancement Layer + Gap Audit

| Issue | Change |
|-------|--------|
| RA-674 | Confidence-weighted evaluator — three-tier routing (auto-accept / review / retry), `CONFIDENCE: N%` parsing |
| RA-675 | Reality-check sprint — closed 19-pt self-scan gap (41/60 → 60/60 ZTE) |
| RA-676 | AUTONOMY_BUDGET single-knob — unified budget control across generator + evaluator |
| RA-677 | Session Scope Contract — hard limits on file-touch radius, test-pass gate, reversibility check |
| RA-678 | Progressive brief complexity — difficulty tiering for autonomous sessions |
| RA-679 | Plan variation discovery — 3-variant selection before generator runs |
| RA-680 | Layered abstraction — TAO tier separation enforced in build pipeline |
| RA-681 | Dependency alerting — CVE + breaking-change detection injected into session context |
| RA-682 | Vercel drift monitoring — deployed SHA vs git HEAD parity watchdog |
| RA-683 | Ship Chain Educational Series — 5-doc `docs/ship-chain/` |
| RA-684 | Scout Agent — Monday 04:30 UTC cron, `agents/scout.py` |
| RA-686 | CEO Board Skill — 9 personas in `board_meeting.py` |
| RA-651 | Supabase `gate_checks` table + `log_gate_check()` in `supabase_log.py` |
| RA-660 | Incident history RAG — `lessons.jsonl` injected into session generator context |
| RA-696 | BVI framework — Business Velocity Index replaces ZTE as primary board metric Cycle 24+ |
| RA-694 | Gap Audit — all 9 disconnected components wired |

**ZTE v2: 81/100**

---

## Sprint 8 — Complete (2026-04-11)

| Issue | Change |
|-------|--------|
| RA-551–576 | Agent SDK migration — board_meeting.py, sessions.py generator + evaluator, orchestrator.py, pipeline.py; subprocess fallback removed |
| RA-579 | `cron.py`: startup catch-up + 12h watchdog fires Urgent Linear ticket if scheduler silent |
| RA-580 | Harness doc staleness watchdog — 48h alert |
| RA-581–583 | `DEPLOYMENT.md`, `verify_deploy.py`, CI `smoke-prod` job |
| RA-584 | `autonomy.py`: Linear todo poller, `/api/autonomy/status` |
| RA-585 | MARATHON-1: 46 pytest tests total |

---

## Sprint 7 — Complete (2026-04-10)

Mobile/tablet layout · worktree isolation hooks · @piceoagent_bot Telegram dashboard · Railway agentic Claude bot (RA-546–549)

---

## Sprint 6 — Complete (2026-04-10)

Pi-SEO autonomous scanner: 10-repo monitoring, triage engine, auto-PR, health dashboard, 6h cron, 13 MCP tools (RA-531–543)

---

## Sprints 1–5 — Complete (2026-04-07–09)

Foundation → Security Hardening → Capability → ZTE Sprint: 0 → 81/100 v2 across 70+ issues.
