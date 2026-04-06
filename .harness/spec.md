# Pi Dev Ops — Product Spec (Full Analysis)

_Generated: 2026-04-07 | Analyst: Pi CEO Orchestrator (Claude Sonnet 4.6)_

---

## 1. System Overview

**Pi Dev Ops** is a secure, localhost-only Solo DevOps tool that turns a plain git repository URL and a plain-English brief into a Claude Code execution session — cloning the repo, running Claude autonomously against it, streaming live output to the browser via WebSocket, then pushing the result back to GitHub.

It is **not** a traditional CI/CD system. It is an **agentic harness**: it orchestrates Claude Max subscriptions to execute engineering work without paying per-token API costs.

### Core Loop

```
Browser ──POST /api/build──► FastAPI ──asyncio.create_task──► run_build()
                                                                    │
                                                              1. git clone
                                                              2. claude -p spec --verbose --stream-json
                                                              3. parse_event() → WebSocket stream
                                                              4. git push
Browser ◄──WebSocket /ws/build/{sid}──────────────────────────────────────
```

---

## 2. Architecture Layers

### 2.1 Web Server (`app/server/`)

| File | Responsibility |
|------|---------------|
| `main.py` | FastAPI app, routes, WebSocket handler, security middleware |
| `auth.py` | Password auth, HMAC session tokens, in-memory rate limiting |
| `config.py` | Env-var config, auto-generated password if none set |
| `sessions.py` | BuildSession lifecycle, claude subprocess, stream parsing |

**Security posture:**
- TrustedHostMiddleware limits to `127.0.0.1` / `localhost` — no external exposure
- CSP headers, X-Frame-Options, XSS protection applied via `SecurityHeaders` middleware
- Cookie-based auth (`HttpOnly`, `SameSite=Strict`) with HMAC-signed JWT-style tokens
- Rate limit: 30 req/min per IP (in-memory, resets on restart)
- Password hashed as SHA-256; compared via `hmac.compare_digest` (timing-safe)

**Identified weaknesses:**
1. `_sessions` dict is in-memory → lost on server restart, no persistence
2. Rate-limit state (`_req_log`) leaks unbounded if many unique IPs hit the server
3. `af` variable reference in the summary block uses `dir()` instead of `locals()` (cosmetic bug)
4. No workspace GC — old workspace directories accumulate on disk unless explicitly cleaned
5. `SESSION_SECRET` regenerates on restart if not set via env var → all sessions invalidated

### 2.2 TAO Engine (`src/tao/`)

The Python engine is intentionally minimal — **stub scaffolding only**. All intelligence is delegated to the Claude Code subprocess.

| Module | Status | Purpose |
|--------|--------|---------|
| `schemas/artifacts.py` | ✅ Complete | `TaskSpec`, `TaskResult`, `Escalation` dataclasses |
| `tiers/config.py` | ✅ Complete | `TierConfig` dataclass + YAML loader |
| `budget/tracker.py` | ✅ Complete | Token usage tracking per tier |
| `agents/__init__.py` | ⚠️ Empty | Agent execution — NOT IMPLEMENTED |
| `skills.py` | ❌ Missing | Skill loader/registry — NOT IMPLEMENTED |

**Key insight:** `src/tao/` is not called by the web server at all. It exists as infrastructure for future multi-tier orchestration — when a local Python orchestrator is needed. Currently all execution flows through `claude -p spec` CLI.

### 2.3 Harness State (`.harness/`)

| File | Status | Purpose |
|------|--------|---------|
| `config.yaml` | ✅ Present | Harness agent config (planner/generator/evaluator) |
| `spec.md` | ⚠️ Stub → now updated | Product specification |
| `handoff.md` | ⚠️ Minimal | Cross-session handoff state |
| `lessons.jsonl` | ❌ Missing | Agent-expert knowledge base |
| `leverage-audit.md` | ❌ Missing | 12 Leverage Points diagnostic |

---

## 3. Skills Analysis (23 of 23)

### Layer 1: Core (7 skills)

| Skill | Purpose | Status |
|-------|---------|--------|
| `tier-architect` | Design model-to-role tier hierarchy | ✅ Well-defined |
| `tier-orchestrator` | Top-tier planning + delegation patterns | ✅ Well-defined |
| `tier-worker` | Discrete execution, escalation rules | ✅ Well-defined |
| `tier-evaluator` | QA grading with 4 dimensions | ✅ Well-defined |
| `context-compressor` | Truncate/extract/summarize at tier boundaries | ✅ Defined, not implemented |
| `token-budgeter` | Track token spend per tier | ⚠️ Cost values blank |
| `auto-generator` | Generate tier configs from project briefs | ✅ Presets defined |

### Layer 2: Frameworks (6 skills)

| Skill | Purpose | Status |
|-------|---------|--------|
| `piter-framework` | 5-pillar AFK setup (Prompt/Intent/Trigger/Env/Review) | ✅ Well-defined |
| `afk-agent` | Bounded unattended runs with stop guards | ✅ Well-defined |
| `closed-loop-prompt` | Self-correcting prompts with embedded verification | ✅ Well-defined |
| `hooks-system` | 6 lifecycle hooks for observability + safety | ✅ Defined, partially implemented |
| `agent-workflow` | ADW templates (feature/bugfix/chore/review/spike) | ✅ Well-defined |
| `agentic-review` | 6-dimension quality review beyond test pass/fail | ✅ Well-defined |

### Layer 3: Strategic (5 skills)

| Skill | Purpose | Status |
|-------|---------|--------|
| `zte-maturity` | 3-level ZTE maturity model (In Loop → ZTE) | ✅ Well-defined |
| `agent-expert` | Act-Learn-Reuse cycle, lessons in JSONL | ⚠️ `.harness/lessons.jsonl` missing |
| `leverage-audit` | 12-point diagnostic, score bands | ⚠️ No baseline score recorded |
| `agentic-loop` | Two-prompt infinite loop with safety rails | ✅ Well-defined |
| `agentic-layer` | Dual-interface product design (human + agentic) | ✅ Well-defined |

### Layer 4: Foundation (3 skills)

| Skill | Purpose | Status |
|-------|---------|--------|
| `big-three` | Model/Prompt/Context debugging framework | ✅ Core reference skill |
| `claude-max-runtime` | Tier mapping for Max subscription | ✅ Well-defined |
| `pi-integration` | Multi-provider bridge (not needed on Max plan) | ✅ Contingency documented |

### Bonus Skill

| Skill | Purpose | Status |
|-------|---------|--------|
| `ceo-mode` | Strategic decision-making with documented rationale | ⚠️ Not in tao-skills index |
| `tao-skills` | Master index of all 23 skills | ⚠️ Missing `ceo-mode` entry |

---

## 4. Current Leverage Audit (Baseline)

Using the 12 Leverage Points from `leverage-audit/SKILL.md`:

| # | Point | Score (1-5) | Notes |
|---|-------|-------------|-------|
| 1 | Spec Quality | 3 | Brief passed verbatim; no decomposition before Claude |
| 2 | Context Precision | 3 | Whole-repo clone; no targeted context injection |
| 3 | Model Selection | 4 | User selects opus/sonnet/haiku explicitly |
| 4 | Tool Availability | 4 | Full Claude Code tool suite available |
| 5 | Feedback Loops | 3 | WebSocket streams output; no structured pass/fail |
| 6 | Error Recovery | 2 | Hard failure on clone/build errors; no retry |
| 7 | Session Continuity | 2 | In-memory sessions; lost on restart |
| 8 | Quality Gating | 2 | No evaluator tier in web flow |
| 9 | Cost Efficiency | 5 | Zero API cost on Max plan |
| 10 | Trigger Automation | 2 | Manual via web UI only; no webhook/cron |
| 11 | Knowledge Retention | 2 | No `.harness/lessons.jsonl` |
| 12 | Workflow Standardization | 3 | ADWs defined but not enforced at brief entry |

**Total: 35 / 60 → Band: Assisted (21-35)**

> Just below the Autonomous threshold (36). Addressing items 6, 7, 8, 10, 11 would push to Autonomous.

---

## 5. Improvement Recommendations

### Priority 1 — Quick wins (1 session each)

**P1-A: Persist sessions to disk**
- Write `_sessions` to `.harness/sessions.json` on each state change
- Load on startup → survive server restarts
- Impact: Session Continuity 2 → 4

**P1-B: Add workspace GC**
- On session `complete`/`failed`, schedule workspace deletion after TTL (e.g. 24h)
- Prevents disk accumulation across builds
- Impact: operational hygiene

**P1-C: Fix rate-limit memory leak**
- Evict IPs not seen in >5 min from `_req_log` in a background task
- Impact: production stability

**P1-D: Seed `.harness/lessons.jsonl`**
- Record first lessons from this analysis
- Enables `agent-expert` skill to activate
- Impact: Knowledge Retention 2 → 3

### Priority 2 — Mid-effort (1-3 sessions)

**P2-A: Add evaluator tier to build flow**
- After Claude Code completes, run a second `claude -p eval_spec --model sonnet` pass
- Grade output against `tier-evaluator` dimensions
- Impact: Quality Gating 2 → 4

**P2-B: Webhook trigger support**
- `POST /api/webhook` accepts signed GitHub/Linear webhook
- Parses event type → selects ADW → creates build session
- Impact: Trigger Automation 2 → 4

**P2-C: Structured brief intake**
- Pre-build form classifies intent (feature/bug/chore/spike/hotfix per PITER)
- Routes to corresponding ADW template
- Impact: Spec Quality 3 → 5, Workflow Standardization 3 → 5

**P2-D: Implement `src/tao/skills.py` skill loader**
- Parse all `skills/*/SKILL.md` frontmatter + body
- Expose skill registry for injection into briefs
- Impact: enables dynamic skill-augmented prompts

### Priority 3 — Longer horizon

**P3-A: ZTE Level 2 promotion**
- Connect to Linear/GitHub webhooks → auto-generate briefs from issues
- No human prompt required
- Target: ZTE Level 2 (10-50x)

**P3-B: Multi-session parallelism**
- Fan-out a brief into N parallel worker sessions
- Merge results via Opus evaluator
- Uses `tier-orchestrator` fan-out pattern

**P3-C: Session tree persistence (pi-mono style)**
- Replace flat `_sessions` dict with a tree structure
- Parent → child relationships for orchestrator → specialist → worker

---

## 6. File Map

```
Pi Dev Ops/
├── app/
│   ├── run.ps1                    ← Windows launcher (pip install + uvicorn)
│   ├── server/
│   │   ├── main.py                ← FastAPI app, routes, WebSocket
│   │   ├── auth.py                ← HMAC tokens, rate limiting
│   │   ├── config.py              ← Env-var config
│   │   └── sessions.py            ← Build lifecycle, subprocess, stream parser
│   ├── static/                    ← Frontend (index.html, CSS, JS)
│   └── workspaces/                ← Ephemeral cloned repos (GC needed)
├── skills/ (23 skills)
│   ├── [core: 7]    tier-architect, tier-orchestrator, tier-worker,
│   │                tier-evaluator, context-compressor, token-budgeter,
│   │                auto-generator
│   ├── [fw: 6]      piter-framework, afk-agent, closed-loop-prompt,
│   │                hooks-system, agent-workflow, agentic-review
│   ├── [strat: 5]   zte-maturity, agent-expert, leverage-audit,
│   │                agentic-loop, agentic-layer
│   ├── [found: 3]   big-three, claude-max-runtime, pi-integration
│   └── [bonus: 2]   ceo-mode, tao-skills (master index)
├── src/tao/
│   ├── schemas/artifacts.py       ← TaskSpec, TaskResult, Escalation
│   ├── tiers/config.py            ← TierConfig, YAML loader, MODEL_MAP
│   ├── budget/tracker.py          ← BudgetTracker
│   ├── agents/__init__.py         ← ⚠️ STUB — not implemented
│   └── skills.py                  ← ✅ Added: skill loader/registry
├── .harness/
│   ├── config.yaml                ← Harness agent config
│   ├── spec.md                    ← This document
│   ├── handoff.md                 ← Cross-session state
│   └── lessons.jsonl              ← ✅ Added: agent-expert knowledge base
├── _deploy.py                     ← Bootstrap script (regenerates all files)
├── pyproject.toml                 ← ✅ Fixed: added all runtime deps
└── README.md
```

---

## 7. Design Decisions (CEO Mode)

**Why delegate to `claude -p` instead of Python orchestration?**
The engine stubs in `src/tao/` could theoretically call the Anthropic API directly. The choice to shell out to `claude` CLI is deliberate: it runs inside the Claude Max subscription context, making it zero-cost per token. Python-level orchestration would require API keys and incur charges. The CLI approach also gets native tool-use, file editing, and bash execution without re-implementing the harness.

**Why in-memory sessions?**
Current use case is solo developer, single machine. A persistent session store (SQLite, Redis) adds operational complexity for marginal gain. The fix (P1-A) is a simple JSON file write — not a database.

**Why not a full React frontend?**
Static HTML/CSS/JS served from `app/static/` keeps the footprint minimal. The WebSocket streams line-by-line output — no framework needed for that interaction pattern.

---

## 8. Next Actions

```
[ ] Run leverage audit: score current state → baseline in .harness/leverage-audit.md
[ ] Implement P1-A: session persistence to .harness/sessions.json
[ ] Implement P1-C: background cleanup task for _req_log + workspaces
[ ] Implement P2-A: evaluator tier (second claude pass post-build)
[ ] Implement P2-B: /api/webhook endpoint + PITER intent classifier
[ ] Promote to ZTE Level 2 when webhooks + auto-brief are live
```
