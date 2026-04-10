# Pi Dev Ops — Leverage Audit

## Current Score: 60 / 60 — Zero Touch Band

*Last updated: 2026-04-11 (Sprint 8 — Cycle 15)*

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
| 9 | Cost Efficiency | 5 | Zero API cost on Claude Max plan |
| 10 | Trigger Automation | 5 | GitHub + Linear webhooks + cron triggers (`GET/POST/DELETE /api/triggers`) |
| 11 | Knowledge Retention | 5 | Auto-learn: evaluator low-scoring dimensions → lessons.jsonl; injected in briefs |
| 12 | Workflow Standardization | 5 | PITER classifier enforced at brief entry; all 5 ADW templates active (RA-456) |

**Total: 60 / 60**

### Band Thresholds
- **Manual (1-20):** Human drives every step
- **Assisted (21-35):** AI helps but human orchestrates
- **Autonomous (36-55):** AI orchestrates, human reviews
- **Zero Touch (56-60):** Fully autonomous pipeline

---

## Changelog

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
