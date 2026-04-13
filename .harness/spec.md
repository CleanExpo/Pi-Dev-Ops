# Pi Dev Ops — Product Spec (Full Analysis)

_Generated: 2026-04-08 | Last updated: 2026-04-13 (Sprint 9 complete) | Analyst: Pi CEO Orchestrator | Sprint: 9 / Cycle 24_

---

## 1. System Overview

**Pi Dev Ops** is a Zero Touch Engineering (ZTE) platform that converts a plain-English brief and a git repository URL into an executed, evaluated, and committed engineering session — entirely autonomously. It orchestrates the Claude Max subscription to perform engineering work at zero per-token cost via the `claude` CLI.

### Core Identity

- **Not CI/CD.** Not a build pipeline. It is an **agentic harness**: a thin orchestration layer between human intent and Claude Code execution.
- **Companion tool.** Designed to run alongside Claude Desktop (left pane = CLI writing code; right pane = Pi Dev Ops orchestrating, tracking, pushing to Linear).
- **ZTE v2 Score: 81/100** as of Sprint 9 / Cycle 24 — Karpathy-series enhancements complete (RA-674–683). SDK-only execution confirmed (RA-576). Full leverage-audit breakdown in `.harness/leverage-audit.md`.

### Build Pipeline

```
Human → Brief + Repo URL
         │
         ▼
POST /api/build  →  FastAPI  →  run_build()
                                    │
  Phase 1:   git clone (3-attempt exponential backoff)
  Phase 2:   workspace analysis (file listing)
  Phase 3:   Claude Code availability check (SDK path — no claude CLI)
  Phase 3.5: sandbox verification (auto re-clone if GC'd)
  Phase 4:   generator — _run_claude_via_sdk() [TAO_USE_AGENT_SDK=1 mandatory]
             └─ claude_agent_sdk with ThinkingConfigAdaptive + HookMatcher
  Phase 3.6: plan discovery (RA-679) — optional; 3 haiku variants in parallel, winner prepended
  Phase 4:   generator — _run_claude_via_sdk() [TAO_USE_AGENT_SDK=1 mandatory]
             └─ brief tier: auto/basic/detailed/advanced (RA-681) selects spec verbosity
             └─ claude_agent_sdk with ThinkingConfigAdaptive + HookMatcher
  Phase 4.5: evaluator — parallel Sonnet+Haiku, Opus tiebreaker if delta>2 (RA-553)
             └─ three-tier routing: AUTO-SHIP FAST / PASS / PASS+FLAG (RA-674)
             └─ scope check: file-count ceiling before eval loop (RA-676)
             └─ if below threshold: inject critique → retry Phase 4
             └─ if passed or exhausted: auto-append lessons to .jsonl
  Phase 5:   git push (3-attempt exponential backoff; auth → hard stop)
                                    │
                                    ▼
                           lessons.jsonl ← auto-learned from evaluator scores
                           .harness/agent-sdk-metrics/YYYY-MM-DD.jsonl ← every SDK call

Browser ← WebSocket /ws/build/{sid}  (live event stream, 150ms polling)

NOTE: claude -p subprocess paths removed in RA-576 (Sprint 8). TAO_USE_AGENT_SDK=0
      raises ImportError at startup — misconfiguration must be loud.
```

### Key Trigger Paths

| Trigger | Route | Behaviour |
|---------|-------|-----------|
| Web UI | `POST /api/build` | Manual single session |
| Fan-out | `POST /api/build/parallel` | Decomposes brief into N parallel workers |
| GitHub Push/PR | `POST /api/webhook` | HMAC-verified; auto-brief |
| Linear In-Progress | `POST /api/webhook` | Issue → structured brief |
| Cron | background `cron_loop()` | Hourly/daily repeating builds |
| MCP | `pi-ceo-server.js` tools | From Claude Desktop / CoWork |
| Telegram | `POST /api/telegram` | /build, /status, /clear commands + free-form chat |
| Ship-chain | `POST /api/spec /api/plan /api/build /api/test /api/review /api/ship` | 6-phase structured pipeline |

---

## 2. Architecture Layers

### 2.1 Web Server (`app/server/`)

| File | Responsibility | Status |
|------|---------------|--------|
| `main.py` | FastAPI app, all routes, WebSocket handler, security middleware | ✅ Complete |
| `auth.py` | Password verify, HMAC session tokens, inline rate-limit GC | ✅ Complete |
| `config.py` | All env-var config with sane defaults | ✅ Complete |
| `sessions.py` | Full build lifecycle: 5-phase pipeline, evaluator gate, phase checkpoints, resume | ✅ Complete |
| `persistence.py` | Atomic JSON session persistence (`write-to-.tmp + os.replace()`) | ✅ Complete |
| `orchestrator.py` | Fan-out parallelism: decompose → N parallel `create_session()` calls | ✅ Complete |
| `brief.py` | PITER intent classifier + 5 ADW templates + 3-tier complexity system (basic/detailed/advanced) + skill/lesson/intent-file injection (RA-678, RA-681) | ✅ Complete |
| `webhook.py` | GitHub + Linear HMAC verification, event parsing, brief generation | ✅ Complete |
| `cron.py` | Scheduled triggers (`.harness/cron-triggers.json`), 60s loop | ✅ Complete |
| `gc.py` | Workspace GC: terminal sessions >4h TTL + orphan dir scan, 30min loop | ✅ Complete |
| `lessons.py` | JSONL-backed institutional memory, `GET/POST /api/lessons` | ✅ Complete |
| `scanner.py` | Pi-SEO autonomous multi-project scanner orchestrator | ✅ Complete |
| `pipeline.py` | Ship-chain pipeline orchestrator (6 phases, artifact persistence) | ✅ Complete |
| `agents/board_meeting.py` | Full board meeting automation — 6 phases (STATUS→LINEAR→SWOT→RECS→SAVE→GAP AUDIT), runs weekly via cron | ✅ Complete |
| `autonomy.py` | Autonomous poller — polls Linear every 5min for Urgent/High issues, auto-creates build sessions. Kill switch: `TAO_AUTONOMY_ENABLED=0` | ✅ Complete |
| `budget.py` | AUTONOMY_BUDGET: maps minutes→{model, threshold, retries, timeout} via linear interpolation across 5 anchors (RA-677) | ✅ Complete |
| `vercel_monitor.py` | Vercel deployment drift: polls Deployments API v6, compares deployed SHA vs HEAD, exposes `/api/health/vercel` (RA-692) | ✅ Complete |
| `core/_chain.py` | Importable Ship Chain primitives: `generate()`, `evaluate()`, `decide()` — no async, safe for scripts (RA-682) | ✅ Complete |
| `advanced/__init__.py` | Sprint 9 enhancement layer re-exports: budget, plan_discovery, complexity (RA-682) | ✅ Complete |
| `agents/plan_discovery.py` | Plan variation discovery: 3 haiku-generated approaches scored, best prepended to generator spec (RA-679) | ✅ Complete |
| `agents/auto_generator.py` | Auto-generates `.harness/config.yaml` from repo URL + brief via complexity tier detection (RA-691) | ✅ Complete |

**Security posture:**
- `SecurityHeaders` middleware: CSP nonce-based policy (per-request), X-Frame-Options, X-XSS-Protection on every response
- CORS: explicit allowlist (`localhost:3000`, `*.vercel.app`, `*.railway.app` + env-var extension)
- Cookie: `HttpOnly`, `Secure` (cloud only), `SameSite=None` (cloud) / `Strict` (local)
- Auth: bcrypt password hash (auto-migrated from SHA-256 on first login), `hmac.compare_digest` (timing-safe). Bearer token also accepted (WS fallback)
- Rate limit: 30 req/min/IP, inline GC every 5 min, stale IP keys pruned at 120s idle
- Path traversal: `_safe_sid()` strips non-alphanumeric from session IDs before file path use
- Webhook HMAC: mandatory secrets (GITHUB_WEBHOOK_SECRET / LINEAR_WEBHOOK_SECRET hard-fail if missing); timing-safe comparison

### 2.2 TAO Engine (`src/tao/`)

The Python engine provides a skills registry, tier config loading, budget tracking, and data schemas. All actual AI execution uses the `claude_agent_sdk` Python package (SDK-only since RA-576, Sprint 8). The `claude -p` subprocess path has been removed. `TAO_USE_AGENT_SDK=1` is mandatory — setting it to 0 raises `ImportError` at startup.

| Module | Status | Purpose |
|--------|--------|---------|
| `schemas/artifacts.py` | ✅ Complete | `TaskSpec`, `TaskResult`, `Escalation` dataclasses |
| `tiers/config.py` | ✅ Complete | `TierConfig` dataclass, MODEL_MAP, YAML loader |
| `budget/tracker.py` | ✅ Complete | `BudgetTracker`: per-tier token accounting, `record(tier, tokens)` |
| `skills.py` | ✅ Complete | Skill loader/registry: frontmatter parser, `load_all_skills()`, `skills_for_intent()`, `skills_manifest()` (RA-693) |
| `agents/__init__.py` | ✅ Complete (RA-482) | `AgentDispatcher` class: intent-based routing, concurrent execution, batch dispatch, result aggregation |
| `templates/3-tier-webapp.yaml` | ✅ Present | Reference config: opus orchestrator + sonnet specialist + haiku workers |

### 2.3 Next.js Dashboard (`dashboard/`)

Deployed on Vercel at `https://pi-dev-ops.vercel.app`.

| Component | Purpose |
|-----------|---------|
| `app/(main)/dashboard/page.tsx` | Main analysis dashboard: repo input, terminal, phase tracker, results |
| `app/(main)/chat/page.tsx` | Chat interface |
| `app/(main)/history/page.tsx` | Build history |
| `app/(main)/settings/page.tsx` | Settings form |
| `app/(main)/health/page.tsx` | Pi-SEO health dashboard (10 repos, scores, findings) |
| `app/api/telegram/route.ts` | Telegram bot webhook handler (@piceoagent_bot) |
| `hooks/useSSE.ts` | SSE client for streaming events from `/api/analyze` |
| `components/Terminal.tsx` | Live terminal output renderer |
| `components/PhaseTracker.tsx` | Phase status visualiser |
| `components/ResultCards.tsx` | Result card grid (ZTE score, leverage points, etc.) |
| `components/ActionsPanel.tsx` | Post-analysis action buttons |
| `lib/types.ts` | Shared TypeScript types: `Phase`, `Session`, `AnalysisResult`, `LeveragePoint` |

### 2.4 MCP Server (`mcp/pi-ceo-server.js`)

Version 3.1.0. Built on `@modelcontextprotocol/sdk` (official subpath imports required: `sdk/server/mcp.js`, `sdk/server/stdio.js`). Total: 21 tools.

| Tool | Purpose |
|------|---------|
| `get_last_analysis` | Reads `.harness/spec.md` + `executive-summary.md` |
| `generate_board_notes` | Formats exec summary as board meeting notes |
| `get_sprint_plan` | Returns `.harness/sprint_plan.md` |
| `get_feature_list` | Returns `.harness/feature_list.json` |
| `list_harness_files` | Lists `.harness/` directory |
| `get_zte_score` | Reads `.harness/leverage-audit.md` directly (authoritative source) |
| `linear_list_issues` | Lists Pi-Dev-Ops Linear project issues |
| `linear_create_issue` | Creates a new Linear issue |
| `linear_update_issue` | Updates an existing Linear issue by identifier |
| `linear_search_issues` | Full-text search across issues |
| `linear_sync_board` | Full kanban board view (all statuses) |
| `scan_project` | Triggers Pi-SEO scan for a repo |
| `get_project_health` | Returns latest scan results + health score |
| `spec_idea` | Ship-chain: converts idea to spec.md |
| `plan_build` | Ship-chain: converts spec to implementation plan |
| `test_build` | Ship-chain: runs smoke test suite |
| `review_build` | Ship-chain: runs evaluator on build session |
| `ship_build` | Ship-chain: gate check + deploy |
| `get_pipeline` | Returns current pipeline state |
| `run_monitor_cycle` | Triggers a monitoring cycle |
| `linear_status` | Diagnostic tool for Linear connectivity |

**Dependencies:** `LINEAR_API_KEY` env var required for Linear tools. Configured in `%APPDATA%\Claude\claude_desktop_config.json`.

### 2.5 Harness State (`.harness/`)

| File | Status | Purpose |
|------|--------|---------|
| `config.yaml` | ✅ Present | Harness agent config (planner: opus, generator: sonnet, evaluator: sonnet) |
| `spec.md` | ✅ This document | Living product specification |
| `handoff.md` | ✅ Complete | Cross-session state, sprint history, architecture snapshot |
| `lessons.jsonl` | ✅ Seeded (18 entries) | Agent-expert institutional memory |
| `leverage-audit.md` | ✅ Present | ZTE audit, full changelog; current score 73/75 |
| `sprint_plan.md` | ✅ Present | Sprint history; Sprint 9 open |
| `bvi-history.jsonl` | ⬜ Pending | Business Velocity Index tracking (RA-695, from Cycle 24) |
| `feature_list.json` | ✅ Present | Feature list for MCP `get_feature_list` tool |
| `pipeline/{id}/` | ✅ Present | Ship-chain artifact store per pipeline run |
| `projects.json` | ✅ Present | Pi-SEO project registry (10 repos) |
| `scan-results/` | ✅ Present | Pi-SEO scan output per project |
| `poc-metrics/` | ✅ Present | Agent SDK PoC comparison metrics |
| `agents/planner.md` | ✅ Present | Planner agent tier 1 specification |
| `agents/evaluator.md` | ✅ Present | Evaluator agent tier 3 specification |
| `contracts/build-contract.md` | ✅ Present | Build contract spec |
| `contracts/eval-contract.md` | ✅ Present | Eval contract spec |
| `qa/smoke-test.md` | ✅ Present | Smoke test checklist (22 checks) |
| `qa/regression-checklist.md` | ✅ Present | Regression checklist |
| `templates/*.md` | ✅ Present | Feature/bugfix/chore brief templates |
| `board-meetings/` | ✅ Present | Autonomous board meeting minutes |
| `anthropic-docs/index.json` | ✅ Present | Fetched Anthropic documentation index |
| `cron-triggers.json` | ✅ Present | Cron trigger persistence (10 Pi-SEO + system crons) |
| `intent/RESEARCH_INTENT.md` | ✅ Present | Strategic steering: ZTE targets, sprint goals (RA-678) |
| `intent/ENGINEERING_CONSTRAINTS.md` | ✅ Present | Hard invariants: endpoint SLAs, lint gate, file budgets (RA-678) |
| `intent/EVALUATION_CRITERIA.md` | ✅ Present | Raised thresholds, zero-tolerance list, lesson policy (RA-678) |
| `plan-discoveries/` | ✅ Present | Plan variation JSONL logs — one file per day (RA-679) |
| `remediation/` | ✅ Present | Per-repo remediation specs — CCW-CRM quality fix brief (RA-690) |
| `agent-sdk-metrics/` | ✅ Present | SDK invocation metrics per day (latency, success, model) |

---

## 3. Skills Analysis (33 of 33)

### Layer 1: Core (7 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `tier-architect` | Design model-to-role tier hierarchy | Partial | `.harness/config.yaml` partially implements |
| `tier-orchestrator` | Top-tier planning + delegation patterns | ✅ | `orchestrator.py` fan-out pattern + brief decomposition |
| `tier-worker` | Discrete execution, escalation rules | ✅ | `run_build()` workers; escalation via opus fallback |
| `tier-evaluator` | QA grading with 4 dimensions | ✅ | Phase 4.5 in `sessions.py`; `evaluator.md` spec |
| `context-compressor` | Truncate/extract/summarize at tier boundaries | Partial | `build_structured_brief()` truncates skill bodies to 800 chars |
| `token-budgeter` | Track token spend per tier | Partial | `BudgetTracker` instantiated per session |
| `auto-generator` | Generate tier configs from project briefs | ✅ | `agents/auto_generator.py` — keyword complexity classifier → config.yaml written to pipeline artifact (RA-691) |

### Layer 2: Frameworks (6 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `piter-framework` | 5-pillar AFK setup | ✅ | `classify_intent()` + 5 ADW templates enforced at brief entry |
| `afk-agent` | Bounded unattended runs with stop guards | ✅ | Phase pipeline has explicit success/failure termination |
| `closed-loop-prompt` | Self-correcting prompts with embedded verification | ✅ | Evaluator critique injected into retry prompt |
| `hooks-system` | 6 lifecycle hooks for observability + safety | Partial | PreToolUse (rate limit), PostToolUse (logging) |
| `agent-workflow` | 5 ADW templates | ✅ | Full templates in `brief.py`, routes all 5 intent types |
| `agentic-review` | 6-dimension quality review | ✅ | Evaluator covers 4 of 6 dimensions |

### Layer 3: Strategic (5 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `zte-maturity` | 3-level maturity model | ✅ | 60/60 achieved; Level 3 ZTE |
| `agent-expert` | Act-Learn-Reuse cycle | ✅ | Auto-learns from evaluator → `lessons.jsonl` → injected in next brief |
| `leverage-audit` | 12-point diagnostic | ✅ | `leverage-audit.md` maintained and read by MCP `get_zte_score` |
| `agentic-loop` | Two-prompt infinite loop | ✅ | Up to 3 evaluator rounds (max_iterations respected) |
| `agentic-layer` | Dual-interface design | Partial | Machine-readable JSON API exists |

### Layer 4: Foundation (3 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `big-three` | Model/Prompt/Context debugging | Partial | Model selection wired; prompt templating via ADW; context injection partial |
| `claude-max-runtime` | Tier mapping for Max subscription | ✅ | Tier mapping matches config.yaml; zero API cost |
| `pi-integration` | Multi-provider bridge | ✅ | Documented as contingency; not needed on Max plan |

### Meta (2 skills)

| Skill | Status |
|-------|--------|
| `ceo-mode` | ✅ Active |
| `tao-skills` | ✅ Master index (31 skills) |

### Layer 5: Content + Design (2 skills) — RA-693

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `brand-ambassador` | Brand-consistent copy, product descriptions, release notes | ✅ | `skills_for_intent("content")` — backed by `anthropic-skills:brand-ambassador` |
| `design-system` | Next.js 16 + Tailwind component system scaffolding | ✅ | `skills_for_intent("design")` — backed by `anthropic-skills:design-system-to-production-quick-start` |

### Layer 6: Pi-SEO (3 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `pi-seo-security` | OWASP Top 10 + secret detection | ✅ | scanner.py skill orchestration |
| `pi-seo-deployment` | Vercel Sandbox audit + Core Web Vitals | ✅ | scanner.py |
| `pi-seo-dependencies` | npm/pip CVE + outdated packages | ✅ | scanner.py |

### Layer 7: Ship Chain (5 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `ship-chain` | Orchestrates all 6 phases, routing + gate checks | ✅ | `pipeline.py` + 7 MCP tools |
| `define-spec` | Converts raw idea → structured spec.md | ✅ | `POST /api/spec` |
| `technical-plan` | Converts spec → implementation plan | ✅ | `POST /api/plan` |
| `verify-test` | Interprets test results, identifies gaps | ✅ | `POST /api/test` |
| `ship-release` | Release gate (score ≥8) + ship log | ✅ | `POST /api/ship` |

---

## 4. Current Leverage Audit (ZTE v2: 81/100 — Zero Touch)

| # | Point | Score | Evidence |
|---|-------|-------|---------|
| 1 | Spec Quality | 5/5 | PITER + 5 ADW templates + 3-tier complexity (basic/detailed/advanced) + intent file injection (RA-456, RA-678, RA-681) |
| 2 | Context Precision | 5/5 | Lesson context + intent files (RESEARCH_INTENT, ENGINEERING_CONSTRAINTS, EVALUATION_CRITERIA) injected per-brief |
| 3 | Model Selection | 5/5 | `_select_model()` + AUTONOMY_BUDGET linear interpolation across 5 anchors (RA-677) |
| 4 | Tool Availability | 5/5 | Full Claude Code suite + fan-out + opus escalation + plan discovery (RA-679) |
| 5 | Feedback Loops | 5/5 | Closed-loop evaluator + confidence routing (RA-674) + lesson injection; plan discovery self-improves after 50 runs |
| 6 | Error Recovery | 5/5 | Clone/generator/push 3-attempt backoff; scope enforcement before eval (RA-676); phase checkpoints + resume |
| 7 | Session Continuity | 5/5 | Phase-level checkpoints; `POST /api/sessions/{sid}/resume` |
| 8 | Quality Gating | 5/5 | Three-tier evaluator (AUTO-SHIP FAST / PASS / PASS+FLAG) + scope contract ceiling (RA-674, RA-676) |
| 9 | Cost Efficiency | 5/5 | Zero API cost on Claude Max; haiku for plan discovery + scoring to minimise token spend |
| 10 | Trigger Automation | 5/5 | GitHub + Linear webhooks + cron + Telegram + Pi-SEO scan rotation + autonomy poller |
| 11 | Knowledge Retention | 5/5 | lessons.jsonl + plan-discoveries JSONL + RESEARCH_INTENT.md pattern proposals (RA-679) |
| 12 | Workflow Standardisation | 5/5 | PITER + all 5 ADW templates + ship-chain pipeline + 33 skills |
| 13 | Observability | 4/5 | gate_checks + alert_escalations in Supabase; ZTE v2 score; SDK metrics; Vercel drift monitoring (RA-692) |
| 14 | External Validation | 3/5 | ZTE v2 Section C live; C2/C3 data pending (RA-672 Phase 2) |
| 15 | Incident History RAG | 5/5 | `_build_incident_context()` injects lessons.jsonl into every generator prompt (RA-660) |

**ZTE v2: 81/100 — Zero Touch band** _(v2 target: 90/100 by end Cycle 25; Elite threshold: 95)_  
**ZTE v1: 75/75** _(all 15 leverage points at full score)_

---

## 5. Sprint History

### Baseline (2026-04-07) — 35/60 Assisted
Initial analysis. Sessions in-memory, no GC, no evaluator, no webhooks, no lessons.

### Sprint 1 — Foundation (2026-04-07) | 35 → 41/60
RA-449 MCP v3.0.0, RA-450 session persistence, RA-451 workspace GC, RA-452 rate-limit GC, RA-453 lessons.jsonl seeded, RA-458 CLAUDE.md, RA-459 security.

### Sprint 2 + ZTE Sprint (2026-04-08) | 41 → 60/60
RA-454 evaluator tier, RA-455 webhooks, RA-456 PITER+ADW, RA-457 skills loader, RA-460 Linear auto-brief, RA-461/462 leverage audit, RA-463 harness dirs, RA-464 fan-out, RA-465 TAO wire-up, RA-466 docs pull cron, RA-467 autonomous board meetings, RA-468 sandbox enforcement. ZTE sprint: lesson injection, closed-loop evaluator retry, phase checkpoints, clone/generator retry, auto-learn, cron triggers.

### Sprint 3 — Validation (2026-04-08) | 60/60 maintained
RA-469 MCP `get_zte_score` reads `leverage-audit.md` + `feature_list.json`, RA-470 E2E smoke test 22/22 passes + PITER priority bug fixed, RA-471 push retry 3-attempt backoff, RA-472 handoff.md.

### Sprint 5 — Security + Agent SDK (2026-04-09)
RA-489–RA-527: bcrypt auth, CSP nonce policy, Next.js auth middleware, pytest suite (34 tests), graceful shutdown, crash recovery, health check hardening, CI expansion (TypeScript + lint). RA-485: Claude Agent SDK PoC (board-meeting agent, parallel 14-cycle comparison run).

### Sprint 6 — Pi-SEO + Ship-Chain (2026-04-10)
RA-531–RA-542: Pi-SEO scanner epic — project registry, autonomous scanner, triage engine, 3 scanner skills (security/deployment/dependencies), auto-PR, health dashboard, scan crons, MCP tools, Vercel Sandbox snapshot. RA-543: Ship-chain pipeline (/spec /plan /build /test /review /ship) — 5 skills, 5 API endpoints, 7 MCP tools.

### Sprint 7 — Mobile + Telegram (2026-04-10)
RA-546: Mobile/tablet responsive layout (bottom tab bar, iOS zoom fix). RA-547: Worktree isolation fix (.claude/settings.json hooks). RA-548: @piceoagent_bot Telegram webhook integration. RA-549: claude-code-telegram agentic bot deployed to Railway.

### Sprint 9 — Karpathy Enhancement Layer (2026-04-13) | ZTE v2: 81/100
RA-674: Confidence-weighted evaluator with three-tier routing (AUTO-SHIP FAST / PASS / PASS+FLAG). RA-676: Session Scope Contract — file-count ceiling enforced before eval, Telegram alert on violation. RA-677: AUTONOMY_BUDGET single-knob — maps budget_minutes → model/threshold/retries/timeout via 5-anchor linear interpolation. RA-678: Markdown intent architecture — RESEARCH_INTENT.md + ENGINEERING_CONSTRAINTS.md + EVALUATION_CRITERIA.md injected per-brief. RA-679: Plan variation discovery — 3 haiku-generated approaches scored in parallel, winner prepended to generator spec; logs to .harness/plan-discoveries/. RA-680: Pi-CEO Essentials — 268-line standalone Ship Chain reference (zero deps). RA-681: Progressive brief complexity — auto-classifies basic/detailed/advanced, adjusts spec verbosity and quality gate tier. RA-682: Layered abstraction — app/server/core/ (primitives) + app/server/advanced/ (enhancements). RA-683: Ship Chain Educational Series — 5-doc Karpathy-10 onboarding in docs/ship-chain/. RA-688: Dependency zero-score alerting in pi_seo_monitor.py — flags repos at 0/100 for 2+ cycles. RA-690: CCW-CRM quality remediation spec (50 ruff findings documented). RA-691: auto_generator.py — auto-generates config.yaml from project complexity keyword detection. RA-692: vercel_monitor.py — deployment drift detection via Vercel Deployments API. RA-693: brand-ambassador + design-system skill stubs + skills_manifest() added to skills registry.

### Sprint 8 — Observability + ZTE v2 (2026-04-12 → 2026-04-13)
RA-576: SDK-only execution locked in (subprocess fallback removed). RA-651: gate_checks Supabase table — quality gate telemetry on every /ship. RA-633: Critical alert escalation chain (Telegram → 30-min watchdog → second page). RA-652: ZTE framework extended to 75-point v1 scale (leverage-audit.md). RA-659: Adaptive Thinking via `ThinkingConfigAdaptive` in SDK options. RA-660: Incident history RAG — `_build_incident_context()` injects lessons.jsonl into generator prompt. RA-661: ZTE v2 framework spec (100-point scale, Section C external validation). RA-662: SDK hooks for latency observability (`HookMatcher` pre/post tool timing). RA-665/666: Linear two-way sync — build outcome + score posted back as Linear comment on completion or failure. RA-672: ZTE v2 data collection — `push_timestamp` and `session_started_at` in gate_checks; `scripts/zte_v2_score.py` computes C1–C5 live; board meeting Phase 1 surfaces v2 score. RA-673: Pi-SEO scanner false positive fix (16,042 → 128 findings); `PI_SEO_ACTIVE=1` deployed to Railway.

---

## 6. Sprint 9 Complete + Sprint 10 Direction

### Sprint 9 — Complete (2026-04-13)
Full Karpathy enhancement layer shipped (RA-674–683). ZTE v2 score: 81/100. Three-tier confidence routing, AUTONOMY_BUDGET single-knob, Session Scope Contract, plan variation discovery, progressive brief complexity, layered abstraction, educational series, dependency alerting, Vercel drift monitoring, skills manifest. All 14 Sprint 9 tickets closed. 10 commits pushed to origin/main.

### Sprint 9 — Complete (2026-04-13)

| Ticket | Item | Status |
|--------|------|--------|
| RA-674 | Confidence-weighted evaluator + three-tier routing | ✅ Done |
| RA-676 | Session Scope Contract — file-count ceiling + Telegram alert on violation | ✅ Done |
| RA-677 | AUTONOMY_BUDGET single-knob pipeline config (5 anchor interpolation) | ✅ Done |
| RA-678 | Markdown intent architecture (RESEARCH_INTENT + ENGINEERING_CONSTRAINTS + EVALUATION_CRITERIA) | ✅ Done |
| RA-679 | Plan variation discovery loop (3 haiku variants, scored, winner prepended) | ✅ Done |
| RA-680 | Pi-CEO Essentials — 268-line standalone Ship Chain reference (`scripts/pi_essentials.py`) | ✅ Done |
| RA-681 | Progressive brief complexity — BasicBrief/DetailedBrief/AdvancedBrief auto-detection | ✅ Done |
| RA-682 | Layered abstraction — `core/` + `advanced/` importable sub-packages | ✅ Done |
| RA-683 | Ship Chain Educational Series — 5 docs, Karpathy-10 nn-zero-to-hero style | ✅ Done |
| RA-688 | Dependency zero-score alerting — flags repos stuck at 0/100 for 2+ scan cycles | ✅ Done |
| RA-690 | CCW-CRM quality remediation spec — 50 ruff findings documented, build brief generated | ✅ Done |
| RA-691 | Auto-generator skill — `auto_generator.py` writes config.yaml from repo complexity tier | ✅ Done |
| RA-692 | Vercel deployment drift monitoring — `vercel_monitor.py` + `/api/health/vercel` | ✅ Done |
| RA-693 | brand-ambassador + design-system skills + `skills_manifest()` | ✅ Done |
| RA-588 | MARATHON-4: 6-hour autonomous self-maintenance run | ⏳ Awaiting Phill initiation |
| RA-687 | 3 CRITICAL security alerts — dr-nrpg + synthex manual inspection required | ⏳ Phill manual action |

---

## 7. File Map (Current State)

```
Pi Dev Ops/
├── app/
│   ├── Dockerfile                      ← Cloud deployment (Railway/Render)
│   ├── requirements.txt                ← Python deps
│   ├── run.ps1                         ← Windows launcher (pip install + uvicorn)
│   └── server/
│       ├── main.py                     ← FastAPI app, routes, WebSocket, security
│       ├── auth.py                     ← HMAC tokens, inline rate-limit GC
│       ├── config.py                   ← All env-var config (TAO_PASSWORD etc.)
│       ├── sessions.py                 ← Build lifecycle, 5-phase pipeline, evaluator
│       ├── persistence.py              ← Atomic JSON session persistence
│       ├── orchestrator.py             ← Fan-out parallelism (POST /api/build/parallel)
│       ├── brief.py                    ← PITER classifier + ADW templates + injection
│       ├── webhook.py                  ← GitHub + Linear HMAC + event parsing
│       ├── cron.py                     ← Scheduled triggers + cron_loop()
│       ├── gc.py                       ← Workspace GC (4h TTL, 30min loop)
│       ├── lessons.py                  ← JSONL lessons CRUD
│       ├── scanner.py                  ← Pi-SEO autonomous multi-project scanner
│       ├── pipeline.py                 ← Ship-chain pipeline orchestrator
│       ├── budget.py                   ← AUTONOMY_BUDGET: minutes→params interpolation (RA-677)
│       ├── vercel_monitor.py           ← Vercel deployment drift check (RA-692)
│       ├── core/                       ← Importable Ship Chain primitives (RA-682)
│       │   └── _chain.py               ← generate(), evaluate(), decide() — no async
│       ├── advanced/                   ← Sprint 9 enhancement layer re-exports (RA-682)
│       └── agents/
│           ├── board_meeting.py        ← Board meeting agent (SDK-only, Adaptive Thinking, HookMatcher)
│           ├── plan_discovery.py       ← Plan variation discovery: 3 variants, scored (RA-679)
│           └── auto_generator.py       ← Auto-generates config.yaml from complexity tier (RA-691)
│   ├── static/index.html               ← Minimal frontend
│   └── workspaces/                     ← Ephemeral session clones (GC'd at 4h)
│       └── {session_id}/               ← Isolated clone per session
├── dashboard/                          ← Next.js (Vercel-deployed)
│   ├── app/(main)/dashboard/page.tsx   ← Main dashboard
│   ├── app/(main)/chat/page.tsx        ← Chat interface
│   ├── app/(main)/history/page.tsx     ← Build history
│   ├── app/(main)/settings/page.tsx    ← Settings
│   ├── app/(main)/health/page.tsx      ← Pi-SEO health dashboard (10 repos)
│   ├── app/api/                        ← Next.js API routes (proxy to backend)
│   ├── app/api/telegram/route.ts       ← Telegram bot webhook handler
│   ├── components/                     ← Terminal, PhaseTracker, ResultCards, ActionsPanel
│   ├── hooks/useSSE.ts                 ← SSE client for streaming events
│   └── lib/types.ts                    ← Shared TypeScript types
├── mcp/
│   └── pi-ceo-server.js               ← MCP v3.1.0 (21 tools, Linear + harness reads)
├── skills/ (33 skills)
│   ├── [core: 7]    tier-architect, tier-orchestrator, tier-worker,
│   │                tier-evaluator, context-compressor, token-budgeter, auto-generator
│   ├── [fw: 6]      piter-framework, afk-agent, closed-loop-prompt,
│   │                hooks-system, agent-workflow, agentic-review
│   ├── [strat: 5]   zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer
│   ├── [found: 3]   big-three, claude-max-runtime, pi-integration
│   ├── [meta: 2]    ceo-mode, tao-skills (master index)
│   ├── [content+design: 2] brand-ambassador, design-system   ← NEW RA-693
│   ├── [pi-seo: 3]  pi-seo-security/, pi-seo-deployment/, pi-seo-dependencies/
│   └── [ship: 5]    ship-chain/, define-spec/, technical-plan/, verify-test/, ship-release/
├── src/tao/
│   ├── skills.py                       ← Skill loader/registry, intent-to-skill mapping
│   ├── schemas/artifacts.py            ← TaskSpec, TaskResult, Escalation dataclasses
│   ├── tiers/config.py                 ← TierConfig, MODEL_MAP, YAML loader
│   ├── budget/tracker.py               ← BudgetTracker (per-tier token accounting)
│   ├── agents/__init__.py              ← AgentDispatcher (intent routing, batch dispatch)
│   └── templates/3-tier-webapp.yaml    ← Reference 3-tier config (opus/sonnet/haiku)
├── supabase/migration.sql              ← DB schema (if Supabase integration active)
├── docs/ship-chain/                    ← Educational series (RA-683)
│   ├── 00-index.md                     ← Series map
│   ├── 01-the-algorithm.md             ← Five pure functions with code examples
│   ├── 02-intent-classification.md     ← PITER, ADW templates, complexity tiers
│   ├── 03-the-evaluator.md             ← Scoring, confidence routing, retry loop
│   ├── 04-karpathy-optimisations.md    ← All Sprint 9 enhancements
│   └── 05-running-the-system.md        ← Dev setup, env vars, first build
├── scripts/
│   ├── analyze.sh                      ← Analysis helper script
│   ├── fetch_anthropic_docs.py         ← Daily docs pull (cron at 5:50am AEST)
│   ├── zte_v2_score.py                 ← ZTE v2 Section C scorer (RA-672)
│   ├── sdk_metrics.py                  ← SDK invocation metrics analyser
│   └── pi_essentials.py                ← 268-line standalone Ship Chain reference (RA-680)
├── .harness/
│   ├── config.yaml                     ← Harness agent config (planner/generator/evaluator)
│   ├── spec.md                         ← This document (living specification)
│   ├── handoff.md                      ← Cross-session state (Sprint 8 complete)
│   ├── leverage-audit.md               ← ZTE score 73/75 + full changelog
│   ├── sprint_plan.md                  ← Sprint 8 complete; Sprint 9 open
│   ├── zte-framework-v2.md             ← ZTE v2 100-point spec (RA-661)
│   ├── zte-v2-score.json               ← Latest live v2 score (written by zte_v2_score.py)
│   ├── lessons.jsonl                   ← Institutional memory (append-only JSONL)
│   ├── feature_list.json               ← Feature list for MCP
│   ├── pipeline/                       ← Ship-chain artifact store per pipeline run
│   ├── projects.json                   ← Pi-SEO project registry (10 repos)
│   ├── scan-results/                   ← Pi-SEO scan output per project
│   ├── poc-metrics/                    ← Agent SDK PoC comparison metrics
│   ├── agents/
│   │   ├── planner.md                  ← Planner agent (Tier 1 Opus) spec
│   │   ├── generator.md                ← Generator agent (Tier 2 Sonnet) spec
│   │   └── evaluator.md                ← Evaluator agent (Tier 3 Sonnet) spec
│   ├── contracts/
│   │   ├── build-contract.md           ← Build contract
│   │   └── eval-contract.md            ← Evaluation contract
│   ├── qa/
│   │   ├── smoke-test.md               ← 22-check smoke test (all passing, RA-470)
│   │   └── regression-checklist.md    ← Regression checklist
│   ├── templates/
│   │   ├── feature-brief.md            ← Feature brief template
│   │   ├── bugfix-brief.md             ← Bug fix brief template
│   │   └── chore-brief.md              ← Chore brief template
│   ├── board-meetings/                 ← Autonomous board meeting minutes
│   └── anthropic-docs/index.json       ← Fetched Anthropic docs index
├── _deploy.py                          ← Bootstrap script (regenerates all files)
├── pyproject.toml                      ← Python project metadata + deps
├── vercel.json                         ← Vercel deployment config
└── README.md                          ← Public README
```

---

## 8. Design Decisions (CEO Mode)

**Why Claude Agent SDK instead of `claude -p` subprocess?** (RA-576, Sprint 8 — completed)
The `claude_agent_sdk` Python package replaced the subprocess path entirely. SDK execution provides structured event streaming, `ThinkingConfigAdaptive` for extended reasoning, `HookMatcher` for latency observability, and avoids shell escaping hazards. The zero-cost advantage under Claude Max is preserved. `TAO_USE_AGENT_SDK=1` is now mandatory — setting it to 0 raises `ImportError` at startup (deliberate: misconfiguration must be loud). API fallback via `TAO_USE_FALLBACK=1` activates direct Anthropic Python SDK (no claude CLI). Test quarterly via `python scripts/fallback_dryrun.py`.

**Why JSONL for lessons?**
JSONL is append-only and atomic at the OS buffer level for a single-process server. Each lesson is one line — no lock needed, no corruption risk. `load_lessons(category=intent)` is O(N) over a small file — acceptable until the file exceeds ~10MB.

**Why atomic writes for session persistence?**
`write-to-.tmp + os.replace()` prevents corrupt session JSON files on crash or power loss. `os.replace()` is atomic on both NTFS and POSIX. Non-fatal on failure — a persistence error should never crash the build.

**Why keyword-based PITER classification?**
A brief ML classifier would be overkill for 5 categories. The keyword matching is deterministic, zero-cost, and the ordering (hotfix first, feature last) handles the ambiguity between broad keywords. The unit tests in RA-470 cover the priority ordering edge cases.

**Why in-memory `_sessions` dict with file backup?**
The use case is a solo developer on a single machine with low session volume. A full database adds operational overhead (schema migration, connection pooling) for marginal gain. The JSON file backup via `persistence.py` provides the important properties: survive restarts, mark interrupted sessions. The trade-off is no concurrent multi-server deployment.

**Why WebSocket instead of SSE for build output?**
WebSocket is bidirectional — the client can send `ping` frames and the server can terminate cleanly. SSE would also work but WS was chosen for its explicit connection lifecycle management.

---

## 9. Next Actions (Sprint 10 — Cycle 24)

### Immediately Actionable (Phill)
```
[ ] RA-587 MARATHON-4: Initiate 6-hour autonomous self-maintenance run
    → All blockers cleared. Server running. Autonomy poller armed.

[ ] RA-687 URGENT: Inspect dr-nrpg + synthex repos manually
    → 3 CRITICAL security alerts (AWS keys, OpenAI key) — cannot be auto-remediated
    → Pi-CEO can build the fix once you confirm the findings
```

### Sprint 10 — Open (Autonomy Poller will pick up)
```
[ ] ZTE v2 C2/C3: deploy RA-672 Phase 2 migration (Linear state-transition logging)
    → Unlocks push_timestamp data → C2 acceptance rate + C3 mean-time-to-value
    → Worth +6 ZTE v2 points (81 → 87)

[ ] CCW-CRM quality fix: trigger Pi-CEO build session for CleanExpo/CCW-CRM
    → Brief in .harness/remediation/ccw-crm-quality-2026-04-13.md
    → 50 ruff violations → target 90/100

[ ] BVI baseline Cycle 24: compute first Business Velocity Index snapshot
    → Primary board metric from Cycle 24 (RA-695 done, metric definition ready)
```

### ZTE v2 Roadmap
```
Current:  81/100 (Zero Touch band)
Target:   90/100 by end Cycle 25
Elite:    95/100

Key blockers:
  C2 acceptance rate  (+3 pts) — needs RA-672 Phase 2
  C3 mean-time-to-value (+3 pts) — needs push_timestamp data
  C4 security posture  (+3 pts) — needs RA-687 resolution
  Remaining +3 pts    — general build throughput data
```

### Strategic Context
- **Primary metric Cycle 24+:** Business Velocity Index (BVI), not ZTE score
- **ZTE 81/100** is background health; BVI leads every board report
- **Security gate:** dr-nrpg + synthex must reach 80/100 before any new feature epics
- **Karpathy series:** RA-674–683 all complete. Enhancement layer stable.
