# Pi Dev Ops — Product Spec (Full Analysis)

_Generated: 2026-04-08 | Last updated: 2026-04-10 (Sprint 7) | Analyst: Pi CEO Orchestrator | Sprint: 7 / Cycle 13_

---

## 1. System Overview

**Pi Dev Ops** is a Zero Touch Engineering (ZTE) platform that converts a plain-English brief and a git repository URL into an executed, evaluated, and committed engineering session — entirely autonomously. It orchestrates the Claude Max subscription to perform engineering work at zero per-token cost via the `claude` CLI.

### Core Identity

- **Not CI/CD.** Not a build pipeline. It is an **agentic harness**: a thin orchestration layer between human intent and Claude Code execution.
- **Companion tool.** Designed to run alongside Claude Desktop (left pane = CLI writing code; right pane = Pi Dev Ops orchestrating, tracking, pushing to Linear).
- **ZTE Score: 60/60** as of Sprint 3 — all 12 leverage points at maximum.

### Build Pipeline

```
Human → Brief + Repo URL
         │
         ▼
POST /api/build  →  FastAPI  →  run_build()
                                    │
  Phase 1:   git clone (3-attempt exponential backoff)
  Phase 2:   workspace analysis (file listing)
  Phase 3:   Claude Code availability check
  Phase 3.5: sandbox verification (auto re-clone if GC'd)
  Phase 4:   generator — claude -p <spec> --stream-json (2-attempt retry)
  Phase 4.5: evaluator — claude -p <eval_spec> (blocking; up to 3 total)
             └─ if below threshold: inject critique → retry Phase 4
             └─ if passed or exhausted: auto-append lessons to .jsonl
  Phase 5:   git push (3-attempt exponential backoff; auth → hard stop)
                                    │
                                    ▼
                           lessons.jsonl ← auto-learned from evaluator scores

Browser ← WebSocket /ws/build/{sid}  (live event stream, 150ms polling)
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
| `brief.py` | PITER intent classifier + 5 ADW templates + skill/lesson context injection | ✅ Complete |
| `webhook.py` | GitHub + Linear HMAC verification, event parsing, brief generation | ✅ Complete |
| `cron.py` | Scheduled triggers (`.harness/cron-triggers.json`), 60s loop | ✅ Complete |
| `gc.py` | Workspace GC: terminal sessions >4h TTL + orphan dir scan, 30min loop | ✅ Complete |
| `lessons.py` | JSONL-backed institutional memory, `GET/POST /api/lessons` | ✅ Complete |
| `scanner.py` | Pi-SEO autonomous multi-project scanner orchestrator | ✅ Complete |
| `pipeline.py` | Ship-chain pipeline orchestrator (6 phases, artifact persistence) | ✅ Complete |
| `agents/board_meeting.py` | Claude Agent SDK PoC — BoardMeetingAgent parallel to existing cron | ✅ Complete |

**Security posture:**
- `SecurityHeaders` middleware: CSP nonce-based policy (per-request), X-Frame-Options, X-XSS-Protection on every response
- CORS: explicit allowlist (`localhost:3000`, `*.vercel.app`, `*.railway.app` + env-var extension)
- Cookie: `HttpOnly`, `Secure` (cloud only), `SameSite=None` (cloud) / `Strict` (local)
- Auth: bcrypt password hash (auto-migrated from SHA-256 on first login), `hmac.compare_digest` (timing-safe). Bearer token also accepted (WS fallback)
- Rate limit: 30 req/min/IP, inline GC every 5 min, stale IP keys pruned at 120s idle
- Path traversal: `_safe_sid()` strips non-alphanumeric from session IDs before file path use
- Webhook HMAC: mandatory secrets (GITHUB_WEBHOOK_SECRET / LINEAR_WEBHOOK_SECRET hard-fail if missing); timing-safe comparison

### 2.2 TAO Engine (`src/tao/`)

The Python engine provides a skills registry, tier config loading, budget tracking, and data schemas. All actual AI execution is delegated to the `claude` CLI subprocess — the engine does not call the Anthropic API directly.

| Module | Status | Purpose |
|--------|--------|---------|
| `schemas/artifacts.py` | ✅ Complete | `TaskSpec`, `TaskResult`, `Escalation` dataclasses |
| `tiers/config.py` | ✅ Complete | `TierConfig` dataclass, MODEL_MAP, YAML loader |
| `budget/tracker.py` | ✅ Complete | `BudgetTracker`: per-tier token accounting, `record(tier, tokens)` |
| `skills.py` | ✅ Complete | Skill loader/registry: frontmatter parser, `load_all_skills()`, `skills_for_intent()` |
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
| `leverage-audit.md` | ✅ Present | 12-point ZTE diagnostic, full changelog from 35→60 |
| `sprint_plan.md` | ✅ Present | Sprint history and Sprint 8 open items |
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

---

## 3. Skills Analysis (31 of 31)

### Layer 1: Core (7 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `tier-architect` | Design model-to-role tier hierarchy | Partial | `.harness/config.yaml` partially implements |
| `tier-orchestrator` | Top-tier planning + delegation patterns | ✅ | `orchestrator.py` fan-out pattern + brief decomposition |
| `tier-worker` | Discrete execution, escalation rules | ✅ | `run_build()` workers; escalation via opus fallback |
| `tier-evaluator` | QA grading with 4 dimensions | ✅ | Phase 4.5 in `sessions.py`; `evaluator.md` spec |
| `context-compressor` | Truncate/extract/summarize at tier boundaries | Partial | `build_structured_brief()` truncates skill bodies to 800 chars |
| `token-budgeter` | Track token spend per tier | Partial | `BudgetTracker` instantiated per session |
| `auto-generator` | Generate tier configs from project briefs | No | Presets defined; no code generates them yet |

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

## 4. Current Leverage Audit (60/60 — Zero Touch)

| # | Point | Score | Evidence |
|---|-------|-------|---------|
| 1 | Spec Quality | 5/5 | PITER classifier + 5 ADW templates + skill injection (RA-456, RA-457) |
| 2 | Context Precision | 5/5 | Lesson context injected per-intent into every brief (`_get_lesson_context`) |
| 3 | Model Selection | 5/5 | `_select_model()` reads `.harness/config.yaml`; override retained |
| 4 | Tool Availability | 5/5 | Full Claude Code suite + fan-out + opus tier escalation |
| 5 | Feedback Loops | 5/5 | Closed-loop evaluator: critique → retry prompt → re-generate → re-evaluate |
| 6 | Error Recovery | 5/5 | Clone 3-attempt backoff; generator 2-attempt retry; phase checkpoints + resume |
| 7 | Session Continuity | 5/5 | Phase-level checkpoints; `POST /api/sessions/{sid}/resume` |
| 8 | Quality Gating | 5/5 | Evaluator is a BLOCKING gate (configurable max retries before push) |
| 9 | Cost Efficiency | 5/5 | Zero API cost on Claude Max |
| 10 | Trigger Automation | 5/5 | GitHub + Linear webhooks + cron triggers + Telegram + Pi-SEO scan rotation |
| 11 | Knowledge Retention | 5/5 | Auto-learn: low evaluator dims → lessons.jsonl → injected in next brief |
| 12 | Workflow Standardisation | 5/5 | PITER at brief entry; all 5 ADW templates active; ship-chain pipeline |

**Total: 60 / 60 — Zero Touch Engineering band (56-60)**

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

---

## 6. Sprint 7 Completions + Sprint 8 Direction

### Sprint 7 — Complete (2026-04-10)
Mobile & tablet responsive layout, worktree isolation fix, Telegram bot integration (@piceoagent_bot), claude-code-telegram deployed to Railway with full Claude Agent SDK tool use.

### Sprint 8 — Open Items (Candidate)

| Priority | Item | Status |
|----------|------|--------|
| High | Pi-SEO first full sweep across all 10 repos | Unstarted |
| High | Agent SDK production cut-over plan (post-PoC) | Unstarted |
| Medium | Self-improvement loop — lesson-pattern analyser | Unstarted |
| Medium | Multi-model parallel evaluation (Sonnet+Haiku consensus) | Unstarted |
| Low | Autonomous Pi Dev Ops self-maintenance on 6h schedule | Unstarted |

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
│       └── agents/
│           └── board_meeting.py        ← Claude Agent SDK PoC board-meeting agent
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
├── skills/ (31 skills)
│   ├── [core: 7]    tier-architect, tier-orchestrator, tier-worker,
│   │                tier-evaluator, context-compressor, token-budgeter, auto-generator
│   ├── [fw: 6]      piter-framework, afk-agent, closed-loop-prompt,
│   │                hooks-system, agent-workflow, agentic-review
│   ├── [strat: 5]   zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer
│   ├── [found: 3]   big-three, claude-max-runtime, pi-integration
│   ├── [meta: 2]    ceo-mode, tao-skills (master index)
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
├── scripts/
│   ├── analyze.sh                      ← Analysis helper script
│   └── fetch_anthropic_docs.py         ← Daily docs pull (cron at 5:50am AEST)
├── .harness/
│   ├── config.yaml                     ← Harness agent config (planner/generator/evaluator)
│   ├── spec.md                         ← This document (living specification)
│   ├── handoff.md                      ← Cross-session state (Sprint 7 complete)
│   ├── leverage-audit.md               ← ZTE score 60/60 + full changelog
│   ├── sprint_plan.md                  ← Sprint 7 complete; Sprint 8 open
│   ├── lessons.jsonl                   ← 18 institutional memory entries
│   ├── feature_list.json               ← Feature list for MCP (62 features)
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

**Why `claude -p` subprocess instead of Python API?**
Zero-cost execution under Claude Max subscription. Calling `anthropic.Anthropic()` directly would incur per-token charges. The CLI also provides native tool-use, bash execution, file editing, and stream-json output without re-implementing the harness. This is the architectural bedrock decision.

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

## 9. Next Actions (Sprint 8)

```
[ ] Pi-SEO activation: trigger first full sweep across all 10 repos; review finding volume
[ ] Agent SDK cut-over: define production migration plan from claude -p subprocess
[ ] Self-improvement loop: scheduled lesson-pattern analyser (CLAUDE.md proposals)
[ ] Multi-model evaluator: Sonnet + Haiku consensus, Opus escalation on disagreement
[ ] Autonomous self-maintenance: Pi Dev Ops scans itself on 6h schedule
```
