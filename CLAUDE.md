# CLAUDE.md — Pi Dev Ops

## Project

- **Name:** Pi Dev Ops (Pi CEO)
- **Repo:** https://github.com/CleanExpo/Pi-Dev-Ops.git (private)
- **Local:** C:\Pi Dev Ops
- **Runtime:** Claude Max (zero API cost)
- **Vercel Dashboard:** https://pi-dev-ops-git-main-unite-group.vercel.app/

## Models

| Tier | Model | Role |
|------|-------|------|
| Orchestrator | Claude Opus 4.6 | Plans, decomposes, reviews |
| Specialist | Claude Sonnet 4.6 | Complex features, code review |
| Worker | Claude Haiku 4.5 | Discrete tasks, fast execution |

## Quick Start (Local)

```powershell
cd "C:\Pi Dev Ops\app"
$env:TAO_PASSWORD="<your-password>"
.\run.ps1
# Open http://127.0.0.1:7777
```

## Repository Structure

```
Pi-Dev-Ops/
├── app/                          # FastAPI backend (localhost:7777)
│   ├── server/
│   │   ├── main.py               # FastAPI app, routes, WebSocket handler, security middleware
│   │   ├── auth.py               # HMAC session tokens, password auth, rate limiting (30 req/min)
│   │   ├── config.py             # Env-var config, auto-generated password if none set
│   │   └── sessions.py           # BuildSession lifecycle, claude subprocess, stream parser
│   ├── static/                   # Frontend (index.html, CSS, JS)
│   ├── run.ps1                   # Windows launcher (pip install + uvicorn)
│   ├── Dockerfile                # Container build
│   └── requirements.txt          # Python deps: fastapi, uvicorn, websockets, httpx
├── dashboard/                    # Next.js 16 frontend (deployed to Vercel)
│   ├── app/
│   │   ├── page.tsx              # Cinematic landing page (PI CEO hero)
│   │   ├── layout.tsx            # Root layout
│   │   ├── globals.css           # Tailwind styles
│   │   ├── (main)/               # Dashboard route group
│   │   └── api/                  # Next.js API routes
│   │       ├── analyze/          # Repo analysis endpoint
│   │       ├── actions/          # Action execution endpoint
│   │       ├── chat/             # Chat with Claude endpoint
│   │       └── telegram/         # Telegram bot webhook
│   ├── components/
│   │   ├── ActionsPanel.tsx      # Action buttons and controls
│   │   ├── PhaseTracker.tsx      # Analysis phase progress tracker
│   │   ├── ResultCards.tsx       # Analysis result display cards
│   │   └── Terminal.tsx          # Live output terminal
│   ├── hooks/                    # React hooks
│   ├── lib/
│   │   ├── claude.ts             # Dual-mode Claude client (CLI for Max, SDK for API)
│   │   ├── github.ts             # Octokit GitHub client (repo context, branches, PRs)
│   │   ├── phases.ts             # 8 analysis phase definitions and prompts
│   │   ├── types.ts              # TypeScript type definitions
│   │   └── vercel-api.ts         # Vercel deployment API client
│   ├── package.json              # next, react 19, @anthropic-ai/sdk, @octokit/rest
│   ├── next.config.ts            # CSP headers, security config
│   ├── tailwind.config.ts        # Tailwind theme
│   └── vercel.json               # Vercel build config (framework: nextjs)
├── mcp/
│   └── pi-ceo-server.js          # MCP server (stdio JSON-RPC 2.0) for Claude Desktop
├── skills/                       # 23 TAO skills (4 layers)
│   ├── [core: 7]                 # tier-architect, tier-orchestrator, tier-worker,
│   │                             # tier-evaluator, context-compressor, token-budgeter,
│   │                             # auto-generator
│   ├── [frameworks: 6]           # piter-framework, afk-agent, closed-loop-prompt,
│   │                             # hooks-system, agent-workflow, agentic-review
│   ├── [strategic: 5]            # zte-maturity, agent-expert, leverage-audit,
│   │                             # agentic-loop, agentic-layer
│   ├── [foundation: 3]           # big-three, claude-max-runtime, pi-integration
│   └── [bonus: 2]                # ceo-mode, tao-skills (master index)
├── src/tao/                      # Python orchestration engine (stub scaffolding)
│   ├── schemas/artifacts.py      # TaskSpec, TaskResult, Escalation dataclasses
│   ├── tiers/config.py           # TierConfig, YAML loader, MODEL_MAP
│   ├── budget/tracker.py         # BudgetTracker (token usage per tier)
│   ├── agents/__init__.py        # ⚠️ STUB — not implemented
│   └── templates/                # Prompt templates
├── scripts/
│   └── analyze.sh                # Analysis shell script
├── .harness/                     # Harness state (cross-session persistence)
│   ├── config.yaml               # Harness agent config (planner/generator/evaluator)
│   ├── spec.md                   # Product specification (full analysis)
│   └── handoff.md                # Cross-session handoff state
├── .claude/                      # Claude Code config
├── _deploy.py                    # Bootstrap script (regenerates all files)
├── vercel.json                   # Root Vercel config: { "rootDirectory": "dashboard" }
└── pyproject.toml                # Python project: tao v1.0.0, requires python >=3.11
```

## Core Loop

```
Browser ──POST /api/build──▶ FastAPI ──asyncio.create_task──▶ run_build()
                                                                │
                                                           1. git clone
                                                           2. claude -p spec --verbose --stream-json
                                                           3. parse_event() → WebSocket stream
                                                           4. git push
Browser ◄──WebSocket /ws/build/{sid}──────────────────────────────┘
```

## Dashboard Analysis Flow (Vercel)

The Next.js dashboard runs 8 analysis phases against a GitHub repo using Claude (CLI mode on Max, SDK mode with API key). Phases are defined in `dashboard/lib/phases.ts`. The dashboard fetches repo context via Octokit, builds a context string from file contents, and streams Claude's output per phase.

## Environment Variables

### Backend (`app/server/`)
- `TAO_PASSWORD` — Login password (required, auto-generated if unset)
- `SESSION_SECRET` — HMAC signing key (auto-generated if unset, regenerates on restart)
- `TAO_ALLOWED_ORIGINS` — Extra CORS origins (comma-separated)
- `RAILWAY_ENVIRONMENT` / `RENDER` / `FLY_APP_NAME` — Cloud detection flags

### Dashboard (`dashboard/`)
- `NEXT_PUBLIC_API_URL` — Backend URL (default: `http://127.0.0.1:7777`)
- `ANALYSIS_MODE` — `cli` (Claude Max) or `api` (Anthropic SDK)
- `ANTHROPIC_API_KEY` — Required when `ANALYSIS_MODE=api`
- `GITHUB_TOKEN` — GitHub personal access token for private repo access

## MCP Server

The MCP server (`mcp/pi-ceo-server.js`) connects Claude Desktop/Cowork to Pi CEO. Register in `%APPDATA%\Claude\claude_desktop_config.json`. Transport: stdio (JSON-RPC 2.0).

**Tools exposed:**
- `get_last_analysis` — Reads `.harness/spec.md` + executive summary
- `generate_board_notes` — Formats exec summary as board meeting notes
- `get_sprint_plan` — Returns prioritised sprint items
- `get_feature_list` — Returns full feature JSON
- `list_harness_files` — Shows `.harness/` directory contents
- `get_zte_score` — ZTE maturity score and leverage breakdown

## Security

- CSP headers, X-Frame-Options (DENY), XSS protection on all responses
- Cookie-based auth: HttpOnly, SameSite=Strict (local) / None+Secure (cloud)
- HMAC-signed session tokens with timing-safe comparison
- Rate limiting: 30 requests/min per IP (in-memory)
- CORS restricted to localhost:3000, Vercel domains, and configured origins

## Key Design Decisions

- **Claude CLI over Python orchestration:** Shells out to `claude -p` to run inside Claude Max subscription context (zero cost per token). Python-level orchestration would require API keys and incur charges.
- **In-memory sessions:** Solo developer, single machine. JSON file persistence (P1-A) planned.
- **Static frontend for backend:** Minimal HTML/CSS/JS in `app/static/`. Next.js dashboard is the rich UI deployed separately to Vercel.

## Leverage Audit Baseline

**Score: 35/60 (Assisted band)** — Just below Autonomous threshold (36).

Weakest points: Error Recovery (2), Session Continuity (2), Quality Gating (2), Trigger Automation (2), Knowledge Retention (2).

## Commands

```bash
# Local backend
cd "C:\Pi Dev Ops\app" && $env:TAO_PASSWORD="<pw>" && .\run.ps1

# Dashboard dev
cd dashboard && npm install && npm run dev

# Build dashboard
cd dashboard && npm run build
```
