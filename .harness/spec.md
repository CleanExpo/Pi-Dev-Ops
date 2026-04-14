# Pi Dev Ops — Product Spec

_Last updated: 2026-04-14 (Sprint 11) | ZTE v2: 84/100_

---

## 1. System Overview

**Pi Dev Ops** is a Zero Touch Engineering (ZTE) platform that converts a plain-English brief and a git repository URL into an executed, evaluated, and committed engineering session autonomously. It orchestrates the Claude Max subscription via the `claude_agent_sdk` Python package at zero per-token cost.

**Core identity:**
- Not CI/CD. An **agentic harness**: thin orchestration between human intent and Claude Code execution.
- Companion tool. Left pane = Claude Desktop writing code; right pane = Pi Dev Ops orchestrating, tracking, pushing to Linear.
- `TAO_USE_AGENT_SDK=1` is mandatory — `0` raises `ImportError` at startup.

### Build Pipeline

```
Human → Brief + Repo URL
         │
         ▼
POST /api/build  →  FastAPI  →  run_build()
                                    │
  Phase 1:   git clone (3-attempt exponential backoff)
  Phase 2:   workspace analysis
  Phase 3:   SDK availability check; sandbox verification (auto re-clone if GC'd)
  Phase 3.6: plan discovery — 3 haiku variants in parallel, winner prepended (RA-679)
  Phase 4:   generator — _run_claude_via_sdk() [TAO_USE_AGENT_SDK=1 mandatory]
             └─ brief tier: auto/basic/detailed/advanced (RA-681)
             └─ ThinkingConfigAdaptive + HookMatcher
  Phase 4.5: evaluator — parallel Sonnet+Haiku, Opus tiebreaker if delta>2 (RA-553)
             └─ three-tier routing: AUTO-SHIP FAST / PASS / PASS+FLAG (RA-674)
             └─ scope check: file-count ceiling before eval loop (RA-676)
             └─ below threshold: inject critique → retry Phase 4
  Phase 5:   git push (3-attempt backoff; auth failure → hard stop)
                                    │
                                    ▼
                           lessons.jsonl ← auto-learned from evaluator scores
                           .harness/agent-sdk-metrics/YYYY-MM-DD.jsonl ← every SDK call

Browser ← SSE /api/analyze (live event stream)
```

### Trigger Paths

| Trigger | Route | Behaviour |
|---------|-------|-----------|
| Web UI | `POST /api/build` | Manual single session |
| Fan-out | `POST /api/build/parallel` | Decomposes brief → N parallel workers |
| GitHub Push/PR | `POST /api/webhook` | HMAC-verified; auto-brief |
| Linear In-Progress | `POST /api/webhook` | Issue → structured brief |
| Cron | background `cron_loop()` | Hourly/daily repeating builds |
| Autonomy | `autonomy.py` 5-min poll | Urgent/High Todo Linear issues → auto-session |
| MCP | `pi-ceo-server.js` tools | From Claude Desktop |
| Telegram | `POST /api/telegram` | /build, /status, /clear + free-form chat |
| Ship-chain | `/api/spec /plan /build /test /review /ship` | 6-phase structured pipeline |

---

## 2. Architecture

### 2.1 Backend (`app/server/`)

Decomposed into focused modules ≤300L each (RA-937). Public contract: `app.server.main:app` is the FastAPI instance — Dockerfile and Railway both reference it.

**Assembler + Factory**

| File | Lines | Responsibility |
|------|-------|---------------|
| `main.py` | ~25 | Thin assembler — imports `app`, registers all routers. Only file Dockerfile sees. |
| `app_factory.py` | ~130 | `app` object, CORS/SecurityHeaders middleware, `_resilient`, startup/shutdown hooks |
| `models.py` | ~126 | All Pydantic request models (BuildRequest, TriggerRequest, ScanRequest, etc.) |

**Route Modules (`routes/`)**

| File | Lines | Endpoints |
|------|-------|-----------|
| `routes/auth.py` | ~48 | `POST /api/login`, `POST /api/logout`, `GET /api/me` |
| `routes/sessions.py` | ~122 | `/api/build`, `/api/build/parallel`, session list/kill/logs/resume |
| `routes/webhooks.py` | ~214 | `POST /api/webhook` (GitHub+Linear), morning-intel, Telegram |
| `routes/triggers.py` | ~32 | Trigger CRUD (`GET/POST/DELETE /api/triggers`) |
| `routes/scan_monitor.py` | ~111 | `/api/scan`, `/api/projects/health`, `/api/monitor`, `/api/monitor/digest` |
| `routes/pipeline.py` | ~89 | `/api/spec`, `/api/plan`, `/api/test`, `/api/ship`, `/api/pipeline/{id}` |
| `routes/utils.py` | ~68 | `/api/gc`, `/api/lessons`, `/api/autonomy/status`, WebSocket `/ws/build/{sid}` |
| `routes/health.py` | ~125 | `/health`, `/api/health/vercel`, Claude CLI poll, static mount |

**Core Modules**

| File | Responsibility |
|------|---------------|
| `auth.py` | bcrypt password verify, HMAC session tokens, rate-limit GC |
| `config.py` | All env-var config; `TAO_PASSWORD` always rehashes on startup if set |
| `sessions.py` | Full build lifecycle: 5-phase pipeline, evaluator gate, disk persistence |
| `orchestrator.py` | Fan-out parallelism: decompose → N parallel `create_session()` calls |
| `brief.py` | PITER classifier + 5 ADW templates + 3-tier complexity + skill/lesson injection |
| `webhook.py` | GitHub + Linear HMAC verification, event parsing, brief generation |
| `cron.py` | Scheduled triggers (`.harness/cron-triggers.json`), 60s loop |
| `gc.py` | Workspace GC: terminal sessions >4h TTL + orphan dir scan, 30min loop |
| `lessons.py` | JSONL-backed institutional memory, `GET/POST /api/lessons` |
| `scanner.py` | Pi-SEO autonomous multi-project scanner orchestrator |
| `pipeline.py` | Ship-chain pipeline orchestrator (6 phases, artifact persistence) |
| `autonomy.py` | Polls Linear every 5min for Urgent/High **Todo** issues → auto-creates sessions |
| `budget.py` | AUTONOMY_BUDGET: maps minutes→{model, threshold, retries, timeout} (RA-677) |
| `vercel_monitor.py` | Vercel deployment drift: Deployments API v6, exposes `/api/health/vercel` |
| `agents/board_meeting.py` | Board meeting automation — 6 phases, weekly via cron |
| `agents/plan_discovery.py` | Plan variation discovery: 3 haiku variants scored, best prepended (RA-679) |
| `agents/auto_generator.py` | Auto-generates config.yaml from project complexity tier (RA-691) |
| `core/_chain.py` | Importable Ship Chain primitives: `generate()`, `evaluate()`, `decide()` |

**Security posture:**
- CSP nonce-based policy per request; X-Frame-Options; X-XSS-Protection
- CORS: explicit allowlist (`localhost:3000`, `*.vercel.app`, `*.railway.app` + env extension)
- Cookie: `HttpOnly`, `Secure` (cloud), `SameSite=None` (cloud) / `Strict` (local)
- Auth: bcrypt (auto-migrated from SHA-256 on first login); `hmac.compare_digest` timing-safe
- Rate limit: 30 req/min/IP; inline GC every 5 min
- Path traversal: `_safe_sid()` strips non-alphanumeric from session IDs

### 2.2 TAO Engine (`src/tao/`)

SDK-only since RA-576. `claude -p` subprocess path removed. All intelligence delegated to `claude_agent_sdk`.

| Module | Purpose |
|--------|---------|
| `schemas/artifacts.py` | `TaskSpec`, `TaskResult`, `Escalation` dataclasses |
| `tiers/config.py` | `TierConfig`, MODEL_MAP, YAML loader |
| `budget/tracker.py` | `BudgetTracker`: per-tier token accounting |
| `skills.py` | Skill loader/registry: frontmatter parser, intent-to-skill mapping, `skills_manifest()` |
| `agents/__init__.py` | `AgentDispatcher`: intent routing, concurrent execution, batch dispatch |

### 2.3 Dashboard (`dashboard/`)

Deployed on Vercel at `https://pi-dev-ops.vercel.app`. Analysis mode: `ANALYSIS_MODE=api` in Vercel env with Max plan subscription token (`sk-ant-oat01-*`). `ANALYSIS_MODE` takes priority over `ANTHROPIC_API_KEY` in `getAnalysisMode()`.

| Component | Purpose |
|-----------|---------|
| `app/(main)/dashboard/page.tsx` | Main analysis: repo input, terminal, phase tracker, results |
| `app/(main)/health/page.tsx` | Pi-SEO health dashboard (10 repos, scores, findings) |
| `app/api/analyze/route.ts` | Analysis pipeline: fetches repo files + harness docs, streams phases |
| `hooks/useSSE.ts` | SSE client with exponential backoff reconnection |
| `lib/claude.ts` | `getAnalysisMode()`, `runPhase()`, `buildContext()` |

**ZTE phase 5 evidence:** `app/api/analyze/route.ts` fetches `.harness/leverage-audit.md`, `CLAUDE.md`, and `.harness/spec.md` from the target repo and injects them into phase 5 context so the evaluator scores against actual operational evidence, not cold code.

### 2.4 MCP Server (`mcp/pi-ceo-server.js`)

Version 3.1.0. 21 tools total. `LINEAR_API_KEY` required for Linear tools.

Key tools: `get_zte_score` (reads `leverage-audit.md`), `linear_*` (5 tools), `scan_project`, `get_project_health`, `spec_idea`, `plan_build`, `test_build`, `review_build`, `ship_build`, `get_pipeline`, `run_monitor_cycle`, `get_last_analysis`, `get_sprint_plan`.

### 2.5 Skills (33 total)

| Layer | Count | Key skills |
|-------|-------|-----------|
| Core | 7 | tier-architect, tier-orchestrator, tier-worker, tier-evaluator, context-compressor, token-budgeter, auto-generator |
| Frameworks | 6 | piter-framework, afk-agent, closed-loop-prompt, hooks-system, agent-workflow, agentic-review |
| Strategic | 5 | zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer |
| Foundation | 3 | big-three, claude-max-runtime, pi-integration |
| Meta | 2 | ceo-mode, tao-skills |
| Content+Design | 2 | brand-ambassador, design-system |
| Pi-SEO | 3 | pi-seo-security, pi-seo-deployment, pi-seo-dependencies |
| Ship Chain | 5 | ship-chain, define-spec, technical-plan, verify-test, ship-release |

---

## 3. ZTE Score (Current)

**ZTE v1: 73/75** | **ZTE v2: 84/100 (Zero Touch band)**

Full breakdown: `.harness/leverage-audit.md`. v2 target: 90/100 (Sprint 12), Elite: 95/100 (Sprint 14).

| Dimension | v1 Score | Notes |
|-----------|----------|-------|
| Spec Quality | 5/5 | PITER + 5 ADW + 3-tier complexity + intent injection |
| Context Precision | 5/5 | lessons.jsonl + RESEARCH_INTENT + ENGINEERING_CONSTRAINTS + EVALUATION_CRITERIA |
| Model Selection | 5/5 | `_select_model()` + AUTONOMY_BUDGET 5-anchor interpolation |
| Tool Availability | 5/5 | Full Claude Code suite + fan-out + opus escalation + plan discovery |
| Feedback Loops | 5/5 | Closed-loop evaluator + confidence routing + lesson injection |
| Error Recovery | 5/5 | 3-attempt backoff on clone/generator/push; scope enforcement; phase resume |
| Session Continuity | 5/5 | Phase checkpoints; `POST /api/sessions/{sid}/resume` |
| Quality Gating | 5/5 | Three-tier routing + scope contract ceiling |
| Cost Efficiency | 5/5 | Zero API cost on Claude Max; haiku for plan discovery |
| Trigger Automation | 5/5 | GitHub + Linear webhooks + cron + Telegram + Pi-SEO + autonomy poller |
| Knowledge Retention | 5/5 | lessons.jsonl + plan-discoveries JSONL + Self-Improvement proposals |
| Workflow Standardisation | 5/5 | PITER + 5 ADW templates + ship-chain + 33 skills |
| Observability | 4/5 | gate_checks + alert_escalations in Supabase; SDK metrics; Vercel drift |
| External Validation | 3/5 | ZTE v2 Section C live; C2/C3 data pending |
| Incident History RAG | 5/5 | `_build_incident_context()` injects lessons.jsonl into every generator prompt |

---

## 4. Current Sprint (Sprint 11)

**Active:**
- RA-588: MARATHON-4 — 6-hour autonomous self-maintenance run. In Progress.
- RA-937: main.py decomposed 922L → 11 focused modules ≤300L (Done 2026-04-14). Unlocks route-scoped autonomous sessions.

**Targets (Sprint 11–14):**

| Sprint | Theme | ZTE v2 | Portfolio health |
|--------|-------|--------|-----------------|
| 11 (now) | RA-937 payoff — route tests, spec refresh, evaluator 8.5 | 85 | 80 |
| 12 | Section C wiring (C1+C2+C3), portfolio dep fixes | 90 | 86 |
| 13 | Brief enrichment, portfolio security triage | 92 | 90 |
| 14 | Elite band push | 95 | 95 |

**Sprint 10 complete (2026-04-14):** ZTE v2 81→84. BVI baseline (RA-814), harness doc regen (RA-815), 28 scanner exclusions (RA-834), carsi credential removed (RA-835), ZTE v2 Section C wired (RA-672), CCW-CRM quality 50→90 (RA-690), Synthex error leakage (RA-786), dep health PRs (RA-843/844).

**Sprint 9 complete (2026-04-13):** Karpathy enhancement layer: confidence-weighted evaluator, AUTONOMY_BUDGET single-knob, Session Scope Contract, plan variation discovery, progressive brief complexity, layered abstraction, dependency alerting, Vercel drift monitoring, skills manifest.

---

## 5. File Map

```
Pi Dev Ops/
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server/
│       ├── main.py                     ← Thin assembler (~25L): imports app, registers routers
│       ├── app_factory.py              ← FastAPI app, CORS/security middleware, startup/shutdown
│       ├── models.py                   ← All Pydantic request models (~126L)
│       ├── routes/
│       │   ├── auth.py                 ← /api/login, /api/logout, /api/me
│       │   ├── sessions.py             ← /api/build, /api/build/parallel, session CRUD + SSE
│       │   ├── webhooks.py             ← /api/webhook (GitHub+Linear), morning-intel, Telegram
│       │   ├── triggers.py             ← /api/triggers CRUD
│       │   ├── scan_monitor.py         ← /api/scan, /api/projects/health, /api/monitor
│       │   ├── pipeline.py             ← /api/spec, /api/plan, /api/test, /api/ship
│       │   ├── utils.py                ← /api/gc, /api/lessons, /api/autonomy/status, WS
│       │   └── health.py               ← /health, /api/health/vercel, Claude CLI poll
│       ├── auth.py                     ← HMAC tokens, bcrypt, rate-limit GC
│       ├── config.py                   ← Env-var config; TAO_PASSWORD always rehashes if set
│       ├── sessions.py                 ← Build lifecycle: 5-phase pipeline, evaluator, persistence
│       ├── orchestrator.py             ← Fan-out parallelism
│       ├── brief.py                    ← PITER + ADW templates + complexity + injection
│       ├── webhook.py                  ← GitHub + Linear HMAC + event parsing
│       ├── cron.py                     ← Scheduled triggers + cron_loop()
│       ├── gc.py                       ← Workspace GC (4h TTL, 30min loop)
│       ├── lessons.py                  ← JSONL lessons CRUD
│       ├── scanner.py                  ← Pi-SEO multi-project scanner
│       ├── pipeline.py                 ← Ship-chain pipeline orchestrator
│       ├── autonomy.py                 ← Linear poller → auto-sessions (5min, Todo only)
│       ├── budget.py                   ← AUTONOMY_BUDGET interpolation
│       ├── vercel_monitor.py           ← Vercel deployment drift check
│       ├── core/_chain.py              ← generate(), evaluate(), decide() — no async
│       ├── advanced/                   ← Sprint 9 enhancement layer re-exports
│       └── agents/
│           ├── board_meeting.py        ← Board meeting (SDK, Adaptive Thinking, HookMatcher)
│           ├── plan_discovery.py       ← 3 haiku variants scored, best prepended
│           ├── auto_generator.py       ← config.yaml from complexity tier
│           ├── pi_seo_monitor.py       ← Pi-SEO monitor cycle
│           └── anthropic_intel_refresh.py ← Daily Anthropic docs snapshot
│   └── workspaces/{session_id}/        ← Ephemeral clones (GC'd at 4h)
├── dashboard/                          ← Next.js (Vercel)
│   ├── app/(main)/dashboard/page.tsx
│   ├── app/(main)/health/page.tsx
│   ├── app/api/analyze/route.ts        ← Analysis pipeline + harness doc injection
│   ├── hooks/useSSE.ts
│   └── lib/claude.ts                   ← getAnalysisMode(), runPhase()
├── mcp/pi-ceo-server.js               ← MCP v3.1.0 (21 tools)
├── skills/ (33 skills)
├── src/tao/                            ← Skills registry, tier config, budget tracker
├── scripts/
│   ├── smoke_test.py                   ← 22-check E2E smoke test
│   ├── analyse_lessons.py              ← Lesson analysis → Self-Improvement Linear tickets
│   ├── zte_v2_score.py                 ← ZTE v2 Section C scorer
│   ├── sdk_metrics.py                  ← SDK invocation metrics
│   └── fallback_dryrun.py              ← API fallback quarterly test
├── .harness/
│   ├── spec.md                         ← This document
│   ├── leverage-audit.md               ← ZTE score 73/75 + full changelog (authoritative)
│   ├── lessons.jsonl                   ← Institutional memory (append-only)
│   ├── handoff.md                      ← Cross-session state
│   ├── sprint_plan.md                  ← Sprint history
│   ├── config.yaml                     ← Harness agent config
│   ├── cron-triggers.json              ← Cron trigger persistence
│   ├── projects.json                   ← Pi-SEO project registry (10 repos)
│   ├── agent-sdk-metrics/              ← SDK invocation metrics per day
│   ├── intent/                         ← RESEARCH_INTENT, ENGINEERING_CONSTRAINTS, EVALUATION_CRITERIA
│   ├── agents/                         ← planner.md, generator.md, evaluator.md
│   ├── contracts/                      ← build-contract.md, eval-contract.md
│   ├── qa/                             ← smoke-test.md (22 checks), regression-checklist.md
│   ├── board-meetings/                 ← Autonomous board meeting minutes
│   ├── plan-discoveries/               ← Plan variation JSONL logs (one file per day)
│   └── anthropic-docs/                 ← Daily Anthropic docs snapshots
├── pyproject.toml
├── railway.toml
├── vercel.json
└── README.md
```

---

## 6. Design Decisions

**Why Claude Agent SDK instead of `claude -p`?**
Structured event streaming, `ThinkingConfigAdaptive` for extended reasoning, `HookMatcher` for latency observability, no shell escaping hazards. Zero-cost under Claude Max preserved. API fallback: `TAO_USE_FALLBACK=1` → direct Anthropic Python SDK. Test quarterly.

**Why JSONL for lessons?**
Append-only, atomic at OS buffer level for single-process server. One lesson per line — no lock needed, no corruption risk. O(N) over a small file — acceptable until ~10MB.

**Why atomic writes for session persistence?**
`write-to-.tmp + os.replace()` prevents corrupt JSON on crash. `os.replace()` is atomic on NTFS and POSIX. Persistence errors must never crash the build pipeline.

**Why keyword-based PITER classification?**
Deterministic, zero-cost, ordering handles ambiguity (hotfix first, feature last). ML classifier would be overkill for 5 categories.

**Why in-memory `_sessions` with file backup?**
Solo developer, low session volume. Full DB adds operational overhead for marginal gain. JSON backup via `persistence.py` survives restarts and marks interrupted sessions.

**Why ZTE phase 5 harness injection?**
The cold-code evaluator scores surface structure without seeing operational evidence. Injecting `leverage-audit.md`, `CLAUDE.md`, and `spec.md` into phase 5 context lets the ZTE evaluator score against the actual 73/75 operational record, not just the codebase topology.
