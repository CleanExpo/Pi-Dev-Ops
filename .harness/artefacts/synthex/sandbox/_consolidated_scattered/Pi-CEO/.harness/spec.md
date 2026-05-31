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

---

## 7. Comprehensive Skills & TAO Engine Analysis

_Added 2026-04-17 (Sprint 12) — covers the 48-skill inventory, src/tao engine architecture, integration patterns, constraint analysis, and improvement suggestions._

### 7.1 Skill Inventory (48 Skills)

Skill definitions are stored as YAML-frontmatted Markdown files under `skills/*/SKILL.md`. The `src/tao/skills.py` loader parses frontmatter and caches all entries in `_SKILLS_CACHE`. `skills_manifest()` partitions them into `auto` (injected by intent router) and `manual` (require explicit invocation).

#### Core Tier System (7 skills)

| Skill | Role | Automation |
|-------|------|-----------|
| `tier-architect` | Design tier configurations; model selection per role | manual |
| `tier-orchestrator` | Top-level decomposition, parallel dispatch, escalation rules | auto |
| `tier-worker` | Discrete task execution; escalation trigger conditions | auto |
| `tier-evaluator` | QA agent; thresholds: completeness≥7, correctness≥7, quality≥6, format≥8 | auto |
| `context-compressor` | Token compression at tier boundaries (truncate/extract/summarize modes) | auto |
| `token-budgeter` | Per-tier token accounting; current costs: Opus $15/M, Sonnet $3/M, Haiku $1.25/M | manual |
| `auto-generator` | Derives `config.yaml` from brief complexity; presets: 2-tier-codereview, 3-tier-webapp, 4-tier-research | manual |

#### Framework & Patterns (11 skills)

| Skill | Role | Key constraint |
|-------|------|---------------|
| `piter-framework` | 5-pillar AFK setup (Prompt/Intent/Trigger/Environment/Review) | Manual invocation required |
| `afk-agent` | Unattended runtime with bounded cost/tokens, stop guards, no silent failures | `stop_conditions` mandatory |
| `closed-loop-prompt` | Self-correcting embedded verification (test-fix loops) | Max 3 correction attempts |
| `hooks-system` | 6 lifecycle hook types: PreToolUse, PostToolUse, Stop, SubagentStop, PreCompact, SessionStart | hooks fire in subprocess, not harness |
| `agent-workflow` | ADWs (Feature Build, Bug Fix, Chore, Code Review, Research Spike) | auto |
| `agentic-review` | 6 QA dimensions: Architecture, Naming, Error handling, Duplication, Complexity, Conventions | manual |
| `agentic-loop` | Infinite self-correcting iteration | Hard caps: 20 iterations, 200k tokens, 60 min |
| `agent-expert` | Act-Learn-Reuse cycle; lessons stored in `lessons.jsonl`, top-5 injected per task | auto |
| `agentic-layer` | Agent-native architecture: JSON I/O over HTML, named actions, machine-readable state | manual |
| `big-three` | Model (right tool/tier) + Prompt (spec with verification) + Context (compressed, recent) | manual |
| `leverage-audit` | 12-point ZTE diagnostic; score bands: Manual 12-20, Assisted 21-35, Autonomous 36-48, Zero Touch 49-60 | manual |

#### Strategic & Direction (6 skills)

| Skill | Role |
|-------|------|
| `zte-maturity` | 4-level maturity model with 12 leverage dimensions |
| `architecture` | Core patterns: split-screen companion, CLAUDE.md hygiene, sandbox isolation, parallel dispatch |
| `ceo-mode` | Executive reporting format: What / State / Works / Doesn't / Risks / Opportunities / Next 3 |
| `brand-ambassador` | On-brand copy generation; banned words: leverage, robust, seamless, delve, tapestry, landscape |
| `product-manager` | Feature completeness 5-point matrix: Completeness, Reliability, Usability, Performance, Documentation |
| `maintenance-manager` | Dependency health, technical debt inventory, observability gaps, SLA recommendations |

#### Ship Chain Pipeline (5 skills)

| Skill | Phase | Gate |
|-------|-------|------|
| `ship-chain` | Orchestrator: /spec → /plan → /build → /test → /review → /ship | review score ≥ 8/10 |
| `define-spec` | Phase 1: PITER classification + Goals, Non-Goals, Acceptance Criteria GWT, Constraints | spec.md written |
| `technical-plan` | Phase 2: Approach, Files Changed, Steps, Dependencies, Risks, Test Plan | plan.md written |
| `verify-test` | Phase 4: Verdict (PASS/FLAKY_PASS/FAIL), coverage delta, regression risk | PASS or FLAKY_PASS |
| `ship-release` | Phase 6: Hard gate review ≥ 8/10; pre-ship checklist; ship log entry | review ≥ 8 |

#### Design Stack (6 skills)

| Skill | Role | Notable constraint |
|-------|------|-------------------|
| `design-system` | Entry point routing UI work to 4-layer stack | manual |
| `design-intelligence` | DESIGN.md master (9-section standard); 66 brand archetypes | Design.md must exist before component build |
| `ui-component-builder` | 3-dial: DESIGN_VARIANCE / MOTION_INTENSITY / VISUAL_DENSITY; 8 mandatory states | All 8 states required: default, hover, active, loading, empty, error, disabled, focus |
| `design-audit` | 24 anti-pattern detection + 6 quality dimensions | manual |
| `ui-ux-pro-max` | Full production workflow: context → brief → build → audit → visual-qa → ship checklist | manual |
| `visual-qa` | Playwright regression; breakpoints: 375/768/1280/1920px; baseline management | Playwright must be installed |

#### Pi-SEO Operations (5 skills)

| Skill | Role |
|-------|------|
| `pi-seo-scanner` | Blast-radius scoring: severity × exposure × fixability; classification: fix-now/schedule/suppress/investigate |
| `pi-seo-health-monitor` | Portfolio health trends; regression threshold: ≥5pt drop; critical: ≥15pt; systemic: 2+ repos |
| `pi-seo-remediation` | 4-tier: Tier1=automated, Tier2=config, Tier3=code, Tier4=architectural; 20 secret/dangerous cards |
| `security-audit` | OWASP Top 10, CVSS scoring, dependency risks | manual |
| `security` | Path traversal, HMAC verification, secrets hygiene, rate limiting | auto |

#### Orchestration & Runtime (4 skills)

| Skill | Role |
|-------|------|
| `claude-runtime` | SDK vs subprocess modes; `TAO_USE_AGENT_SDK` flag semantics; stream-json parsing |
| `claude-max-runtime` | Tier mapping for Max subscription (zero API cost); `ANALYSIS_MODE=api` |
| `pi-integration` | Multi-provider bridge: Anthropic + OpenAI + Ollama |
| `claude` | SDK patterns; abort controller placement; MCP subpath imports |

#### Utilities & Meta (4 skills)

| Skill | Role |
|-------|------|
| `analyzing-customer-patterns` | Outcome feedback loop; staleness rule: 30-day; positive/negative/neutral/stale signals |
| `scheduled-tasks` | Reliable scheduled task prompts; dynamic repo discovery; tool-approval minimization |
| `deployment` | Railway proxy; Vercel SSE limit 300s; Telegram; per-phase model routing |
| `tao-skills` | Master index of 31 TAO skills across 7 layers |

**Intent-to-skill mapping** (auto-injected on intent classification):

| Intent | Auto-injected skills |
|--------|---------------------|
| `feature` | tier-orchestrator, agent-workflow, closed-loop-prompt, agent-expert |
| `bug` | tier-worker, closed-loop-prompt, agent-expert, security |
| `hotfix` | tier-worker, agent-expert |
| `spike` | tier-orchestrator, agentic-loop, agent-expert |
| `chore` | tier-worker, agent-workflow |
| `spec` | define-spec, piter-framework |
| `plan` | technical-plan, tier-architect |
| `test` | verify-test, closed-loop-prompt |
| `ship` | ship-chain, ship-release |
| `design` | design-system, design-intelligence |
| `monitor` | pi-seo-scanner, pi-seo-health-monitor |
| `content` | brand-ambassador, ceo-mode |

---

### 7.2 TAO Engine Architecture (`src/tao/`)

The TAO engine provides skill registry, tier configuration, and budget tracking. It is **stub scaffolding** — the web server does not import it directly. All agent execution flows through `app/server/session_sdk.py` via `claude_agent_sdk`. The engine modules provide the shared schema and config layer.

#### Module Map

```
src/tao/
├── __init__.py
├── skills.py                  ← Skill loader & intent router (48 skills, _SKILLS_CACHE)
├── agents/
│   └── __init__.py            ← AgentDispatcher: intent routing, concurrent execution
├── budget/
│   └── tracker.py             ← BudgetTracker dataclass: record(), remaining(), pct_used()
├── schemas/
│   └── artifacts.py           ← TaskSpec, TaskResult, Escalation dataclasses
├── tiers/
│   └── config.py              ← TierConfig, MODEL_MAP, load_config(path)
└── templates/
    └── 3-tier-webapp.yaml     ← Preset: orchestrator(Opus,20%) + specialist(Sonnet,30%) + worker(Haiku,50%)
```

#### Schema Layer (`schemas/artifacts.py`)

```python
TaskSpec:    description, tier, task_id, context, parent_task_id, expected_output, max_tokens
TaskResult:  task_id, tier, content, success, tokens_used, model, duration_seconds
Escalation:  task_id, from_tier, reason, context_needed, partial_result
```

These dataclasses define the contract between tier layers. `Escalation` is raised when a Worker cannot resolve a task within its authority (ambiguous spec, >3 files, security boundary).

#### Tier Configuration (`tiers/config.py`)

```python
TierConfig:  name, model, role, parent, max_concurrency, token_budget_pct, fallback_model
MODEL_MAP:   opus→claude-opus-4-7, sonnet→claude-sonnet-4-6, haiku→claude-haiku-4-5-20251001
```

`load_config(path)` reads YAML, returns `(List[TierConfig], total_token_budget)`. The 3-tier webapp preset allocates:
- Orchestrator: Opus 4.7, 20% of 500k = 100k tokens
- Specialist: Sonnet 4.6, 30% = 150k tokens, `max_concurrency=2`
- Worker: Haiku 4.5, 50% = 250k tokens, `max_concurrency=5`

#### Budget Tracking (`budget/tracker.py`)

```python
BudgetTracker: total_budget, used, per_tier: dict[str, int]
Methods:       record(tier, tokens), remaining(), pct_used()
```

Budget tracking is per-tier and per-session. The `autonomy_budget` in `config.yaml` drives a higher-level policy that maps session runtime minutes to {model, eval_threshold, max_retries, timeout}:

| Minutes | Model | eval_threshold | max_retries | timeout |
|---------|-------|---------------|-------------|---------|
| 10 | haiku | 7.5 | 1 | 8 min |
| 30 | sonnet | 8.5 | 2 | 25 min |
| 60 | sonnet | 9.0 | 3 | 50 min |
| 120 | sonnet | 9.0 | 4 | 100 min |
| 240 | sonnet | 9.5 | 5 | 200 min |

#### Skill Registry (`skills.py`)

- Parses all `skills/*/SKILL.md` YAML frontmatter on first access, caches in `_SKILLS_CACHE`
- `skills_manifest()` returns `{auto: [...], manual: [...]}` partition
- Intent routing: 12 intents map to lists of skill names; matched skills are auto-prepended to generator prompts
- Skills with `automation: manual` require explicit caller invocation (e.g., `design-audit`, `leverage-audit`)

#### Agent Dispatcher (`agents/__init__.py`)

`AgentDispatcher` receives an intent classification and dispatches to concurrent tier execution. Key logic:
- Resolves intent → skill list via `skills.py`
- Dispatches `TaskSpec` objects to appropriate tier workers
- Collects `TaskResult` objects; raises `Escalation` to parent tier on failure
- Batch dispatch: independent tasks run concurrently (up to `max_concurrency` per tier)

---

### 7.3 Integration Patterns

#### Model Policy Enforcement (3-Layer)

Layer 1 — `model_policy.py`: `select_model(role, requested)` downshifts Opus → Sonnet for non-allowed roles. Violations appended to `.harness/model-policy-violations.jsonl`.

Layer 2 — `session_sdk.py`: `assert_model_allowed(role, model)` called before every SDK invocation. Raises `ValueError` on violation — hard stop.

Layer 3 — `config.py`: `OPUS_ALLOWED_ROLES` env-overridable set defaults to `{"planner", "orchestrator"}`. Override via `TAO_OPUS_ALLOWED_ROLES=planner,orchestrator,foo`.

#### SDK Integration Pattern (`session_sdk.py`)

Every generator/evaluator call follows this sequence:
1. `assert_model_allowed(role, model)` — policy gate
2. Pop `ANTHROPIC_API_KEY` if empty (RA-1195) — prevents 401 on OAuth tokens
3. Attach `prompt-caching-2024-07-31` beta flag if `ENABLE_PROMPT_CACHING_1H=1` (RA-1009)
4. Set `permission_mode='bypassPermissions'` (RA-1172) — prevents stall on tool prompts
5. Execute via top-level `query()` (RA-1171) — stateless, avoids task-scope bug in `ClaudeSDKClient`
6. Enforce timeout via `asyncio.wait_for` (RA-1170) — SDK has no built-in stream timeout
7. Append invocation row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl` — fire-and-forget

#### Lesson Injection Pattern

Every generator prompt receives up to 5 lessons from `lessons.jsonl` matched by cosine similarity to the current brief. Lessons are keyed on evaluator score, reviewer critiques, and git diff fingerprints. The `agent-expert` skill defines the Act-Learn-Reuse cycle.

#### PITER Classification → Brief Generation

```
raw brief
   │
   ▼  keyword match (hotfix > bug > chore > spike > feature)
PITER intent
   │
   ▼  intent → auto skills + ADW template + complexity tier (basic/detailed/advanced)
enriched prompt
   │
   ▼  + top-5 lessons.jsonl entries + RESEARCH_INTENT + ENGINEERING_CONSTRAINTS
generator input
```

#### Phase Checkpointing

Session state persisted atomically after each phase (`write-to-.tmp + os.replace()`). Phase resume reads last checkpoint — partial failures restart from the failed phase, not from Phase 1.

---

### 7.4 Constraint Analysis

#### Hard Constraints

| Constraint | Source | Consequence of violation |
|-----------|--------|------------------------|
| `TAO_USE_AGENT_SDK=1` mandatory | `config.py` | `ImportError` at startup |
| Opus reserved for planner+orchestrator | RA-1099 | ValueError before SDK call, violation logged |
| `permission_mode='bypassPermissions'` on every SDK call | RA-1172 | Silent stall on tool prompts in automation |
| `async for message in receive_response()` (not `_query`) | SDK contract | Breaks on SDK upgrades |
| `query()` not `ClaudeSDKClient` | RA-1171 | Task-scope bug causes context leakage |
| Evaluator gate: score ≥ 8/10 | RA-674 | Session fails; retry up to max_retries |
| Workspace GC: terminal states deleted at 4h | `gc.py` | Potential loss of artifacts if not pushed |
| SSE stream: Vercel hard limit 300s | Vercel infra | Phase must complete under 240s or stream drops |
| 3-layer autonomous permissions | Scheduled tasks | Silent stall without all three layers |
| CLAUDE.md `functions < 40L, files < 300L` | Project conventions | Reviewer must reject; RA-937 was the payoff |

#### Soft Constraints

| Constraint | Source | Notes |
|-----------|--------|-------|
| Max 3 skill correction iterations (`closed-loop-prompt`) | Skill definition | Oscillation detection after 2 consecutive identical outputs |
| Max 5 relevant lessons injected per prompt | `lessons.py` | Top-5 by similarity; more degrades focus |
| `agentic-loop` caps: 20 iterations, 200k tokens, 60 min | Skill definition | Hard-stops to prevent runaway loops |
| Max concurrent sessions: 3 | `config.py` | HTTP 429 on overflow; no queue |
| `_sessions` in-memory; no cross-instance sync | `sessions.py` | Railway multi-instance not supported today |
| `ANTHROPIC_API_KEY` must not be empty string | RA-1195 | Silently breaks OAuth fallback; must `pop()` |
| Vercel env vars always trimmed (trailing `\n`) | RA-API hygiene | Next.js routes must `.trim()` before use |
| `op://` refs in `.env` not resolved by `dotenv` | RA-1Password | Pydantic validator must detect and return None |

#### Race Conditions & Edge Cases

- **`_sessions` restart loss:** In-memory dict cleared on Railway restart. Persist session status to disk after every state change (already done via `persistence.py`; risk is in-flight sessions only).
- **Cron `last_fired_at` reset:** Railway redeploy resets git-committed `cron-triggers.json` values. Startup catch-up within 10s required (RA pattern: `abs()` in debounce + fire overdue triggers at boot).
- **autonomy.py poll:** Skips entirely when `LINEAR_API_KEY` missing, but `/health` still returns 200. `linear_api_key: bool` must surface in health response.
- **Rate-limit GC:** `_req_log` accumulates IP keys forever on local installs. Inline prune every 5 min (no background task needed).
- **Cloud IP rate-limiting:** `request.client.host` is LB-internal in Railway. Trust `X-Forwarded-For[0]` when `_IS_CLOUD`.

---

### 7.5 Improvement Suggestions

#### Improvement 1: Skill Versioning & Drift Detection

**Current state:** Skill YAML frontmatter has no `version` field. Changes to skill constraints (e.g., raising `agentic-loop` cap from 20→30 iterations) are invisible to the harness — `_SKILLS_CACHE` simply loads whatever is on disk.

**Problem:** Agent runs that were parameterised against the old constraint silently get the new one. Evaluator scores can shift without explanation. Skills that reference each other (e.g., `tier-evaluator` thresholds referenced in `agent-workflow`) can drift out of sync.

**Suggestion:** Add a `version: semver` field to every `SKILL.md` frontmatter. `skills.py` records the loaded version in the session's metadata row. `session_sdk.py` logs `skills_snapshot: {name: version}` to `.harness/agent-sdk-metrics/`. A weekly cron job (`scripts/check_skill_drift.py`) diffs current versions against the snapshot from the previous successful session and opens a Linear RA-ticket if any skill changed. Zero new dependencies — pure YAML + JSONL.

**Effort:** Low. Files touched: `skills/*/SKILL.md` (frontmatter only), `src/tao/skills.py`, `app/server/session_sdk.py`, `scripts/check_skill_drift.py`.

---

#### Improvement 2: Per-Session Budget Dashboard (Observability Gap)

**Current state:** `BudgetTracker` accurately records per-tier token consumption in memory. SDK metrics are written to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. However, the SSE stream sent to the browser contains phase names and evaluator scores but **no cost or token data**. The dashboard has no live cost surface.

**Problem:** Operators cannot see whether a session is on-budget until it completes. Runaway generator prompts (e.g., `agentic-loop` oscillating) are invisible until the 200k token hard-cap fires. The autonomy budget tier (10/30/60/120/240 min) is set globally, not per-session.

**Suggestion:** Add a `budget` field to every SSE event emitted in `sessions.py`. The field carries `{tier: str, tokens_used: int, tokens_remaining: int, cost_usd_est: float}`. The dashboard `useSSE.ts` hook accumulates these events and renders a live cost chip beside the phase tracker. Values are derived from `BudgetTracker.pct_used()` and the model price table already in `config.py`. No new backend infrastructure — SSE already streams to the browser.

**Effort:** Medium. Files touched: `app/server/sessions.py` (emit budget event), `app/server/session_sdk.py` (pass tracker ref), `dashboard/hooks/useSSE.ts` (parse budget event), `dashboard/app/(main)/dashboard/page.tsx` (render cost chip). Matches Surface Treatment RA-1109 requirement: every long-running action needs a live progress surface.

---

#### Improvement 3: Graduated Escalation for Autonomy Budget Violations

**Current state:** When a generator session exceeds the `autonomy_budget` timeout, the session is killed and marked `failed`. The evaluator never runs. There is no intermediate path — no partial evaluation, no lesson extraction, no Telegram alert with the partial diff.

**Problem:** Failed sessions produce no lessons. A 240-minute session that times out at 235 minutes discards all institutional memory. The `lessons.jsonl` file stays unchanged even though the generator may have produced useful partial output.

**Suggestion:** Add a `_phase_timeout_recovery()` hook in `sessions.py` that fires when the generator exceeds `timeout_min`. The hook: (1) captures the current workspace diff, (2) runs a lightweight evaluator pass at Haiku cost (scoring only `correctness` and `completeness`, skipping `format` and `code-quality`), (3) extracts any actionable lesson from the partial output and appends it to `lessons.jsonl`, (4) sends a Telegram alert with the partial score and the git diff URL. Sessions remain `failed` in status — the recovery is observability-only, not a ship path. This costs one Haiku call (~$0.001) per timeout and recovers institutional memory from every failed session.

**Effort:** Medium. Files touched: `app/server/sessions.py` (timeout hook), `app/server/lessons.py` (partial lesson writer), `app/server/routes/utils.py` (expose partial-lesson endpoint). New helper: `scripts/send_telegram.py` already exists — reuse it.

---

#### Improvement 4: `_sessions` Cross-Instance Persistence (Risk Register R-03)

**Current state:** `_sessions` dict is in-memory. Railway redeploys (which happen on every git push) clear all running sessions. Phase checkpoint files survive (written to disk) but the in-memory routing table is lost.

**Problem:** If Railway scales to 2 instances (which it can do automatically under load), each instance has a different `_sessions` view. A `/api/sessions` list request routed to instance B returns zero results for sessions started on instance A. An SSE reconnect after a Railway restart never finds the session.

**Suggestion:** Write session status to a Supabase `sessions` table (already declared in `supabase/migration.sql` with no current writer — this is listed as a cleanup target in the observability section). On startup, load all non-terminal sessions from Supabase into `_sessions`. On every state change, write atomically to both disk (existing) and Supabase (new). Read path: prefer in-memory, fall back to Supabase on miss. This makes session state cross-instance and restart-safe with no new dependencies (Supabase client already present). The `supabase_log.py` single-write-path pattern applies: Supabase writes are fire-and-forget — observability failures must not block the build pipeline.

**Effort:** High. Files touched: `app/server/sessions.py` (startup load + write-through), `app/server/supabase_log.py` (new `log_session_state()` function), `supabase/migration.sql` (activate existing `sessions` table schema). Risk: Supabase write latency adds ~20ms per phase transition — acceptable given phases run for 30-240s.

---

### 7.6 Skill Coverage Gaps

Three areas have no auto-injected skill coverage today:

| Gap | Current state | Suggested skill |
|-----|--------------|----------------|
| **TypeScript / Next.js type safety** | No skill auto-injected for `tsc --noEmit` failures | `ts-strict`: enforces strict mode checks, `any` prohibition, interface-over-type |
| **Supabase query parameterisation** | `security` skill covers backend; no skill for Supabase RLS / parameterised queries in Next.js routes | Extend `security` skill with Supabase-specific section |
| **Phase timeout recovery** | `afk-agent` has stop guards but no partial-result extraction on timeout | Extend `afk-agent` skill with a `timeout_recovery` stanza |

These gaps mean that generator prompts for design/frontend tasks receive no type-safety guidance, and Supabase-touching Next.js API routes receive no RLS reminder. Adding these stanzas to existing skills (rather than new skill files) keeps the manifest at 48 and avoids intent-routing complexity.

---

### 7.7 Architecture Observations

1. **TAO engine is decoupled from runtime.** `src/tao/` provides schemas and skill registry, but `app/server/` re-derives model routing independently in `model_policy.py` and `config.py`. The `TierConfig.model` field and `MODEL_MAP` in `tiers/config.py` are duplicated in `config.py`'s `MODEL_SHORT_TO_ID`. A single source-of-truth constant file would eliminate drift risk.

2. **Skill injection is one-shot.** Auto-injected skills are prepended to the generator prompt once. There is no mechanism for the generator to request additional skills mid-session. The `closed-loop-prompt` correction loop re-uses the same skill set on retry. If the correction requires a skill not in the original injection (e.g., a bug correction needing `security` which wasn't injected for a `feature` intent), the generator has no path to get it without re-triggering the full phase.

3. **Manual skills are undiscoverable at runtime.** Skills with `automation: manual` only appear if the caller explicitly names them in the brief. There is no mechanism for the orchestrator to surface "you might want to invoke `design-audit` given your brief mentions UI components." A lightweight keyword match (similar to PITER classification) could surface relevant manual skills as suggestions in the SSE stream.

4. **Budget tracker is instantiated but not wired.** `BudgetTracker` in `src/tao/budget/tracker.py` is a correct implementation, but `session_sdk.py` does not instantiate it. SDK metric rows capture `output_len` but not `tokens_used` (which requires a structured SDK response field). The tracker is effectively unused in production today.
