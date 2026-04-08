# Pi Dev Ops — Product Spec (Full Analysis)

_Generated: 2026-04-08 | Last updated: 2026-04-08 (Sprint 4 spike) | Analyst: Pi CEO Orchestrator (Claude Sonnet 4.6) | Sprint: 4 / Cycle 6_

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

**Security posture:**
- `SecurityHeaders` middleware: CSP, X-Frame-Options, X-XSS-Protection on every response
- CORS: explicit allowlist (`localhost:3000`, `*.vercel.app`, `*.railway.app` + env-var extension)
- Cookie: `HttpOnly`, `Secure` (cloud only), `SameSite=None` (cloud) / `Strict` (local)
- Auth: SHA-256 password hash, `hmac.compare_digest` (timing-safe). Bearer token also accepted (WS fallback)
- Rate limit: 30 req/min/IP, inline GC every 5 min, stale IP keys pruned at 120s idle
- Path traversal: `_safe_sid()` strips non-alphanumeric from session IDs before file path use
- Webhook HMAC: timing-safe comparison for both GitHub (`sha256=<hex>`) and Linear (`<hex>`) formats

**Known limitations / open items:**
1. `src/tao/agents/__init__.py` is empty — agent dispatch not implemented in Python; all execution is via `claude -p` subprocess
2. Dashboard `lib/types.ts` defines richer session/phase types than the backend currently emits via `/api/sessions` — potential misalignment
3. `GET /api/capabilities` endpoint not implemented (agentic-layer skill recommends it for machine-to-machine discovery)
4. `scripts/smoke_test.py` does not exist — 22-check smoke test lives only in `.harness/qa/smoke-test.md`

**Resolved since Sprint 3:**
- ✅ `.harness/executive-summary.md` created (MCP board notes now fully functional)
- ✅ `token-budgeter/SKILL.md` cost fields filled in (Opus $15, Sonnet $3, Haiku $1.25 per M output)
- ✅ `ceo-mode` added to `tao-skills/SKILL.md` master index (23/23 skills indexed)

### 2.2 TAO Engine (`src/tao/`)

The Python engine provides a skills registry, tier config loading, budget tracking, and data schemas. All actual AI execution is delegated to the `claude` CLI subprocess — the engine does not call the Anthropic API directly.

| Module | Status | Purpose |
|--------|--------|---------|
| `schemas/artifacts.py` | ✅ Complete | `TaskSpec`, `TaskResult`, `Escalation` dataclasses |
| `tiers/config.py` | ✅ Complete | `TierConfig` dataclass, MODEL_MAP, YAML loader |
| `budget/tracker.py` | ✅ Complete | `BudgetTracker`: per-tier token accounting, `record(tier, tokens)` |
| `skills.py` | ✅ Complete | Skill loader/registry: frontmatter parser, `load_all_skills()`, `skills_for_intent()` |
| `agents/__init__.py` | ⚠️ Empty | Agent dispatch — not yet implemented |
| `templates/3-tier-webapp.yaml` | ✅ Present | Reference config: opus orchestrator + sonnet specialist + haiku workers |

**Engine integration points:**
- `sessions.py` imports `BudgetTracker`, `load_config`, `TaskSpec`, `TaskResult` on startup (soft-fails via `_TAO_AVAILABLE` flag)
- `brief.py` calls `skills_for_intent(intent)` to inject relevant skill bodies into every spec
- `.harness/config.yaml` is parsed by `load_config()` to drive `_select_model()` per phase

**Why delegate to `claude -p` rather than Python API calls?**
The Claude Max subscription includes zero-cost Claude Code execution. Calling `anthropic.Anthropic()` directly would incur per-token charges and require API key management. The CLI subprocess approach also gets native tool-use, file editing, and bash execution without re-implementing the harness.

### 2.3 Next.js Dashboard (`dashboard/`)

Deployed on Vercel at `https://pi-dev-ops.vercel.app`.

| Component | Purpose |
|-----------|---------|
| `app/(main)/dashboard/page.tsx` | Main analysis dashboard: repo input, terminal, phase tracker, results |
| `app/(main)/chat/page.tsx` | Chat interface |
| `app/(main)/history/page.tsx` | Build history |
| `app/(main)/settings/page.tsx` | Settings form |
| `hooks/useSSE.ts` | SSE client for streaming events from `/api/analyze` |
| `components/Terminal.tsx` | Live terminal output renderer |
| `components/PhaseTracker.tsx` | Phase status visualiser |
| `components/ResultCards.tsx` | Result card grid (ZTE score, leverage points, etc.) |
| `components/ActionsPanel.tsx` | Post-analysis action buttons |
| `lib/types.ts` | Shared TypeScript types: `Phase`, `Session`, `AnalysisResult`, `LeveragePoint` |

**Potential dashboard–backend gap:** The dashboard `types.ts` defines `Session.phases: Phase[]` and `AnalysisResult.leveragePoints: LeveragePoint[]` but the backend `/api/sessions` currently returns a flat status string, not structured phases. The dashboard's `/api/analyze` route (SSE) and the backend's `/api/build` + WebSocket flow may need reconciliation in Sprint 4.

### 2.4 MCP Server (`mcp/pi-ceo-server.js`)

Version 3.0.0. Built on `@modelcontextprotocol/sdk` (official subpath imports required: `sdk/server/mcp.js`, `sdk/server/stdio.js`).

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

**Dependencies:** `LINEAR_API_KEY` env var required for Linear tools. Configured in `%APPDATA%\Claude\claude_desktop_config.json`.

### 2.5 Harness State (`.harness/`)

| File | Status | Purpose |
|------|--------|---------|
| `config.yaml` | ✅ Present | Harness agent config (planner: opus, generator: sonnet, evaluator: sonnet) |
| `spec.md` | ✅ This document | Living product specification |
| `handoff.md` | ✅ Complete | Cross-session state, sprint history, architecture snapshot |
| `lessons.jsonl` | ✅ Seeded (18 entries) | Agent-expert institutional memory |
| `leverage-audit.md` | ✅ Present | 12-point ZTE diagnostic, full changelog from 35→60 |
| `sprint_plan.md` | ✅ Present | Sprint 3 items, completed sprint history |
| `feature_list.json` | ✅ Present | Feature list for MCP `get_feature_list` tool |
| `agents/planner.md` | ✅ Present | Planner agent tier 1 specification |
| `agents/evaluator.md` | ✅ Present | Evaluator agent tier 3 specification |
| `contracts/build-contract.md` | ✅ Present | Build contract spec |
| `contracts/eval-contract.md` | ✅ Present | Eval contract spec |
| `qa/smoke-test.md` | ✅ Present | Smoke test checklist (22 checks) |
| `qa/regression-checklist.md` | ✅ Present | Regression checklist |
| `templates/*.md` | ✅ Present | Feature/bugfix/chore brief templates |
| `board-meetings/` | ✅ Present | Autonomous board meeting minutes |
| `anthropic-docs/index.json` | ✅ Present | Fetched Anthropic documentation index |
| `cron-triggers.json` | ⚠️ Created at runtime | Cron trigger persistence |

---

## 3. Skills Analysis (23 of 23)

### Layer 1: Core (7 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `tier-architect` | Design model-to-role tier hierarchy | Partial | `.harness/config.yaml` partially implements; `agents/__init__.py` not implemented |
| `tier-orchestrator` | Top-tier planning + delegation patterns | ✅ | `orchestrator.py` fan-out pattern + brief decomposition |
| `tier-worker` | Discrete execution, escalation rules | ✅ | `run_build()` workers; escalation via opus fallback |
| `tier-evaluator` | QA grading with 4 dimensions | ✅ | Phase 4.5 in `sessions.py`; `evaluator.md` spec |
| `context-compressor` | Truncate/extract/summarize at tier boundaries | Partial | `build_structured_brief()` truncates skill bodies to 800 chars; no AI summarisation |
| `token-budgeter` | Track token spend per tier | Partial | `BudgetTracker` instantiated per session; cost values blank in skill file |
| `auto-generator` | Generate tier configs from project briefs | No | Presets defined; no code generates them yet |

### Layer 2: Frameworks (6 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `piter-framework` | 5-pillar AFK setup | ✅ | `classify_intent()` + 5 ADW templates enforced at brief entry |
| `afk-agent` | Bounded unattended runs with stop guards | ✅ | Phase pipeline has explicit success/failure termination |
| `closed-loop-prompt` | Self-correcting prompts with embedded verification | ✅ | Evaluator critique injected into retry prompt |
| `hooks-system` | 6 lifecycle hooks for observability + safety | Partial | PreToolUse (rate limit), PostToolUse (logging); Stop/SubagentStop not yet implemented |
| `agent-workflow` | 5 ADW templates | ✅ | Full templates in `brief.py`, routes all 5 intent types |
| `agentic-review` | 6-dimension quality review | ✅ | Evaluator covers 4 of 6 dimensions; Architecture + Naming not explicitly graded |

### Layer 3: Strategic (5 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `zte-maturity` | 3-level maturity model | ✅ | 60/60 achieved; Level 3 ZTE |
| `agent-expert` | Act-Learn-Reuse cycle | ✅ | Auto-learns from evaluator → `lessons.jsonl` → injected in next brief |
| `leverage-audit` | 12-point diagnostic | ✅ | `leverage-audit.md` maintained and read by MCP `get_zte_score` |
| `agentic-loop` | Two-prompt infinite loop | ✅ | Up to 3 evaluator rounds (max_iterations respected) |
| `agentic-layer` | Dual-interface design | Partial | Machine-readable JSON API exists; `capabilities` endpoint not implemented |

### Layer 4: Foundation (3 skills)

| Skill | Purpose | Wired In Code | Notes |
|-------|---------|---------------|-------|
| `big-three` | Model/Prompt/Context debugging | Partial | Model selection wired; prompt templating via ADW; context injection partial |
| `claude-max-runtime` | Tier mapping for Max subscription | ✅ | Tier mapping matches config.yaml; zero API cost |
| `pi-integration` | Multi-provider bridge | ✅ | Documented as contingency; not needed on Max plan |

### Meta (2 skills)

| Skill | Status |
|-------|--------|
| `ceo-mode` | ✅ Active — used this session |
| `tao-skills` | ⚠️ Missing `ceo-mode` in the 23-skill index (shows 23 but only lists 22 in text) |

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
| 10 | Trigger Automation | 5/5 | GitHub + Linear webhooks + cron triggers |
| 11 | Knowledge Retention | 5/5 | Auto-learn: low evaluator dims → lessons.jsonl → injected in next brief |
| 12 | Workflow Standardisation | 5/5 | PITER at brief entry; all 5 ADW templates active |

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

---

## 6. Improvement Recommendations (Sprint 4)

### Completed (this cycle)

**~~P4-A~~: ✅ `executive-summary.md` created**
MCP `get_last_analysis` now returns full content; board meeting generation functional.

**~~P4-B~~: ✅ `token-budgeter` skill cost fields filled in**
Opus $15, Sonnet $3, Haiku $1.25 per M output tokens documented in skill.

**~~P4-C~~: ✅ `ceo-mode` added to `tao-skills` master index**
All 23 skills correctly indexed; `skills_for_intent("spike")` returns `ceo-mode`.

### Priority 1 — High Impact, One Session

**P4-D: Implement `capabilities` endpoint (agentic-layer skill)**
- `GET /api/capabilities` → returns self-describing JSON of all available actions
- Enables machine-to-machine discovery of the API surface
- Impact: Agentic Layer skill fully satisfied; ZTE Level 3 capability published

### Priority 2 — Medium Impact, 1-3 Sessions

**P4-E: Dashboard–backend session data alignment**
- `dashboard/lib/types.ts` defines `Session.phases: Phase[]` but `/api/sessions` returns a flat status string
- Option A: Enrich backend `/api/sessions` response to include phase array
- Option B: Strip unused frontend types to match what the backend actually emits
- Recommendation: Option A — phases are already tracked in `session.last_completed_phase`; serialise the full `_PHASE_ORDER` array with per-phase status

**P4-F: Implement `src/tao/agents/__init__.py`**
- Currently empty; planner/evaluator agent specifications exist in `.harness/agents/`
- Implement `AgentDispatcher` class that reads `TierConfig` and calls `claude -p` subprocess
- Impact: Python-level orchestration becomes possible; enables programmatic task trees

**P4-G: E2E regression script (`scripts/smoke_test.py`)**
- Convert the 22-check smoke test from `.harness/qa/smoke-test.md` into a runnable Python script
- Can be used as pre-deploy gate and scheduled daily via cron trigger
- Impact: every push is validated; prevents regressions across sprints

**P4-H: `auto-generator` skill implementation**
- `auto-generator/SKILL.md` defines 3 presets (2-tier-codereview, 3-tier-webapp, 4-tier-research)
- Implement `generate_config(preset)` in `src/tao/` that produces a valid `config.yaml`
- Impact: brief onboarding for new repos — auto-select tier config from project type

### Priority 3 — Longer Horizon

**P4-I: ZTE Level 3 — Full system self-improvement loop**
- Evaluator low-score lessons are already written to `lessons.jsonl`
- Missing: a scheduled agent that reads recent lessons, identifies patterns, and proposes CLAUDE.md or skills updates
- This closes the ZTE loop: system detects its own weaknesses and improves its own prompts

**P4-J: Multi-model parallel evaluation (Agentic Loop upgrade)**
- Run evaluator with both Sonnet and Haiku simultaneously
- Accept if both agree; escalate to Opus if they disagree
- Impact: evaluation quality improves; cost stays low (Haiku is $0.25/M)

**P4-K: Linear API key for Pi CEO MCP**
- Add `LINEAR_API_KEY` to `claude_desktop_config.json` env block
- Currently the `linear_*` MCP tools fall back to an error message
- Impact: autonomous issue creation/update from Claude Desktop without Composio dependency

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
│       └── lessons.py                  ← JSONL lessons CRUD
│   ├── static/index.html               ← Minimal frontend
│   └── workspaces/                     ← Ephemeral session clones (GC'd at 4h)
│       └── {session_id}/               ← Isolated clone per session
├── dashboard/                          ← Next.js (Vercel-deployed)
│   ├── app/(main)/dashboard/page.tsx   ← Main dashboard
│   ├── app/(main)/chat/page.tsx        ← Chat interface
│   ├── app/(main)/history/page.tsx     ← Build history
│   ├── app/(main)/settings/page.tsx    ← Settings
│   ├── app/api/                        ← Next.js API routes (proxy to backend)
│   ├── components/                     ← Terminal, PhaseTracker, ResultCards, ActionsPanel
│   ├── hooks/useSSE.ts                 ← SSE client for streaming events
│   └── lib/types.ts                    ← Shared TypeScript types
├── mcp/
│   └── pi-ceo-server.js               ← MCP v3.0.0 (11 tools, Linear + harness reads)
├── skills/ (23 skills)
│   ├── [core: 7]    tier-architect, tier-orchestrator, tier-worker,
│   │                tier-evaluator, context-compressor, token-budgeter, auto-generator
│   ├── [fw: 6]      piter-framework, afk-agent, closed-loop-prompt,
│   │                hooks-system, agent-workflow, agentic-review
│   ├── [strat: 5]   zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer
│   ├── [found: 3]   big-three, claude-max-runtime, pi-integration
│   └── [meta: 2]    ceo-mode, tao-skills (master index — needs ceo-mode entry)
├── src/tao/
│   ├── skills.py                       ← ✅ Skill loader/registry, intent-to-skill mapping
│   ├── schemas/artifacts.py            ← TaskSpec, TaskResult, Escalation dataclasses
│   ├── tiers/config.py                 ← TierConfig, MODEL_MAP, YAML loader
│   ├── budget/tracker.py               ← BudgetTracker (per-tier token accounting)
│   ├── agents/__init__.py              ← ⚠️ EMPTY — agent dispatch not implemented
│   └── templates/3-tier-webapp.yaml    ← Reference 3-tier config (opus/sonnet/haiku)
├── supabase/migration.sql              ← DB schema (if Supabase integration active)
├── scripts/
│   ├── analyze.sh                      ← Analysis helper script
│   └── fetch_anthropic_docs.py         ← Daily docs pull (cron at 5:50am AEST)
├── .harness/
│   ├── config.yaml                     ← Harness agent config (planner/generator/evaluator)
│   ├── spec.md                         ← This document (living specification)
│   ├── handoff.md                      ← Cross-session state (Sprint 3 complete)
│   ├── leverage-audit.md               ← ZTE score 60/60 + full changelog
│   ├── sprint_plan.md                  ← Sprint 3 complete; Sprint 4 open
│   ├── lessons.jsonl                   ← 18 institutional memory entries
│   ├── feature_list.json               ← Feature list for MCP
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
│   ├── board-meetings/
│   │   └── 2026-04-08-1200-board-minutes.md  ← Autonomous board meeting
│   ├── anthropic-docs/index.json       ← Fetched Anthropic docs index
│   └── [cron-triggers.json]            ← Created at runtime by cron.py
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
WebSocket is bidirectional — the client can send `ping` frames and the server can terminate cleanly. SSE would also work but WS was chosen for its explicit connection lifecycle management. The dashboard `useSSE.ts` hook polls the SSE endpoint separately for analysis results, suggesting a future unification to either protocol.

---

## 9. Next Actions (Sprint 4)

```
[x] P4-A: Create .harness/executive-summary.md (DONE)
[x] P4-B: Fix token-budgeter/SKILL.md cost values (DONE — Opus $15, Sonnet $3, Haiku $1.25)
[x] P4-C: Add ceo-mode to tao-skills/SKILL.md master index (DONE)
[ ] P4-D: Implement GET /api/capabilities endpoint
[ ] P4-E: Align /api/sessions to emit Phase[] array (match dashboard types.ts)
[ ] P4-F: Implement src/tao/agents/__init__.py AgentDispatcher
[ ] P4-G: Build scripts/smoke_test.py from .harness/qa/smoke-test.md
[ ] P4-H: Add LINEAR_API_KEY to claude_desktop_config.json for MCP Linear tools
```

### Additional findings from Sprint 4 spike

**Skill registry cache:** `src/tao/skills.py` caches skills after first `load_all_skills()` call.
Hot-reload via `invalidate_cache()` is implemented but never called — a file watcher could wire this.

**Lesson fallback:** `_get_lesson_context()` in `brief.py` falls back to the 3 most recent lessons of any category when no intent-specific lessons exist. This means new intents bootstrap from general lessons rather than returning empty context.

**Health endpoint:** `GET /health` exists in `main.py` and returns `{"status": "ok", "sessions": N}` — not documented in the spec previously.

**BudgetTracker vs cost estimation gap:** `BudgetTracker.record(tier, tokens)` accumulates tokens per tier but has no cost calculation. The `token-budgeter` skill now has accurate pricing — wiring the two (adding a `cost_usd()` method to `BudgetTracker` using the skill's rates) would close this gap.

**`brief.py` note appended in spike sessions:** When this spike runs, the brief passed to Claude includes `[NOTE: Simplified due to previous failure. Focus on core task only.]` — this is the lesson injection system working: a previous failure lesson was included in the context, affecting the spec generated for this session.
