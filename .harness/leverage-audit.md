# Pi Dev Ops — Leverage Audit

## Current Score: 85 / 100 (ZTE v2) — Zero Touch Band

_ZTE v2 framework: 100-point scale (Section A: AI Pipeline 60pts + Section B: Operational Health 15pts + Section C: External Validation 25pts). See `.harness/zte-framework-v2.md`._

_ZTE v1 reference (75-point): 73/75. Updated to v2 as of Sprint 9. Historical changelog below uses v1 scoring._

*Last updated: 2026-04-16 (Sprint 12 active)*

> **RA-675 resolution note:** Previous self-scan returned 41/60 ZTE due to stale spec.md (RA-685).
> spec.md regenerated 2026-04-13. Automated ZTE v2 score: 81/100 (73/75 + 8/25 Section C).
> Scanner false positives from scanner.py scanning its own regex patterns added to path_exclusions.
> Ruff lint errors (F401/F841/F541) resolved across app/server/, scripts/, src/.

> **Scoring revision (RA-652):** Framework extended from 12 AI-pipeline dimensions (60 max) to 15 dimensions
> including 3 Operational Health dimensions (75 max). Rationale: a 60/60 AI pipeline score is meaningless
> if the local infrastructure running it is unreliable. Operational health is now a first-class gate.

### Section A — AI Pipeline (12 dimensions, max 60)

| # | Leverage Point | Score (1-5) | Notes |
|---|---------------|-------------|-------|
| 1 | Spec Quality | 5 | PITER classifier + ADW templates + skill injection (RA-456, RA-457) |
| 2 | Context Precision | 5 | Lesson context injected per-intent into every brief (`_get_lesson_context`) |
| 3 | Model Selection | 5 | Auto-selected from `.harness/config.yaml` agents block; override still works |
| 4 | Tool Availability | 5 | Full Claude Code tool suite + fan-out parallelism + opus tier escalation |
| 5 | Feedback Loops | 5 | Closed-loop evaluator retry: critique injected into retry prompt, re-evaluates |
| 6 | Error Recovery | 5 | Clone 3-attempt backoff, generator retry, phase checkpoints, session resume |
| 7 | Session Continuity | 5 | Phase-level checkpoints; `POST /api/sessions/{sid}/resume` skips done phases |
| 8 | Quality Gating | 5 | Evaluator is now BLOCKING gate with max 2 retries before push |
| 9 | Cost Efficiency | 5 | Zero API cost on Claude Max 20x plan; Claude API fallback cost-tracked per call |
| 10 | Trigger Automation | 5 | GitHub + Linear webhooks + cron triggers + n8n 5-min Linear poller (RA-643) |
| 11 | Knowledge Retention | 5 | Auto-learn: evaluator low-scoring dimensions → lessons.jsonl; injected in briefs |
| 12 | Workflow Standardization | 5 | PITER classifier enforced at brief entry; all 5 ADW templates active (RA-456) |

**Section A Total: 60 / 60**

### Section B — Operational Health (3 dimensions, max 15)

| # | Leverage Point | Score (1-5) | Notes |
|---|---------------|-------------|-------|
| 13 | Infrastructure Reliability | 3 | Mac Mini sleep=off + autorestart=on (RA-637); Ollama launchd watchdog (RA-638); n8n Docker restart=always (RA-639). UPS still pending (RA-641) — power cut = outage. No cloud failover yet. |
| 14 | Operational Observability | 5 | Bloomberg terminal Command Centre at :3001 (RA-648); `gate_checks` table logs every /ship phase gate result (RA-651); `supabase_log.py` is single write path for all server-side events; `alert_escalations` table tracks full alert lifecycle. |
| 15 | Incident Response | 5 | Telegram alerting active (RA-645, RA-649); Autonomy Watchdog pre-check (RA-632); escalation watchdog in `cron.py` re-pages after 30 min if alert unacked (RA-633); `alert_escalations` Supabase table tracks ack/escalated state. Full automated escalation chain complete. |

**Section B Total: 13 / 15**

---

**Grand Total: 73 / 75**

### Band Thresholds (Revised for 75-point framework)
- **Manual (1-25):** Human drives every step
- **Assisted (26-44):** AI helps but human orchestrates
- **Autonomous (45-67):** AI orchestrates, human reviews
- **Zero Touch (68-75):** Fully autonomous pipeline with operational integrity

### Path to 75 / 75
| Dimension | Gap | Action Required |
|-----------|-----|-----------------|
| Infrastructure Reliability (13) | 3→5 | **RA-641: Purchase UPS** (+2 pts — Phill's action). Power cut = outage until UPS installed. User has elected not to purchase UPS — ceiling is 73/75 (98% operational). |

### App Operational Status (98% — all code-fixable issues resolved 2026-04-13)
| Area | Status | Notes |
|------|--------|-------|
| Auth (login + session) | ✅ | HMAC key aligned; Edge Buffer bug fixed |
| gate_checks Supabase writes | ✅ | NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY set in Railway |
| Linear ticket creation | ✅ | LINEAR_API_KEY added to Vercel production env |
| Branch naming (same-day 422) | ✅ | pidev/analysis-YYYYMMDD-HHmm format |
| Autonomy poll Linear 400 | ✅ | orderBy: priority → orderBy: updatedAt |
| Scanner SSH clone failure | ✅ | git@github.com: → https://github.com/ |
| vercel_monitor._root | ✅ | Private attr replaced with Path(__file__).parents[2] |
| VERCEL_TOKEN on Railway | ⚠️ | Requires manual token creation at vercel.com/account/tokens |

---

## Changelog

### 2026-04-13 — Cycle 24: All active errors resolved — App at 98% operational
| Fix | Detail |
|-----|--------|
| Auth infinite loop | proxy.ts HMAC key aligned with login route (DASHBOARD_PASSWORD) |
| Edge runtime crash | Buffer.from() → btoa() in proxy.ts (Edge runtime has no Buffer) |
| gate_checks 0 rows | NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY added to Railway |
| PI_CEO_PASSWORD trailing \n | re-set via printf (not echo) to strip newline |
| Linear ticket never shown | LINEAR_API_KEY added to Vercel production env |
| Same-day branch 422 | branch now pidev/analysis-YYYYMMDD-HHmm |
| Autonomy poll Linear 400 | orderBy: priority → orderBy: updatedAt in autonomy.py |
| Scanner SSH clone failure | git@github.com → https://github.com in scanner.py |
| vercel_monitor private attr | config._root → Path(__file__).parents[2] |

### 2026-04-13 — Cycle 23: Sprint 9 close — CEO Memo structural build (73/75 maintained)
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Scout Agent | — | RA-684 | Weekly GitHub/ArXiv/HN intel gathering; [SCOUT] Linear issues; pre-board cron Mon 04:30 UTC |
| CEO Board Personas | — | RA-686 | 9 personas (Phase 2.5) wired into board_meeting.py; SWOT gets CEO SYNTHESIS |
| Feedback Loop | — | RA-689 | analyzing-customer-patterns skill built; shipped-features.jsonl tracking; stale-feature review issues |
| BVI Metric | — | RA-696 | Business Velocity Index: CRITICALs + portfolio delta + MARATHON completions; primary board metric from Cycle 24 |
| Self-scan gap | RA-675 | Resolved | spec.md regenerated; scanner false positives excluded; ruff errors fixed; leverage-audit updated |

### 2026-04-12 — Cycle 22: Sprint 8 close-out — 71→73/75
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Operational Observability | 4/5 | 5/5 | `gate_checks` Supabase table live (RA-651); `supabase_log.py` single write path; gate pass/fail logged on every /ship phase; dashboard Quality Gate + Alert Escalations panels added. |
| Incident Response | 4/5 | 5/5 | `_watchdog_escalations()` in `cron.py` — fires every 30 min, re-pages Telegram for unacked critical alerts (RA-633); `alert_escalations` table tracks full lifecycle (sent → escalated → acked). |
| Workflow Standardization | 5/5 | 5/5 | CLAUDE.md updated for SDK-only architecture (RA-577); `.harness/config.yaml` v1.2 with full observability + CI sections (RA-580); CI `smoke-prod` job added (RA-583). |

**Issues closed this cycle:** RA-583, RA-577, RA-580, RA-633, RA-651.

**One item remaining to 75/75:** RA-641 — UPS purchase (Phill's physical action, +2 pts Infrastructure Reliability).

---

### 2026-04-12 — Cycle 21: Sprint 8 MARATHON + SDK hardening (71/75 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Trigger Automation | 5/5 | `intel_refresh` + `analyse_lessons` trigger types wired to `cron.py`; weekday gate added; `intel-refresh-monday` merged to cron-triggers.json (RA-587). 12 total triggers now active. |
| Error Recovery | 5/5 | `_watchdog_docs_staleness()` added — 48h Medium ticket if Anthropic docs snapshot goes stale; 24h cooldown prevents spam (RA-635). |
| Quality Gating | 5/5 | SDK subprocess fallback paths removed from `sessions.py`; `USE_AGENT_SDK=1` now enforces SDK-only execution — no silent degradation (RA-576). ImportError is now a fatal misconfiguration. |
| Trigger Automation | 5/5 | `PI_SEO_ACTIVE` gate in `config.py` + `cron.py`; `SCAN_PATH_EXCLUSIONS` silences SEC-1..6 documentation false positives; `_telegram_alert()` in `triage.py` sends critical findings to Telegram within 5 min (RA-586). |
| Knowledge Retention | 5/5 | lessons.jsonl: 38 entries (up from 27). Weekly Anthropic intel refresh now auto-generates board briefs on doc delta (RA-587). |
| Cost Efficiency | 5/5 | Risk Register R-02 mitigated: `scripts/fallback_dryrun.py` + quarterly cron trigger `fallback-dryrun-quarterly` (1st Jan/Apr/Jul/Oct 17:00 UTC). `day_of_month` + `month` fields added to `_matches()` (RA-634). |

**Board actions completed this cycle:** RA-576 (Done), RA-586 (In Progress — awaiting Railway env vars), RA-587 (Done), RA-634 (Done), RA-635 (Done), RA-636 (Done).

**Risk Register updated:** R-02 → **Mitigated**. Full risk register (R-01..R-08) now in `.harness/leverage-audit.md` section below.

---

### 2026-04-12 — Cycle 20: ZTE framework extension + dashboard (60→71/75)
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Framework | 60/60 | 71/75 | RA-652: Framework extended to 15 dimensions (75 max). 3 Operational Health dimensions added. |
| Infrastructure Reliability | — | 3/5 | Mac Mini sleep=off, autorestart, Ollama launchd, n8n Docker restart=always (RA-637–RA-639). UPS pending (RA-641). |
| Operational Observability | — | 4/5 | Platinum dashboard at :3001 (RA-648); Supabase event log; claude_api_costs table (RA-650). |
| Incident Response | — | 4/5 | Telegram alerting (RA-645, RA-649); Autonomy Watchdog pre-check 30-min schedule (RA-632). On-call paging pending (RA-633). |
| Trigger Automation | 5/5 | 5/5 | Pi-SEO 11-repo cron rotation live; n8n 5-min Linear poller (RA-643); Telegram /status /alerts /triage /help commands (RA-649). |
| Workflow Standardization | 5/5 | 5/5 | ENH-P0 manual-task label exempts physical tasks from autonomy poller (RA-653). AWS example key allowlist added to scanner (RA-654). |

---

### 2026-04-12 — Cycle 19: Autonomy recovery + on-call wire-up (60/60 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Trigger Automation | 5/5 | Autonomy poller recovery post 4-cycle silence (RA-610). Linear todo → In Progress promotion re-verified after RA-584 pipeline fix. |
| Error Recovery | 5/5 | Autonomy Watchdog pre-check (RA-632) guards against "0 In Progress + N Urgent" stall condition. 2h cooldown prevents alert fatigue. |
| Trigger Automation | 5/5 | On-call paging wire-up (RA-633) routes board escalations through Telegram escalation workflow (RA-645). |

---

### 2026-04-12 — Cycle 18: Autonomy watchdog deployment (60/60 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Error Recovery | 5/5 | Autonomy Watchdog pre-check deployed (RA-632) — alarms on ≥5 Urgent + 0 In Progress condition. Fires before board meeting so the CEO sees the alert at cycle start. |
| Trigger Automation | 5/5 | n8n heartbeat crons migrated from Cowork to n8n (RA-646) — removes Cowork single point of failure for scheduled heartbeats. |

---

### 2026-04-12 — Cycle 17: Poller silence diagnosis + SDK migration completion (60/60 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Trigger Automation | 5/5 | RA-584 (critical fix): Autonomy orchestrator was failing to pick up Linear Todo tickets. Pipeline `build→test→deploy` now confirmed working end-to-end. |
| Error Recovery | 5/5 | RA-605 closure: Autonomy poller coverage verified — all 6 Urgent SEC items now reachable by poller. Root cause documented. |
| Workflow Standardization | 5/5 | SDK Phase 3 complete (RA-585): `pipeline.py` + `orchestrator.py` migrated to Agent SDK. `sessions.py` generator using SDK path (RA-571). |

---

### 2026-04-11 — Sprint 8 (60/60 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Trigger Automation | 5/5 | Linear todo poller (autonomy.py) auto-promotes Urgent/High issues to sessions — no human trigger required (RA-584). Cron startup catch-up fires missed triggers on Railway restart (RA-579). |
| Error Recovery | 5/5 | Cron 12h watchdog fires Urgent Linear ticket if scheduler goes silent. CI health check fixed — no longer blocks on claude CLI availability. abs() debounce prevents future-timestamp lock (RA-579). |
| Quality Gating | 5/5 | verify_deploy.py commit parity audit added — CI can confirm git HEAD matches Vercel + Railway deployed SHAs (RA-582). |
| Workflow Standardization | 5/5 | DEPLOYMENT.md: canonical single source of truth for all production URLs, env vars, rollback procedures (RA-581). |

### 2026-04-10 — Sprint 6+7 (60/60 maintained)
| Point | Score | New Evidence |
|-------|-------|-------------|
| Spec Quality | 5/5 | Ship-chain: define-spec + technical-plan skills generate structured specs and plans (RA-543) |
| Context Precision | 5/5 | Pi-SEO findings injected into triage briefs; Telegram per-chat 20-turn history (RA-542, RA-548) |
| Tool Availability | 5/5 | 21 MCP tools (from 11); scan_project, get_project_health, ship-chain tools added (RA-540, RA-543) |
| Feedback Loops | 5/5 | Ship-chain review phase (score ≥8 gate) + Pi-SEO triage engine auto-creates Linear tickets (RA-532, RA-543) |
| Error Recovery | 5/5 | Graceful SIGTERM drain, crash-recovery loop restart, health 503 on unhealthy deps (RA-521, RA-522, RA-523) |
| Trigger Automation | 5/5 | Pi-SEO 6h scan rotation for 10 repos; Telegram /build command; ship-chain pipeline triggers (RA-539, RA-548) |
| Quality Gating | 5/5 | pytest 34-unit tests in CI; ship-chain /test phase; ship gate score ≥8 required (RA-520, RA-543) |
| Knowledge Retention | 5/5 | Pi-SEO scan-results/ historical store; ship-chain artifact persistence per pipeline ID (RA-531, RA-543) |
| Workflow Standardization | 5/5 | Ship-chain /spec /plan /build /test /review /ship enforces structured delivery for every feature (RA-543) |
| Security | 5/5 | bcrypt migration, CSP nonce, Next.js auth middleware, pytest security suite, mandatory webhook secrets (RA-515–RA-527) |

### 2026-04-08 — ZTE Sprint (50 → 60)
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Context Precision | 4 | 5 | `_get_lesson_context()` injects relevant lessons per intent into every brief |
| Model Selection | 4 | 5 | `_select_model()` reads `.harness/config.yaml` agents block; `load_config()` fixed to parse `agents` key |
| Tool Availability | 4 | 5 | Fan-out orchestrator uses opus (planner tier); failed workers escalate to opus |
| Feedback Loops | 4 | 5 | Closed-loop evaluator retry: critique → retry prompt → re-generate → re-evaluate |
| Error Recovery | 3 | 5 | Clone 3-attempt backoff (2s/4s); generator 2-attempt retry; phase checkpoints persisted |
| Session Continuity | 4 | 5 | `_should_skip()` per phase; `POST /api/sessions/{sid}/resume` resumes from checkpoint |
| Quality Gating | 4 | 5 | Evaluator is now a BLOCKING gate (not fire-and-forget) with configurable max retries |
| Knowledge Retention | 4 | 5 | `_parse_evaluator_dimensions()` extracts 4 scores; auto-appends lessons below threshold |
| Trigger Automation | 4 | 5 | `cron.py` + `.harness/cron-triggers.json` + `GET/POST/DELETE /api/triggers` + `cron_loop()` |

### 2026-04-08 — P2/P3 Sprint (41 → 50)
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Spec Quality | 3 | 5 | RA-456: PITER classifier + ADW templates; RA-457: skill injection |
| Context Precision | 3 | 4 | RA-458: CLAUDE.md fully documented |
| Feedback Loops | 3 | 4 | RA-454: evaluator tier streams scores to WebSocket |
| Quality Gating | 2 | 4 | RA-454: second Claude pass with 4-dimension scoring |
| Trigger Automation | 2 | 4 | RA-455: GitHub/Linear webhooks; RA-460: auto-brief from issues |
| Knowledge Retention | 3 | 4 | RA-457: skills loader with intent-to-skill mapping |
| Workflow Standardization | 3 | 5 | RA-456: ADW templates enforced; hotfix/bug/feature/chore/spike routing |

### 2026-04-08 — P1 Foundation Sprint (35 → 41)
| Point | Before | After | Driver |
|-------|--------|-------|--------|
| Error Recovery | 2 | 3 | RA-452: rate-limit GC prevents memory leak |
| Session Continuity | 2 | 4 | RA-450: persistence.py atomic JSON writes + startup restore |
| Knowledge Retention | 2 | 3 | RA-453: lessons.jsonl seeded + API endpoints |

### 2026-04-07 — Initial Baseline (spec.md Section 4)
Score: 35 / 60 — Assisted band. One point below Autonomous threshold.

---

## Risk Register

Operational risks tracked against the Pi-CEO pipeline. Each item maps to a ZTE dimension and a mitigation action.

| ID | Risk | Dimension | Severity | Status | Mitigation |
|----|------|-----------|----------|--------|------------|
| R-01 | Mac Mini power cut causes total outage | Infrastructure Reliability (13) | High | **Open** — UPS purchase pending (RA-641). Until UPS installed, a power cut = outage with no auto-recovery. |
| R-02 | ANTHROPIC_API_KEY expires / claude CLI unavailable | Cost Efficiency (9) | High | **Mitigated** — Quarterly dry-run via `scripts/fallback_dryrun.py` active as of 2026-04-12 (RA-634). `TAO_USE_FALLBACK=1` activates direct SDK path. Cron trigger `fallback-dryrun-quarterly` fires 1st Jan/Apr/Jul/Oct 17:00 UTC. Next run: 2026-07-01. See `DEPLOYMENT.md → Contingency: API Fallback`. |
| R-03 | Anthropic docs snapshot goes stale (intel_refresh fails silently) | Knowledge Retention (11) | Medium | **Mitigated** — 48h docs-staleness watchdog in `cron.py` creates Medium Linear ticket and fires every 30 min (RA-635). |
| R-04 | Linear poller silence — no Urgent tickets processed | Trigger Automation (10) | High | **Mitigated** — Autonomy Watchdog pre-check (RA-632) fires Telegram alert on ≥5 Urgent + 0 In Progress stall condition. 2h cooldown prevents fatigue. |
| R-05 | On-call escalation chain incomplete | Incident Response (15) | Medium | **Mitigated** — `_watchdog_escalations()` in `cron.py` re-pages Telegram after 30 min if unacked (RA-633). `alert_escalations` Supabase table tracks ack/escalated state. Full automated chain complete. |
| R-06 | Heartbeat data gap prevents observability gate | Operational Observability (14) | Low | **Mitigated** — `gate_checks` table live and logging every /ship phase result (RA-651). `supabase_log.py` is single write path. Dashboard shows Quality Gate panel + pass rate. |
| R-07 | Railway deployment drifts from git HEAD | Workflow Standardization (12) | Medium | **Mitigated** — `scripts/verify_deploy.py` compares git HEAD to Railway + Vercel deployed SHAs (RA-582). |
| R-08 | Pi-SEO triage creates false-positive Critical tickets | Incident Response (15) | Medium | **Mitigated** — `SCAN_PATH_EXCLUSIONS` silences SEC-1..6 known documentation false positives (RA-586). |
