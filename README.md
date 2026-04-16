# Pi CEO — Autonomous DevOps Agent

![Smoke Test](https://github.com/CleanExpo/Pi-Dev-Ops/actions/workflows/smoke_test.yml/badge.svg)

**Private agentic engineering system powered by Claude Harness.**

Pi CEO converts a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session — cloning the repo, running Claude against it, streaming live output to the browser, and pushing the result back to GitHub. Zero API cost on Claude Max.

## Architecture

Pi CEO uses a **Tiered Agent Orchestrator (TAO)** model with three Claude tiers:

| Tier | Model | Role |
|------|-------|------|
| Orchestrator | Opus 4.7 | Plans, decomposes, reviews |
| Specialist | Sonnet 4.6 | Complex features, code review |
| Worker | Haiku 4.5 | Discrete tasks, fast execution |

The system includes **33 skills** organised across 4 layers (Core, Frameworks, Strategic, Foundation) that encode engineering methodology — from tier architecture and agent workflows to ZTE maturity scoring and leverage audits.

## Components

### Backend (FastAPI)

Python server (`app/server/`) deployed to Railway at `https://pi-dev-ops-production.up.railway.app`. Handles authentication, build session management, and live WebSocket streaming.

The backend is decomposed into focused modules (≤300L each):
- `app_factory.py` — FastAPI app, CORS/security middleware, startup hooks
- `models.py` — Pydantic request models
- `routes/` — 8 route modules (auth, sessions, webhooks, triggers, scan_monitor, pipeline, utils, health)

### Dashboard (Next.js)

Frontend (`dashboard/`) deployed to Vercel at `https://dashboard-unite-group.vercel.app`. Runs analysis phases against GitHub repos using Claude. Supports dual-mode execution: CLI (Claude Max, zero cost) or SDK (Anthropic API key). Built with Next.js 16, React 19, Tailwind, and Octokit.

### MCP Server

stdio JSON-RPC 2.0 server (`mcp/pi-ceo-server.js`) that connects Claude Desktop and Cowork to Pi CEO analysis outputs. Exposes tools for retrieving analysis results, generating board notes, sprint plans, and ZTE scores.

## Quick Start

### Local Backend

```bash
cd app
source .env.local
uvicorn server.main:app --host 127.0.0.1 --port 7777
# Open http://127.0.0.1:7777
```

### Dashboard (Development)

```bash
cd dashboard
cp .env.example .env.local
# Edit .env.local with your settings
npm install
npm run dev
# Open http://localhost:3000
```

### Docker

```bash
docker build -t pi-ceo .
docker run -p 7777:7777 -e TAO_PASSWORD=your-password pi-ceo
```

## Environment Variables

### Backend (Railway)

| Variable | Required | Description |
|----------|----------|-------------|
| `TAO_PASSWORD` | **Yes** | Dashboard login password |
| `ANTHROPIC_API_KEY` | **Yes** | `sk-ant-` key — required for Claude sessions |
| `LINEAR_API_KEY` | **Yes** | `lin_api_` key — required for autonomy poller |
| `TAO_SESSION_SECRET` | Optional | HMAC signing key (auto-generated on first boot) |
| `TAO_ALLOWED_ORIGINS` | Optional | Extra CORS origins (comma-separated) |
| `TAO_AUTONOMY_ENABLED` | Optional | Set to `0` to disable Linear todo poller (default: `1`) |
| `TAO_WEBHOOK_SECRET` | Optional | HMAC secret for GitHub webhook verification |
| `TAO_LINEAR_WEBHOOK_SECRET` | Optional | HMAC secret for Linear webhook verification |
| `TELEGRAM_BOT_TOKEN` | Optional | Telegram bot for alerts and `/ack_alert` |
| `PI_SEO_ACTIVE` | Optional | Set to `1` to enable Pi-SEO live scans (default: `0`) |

### Dashboard (Vercel)

| Variable | Required | Description |
|----------|----------|-------------|
| `PI_CEO_URL` | **Yes** (prod) | Backend URL |
| `PI_CEO_PASSWORD` | **Yes** (prod) | Same value as `TAO_PASSWORD` |
| `NEXT_PUBLIC_SUPABASE_URL` | Optional | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Optional | Supabase public anon key |
| `ANTHROPIC_API_KEY` | Optional | For direct AI calls from dashboard routes |

## Production URLs

| Service | URL |
|---------|-----|
| Dashboard | https://dashboard-unite-group.vercel.app |
| Backend API | https://pi-dev-ops-production.up.railway.app |
| Health | https://pi-dev-ops-production.up.railway.app/health |

## MCP Server Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pi-ceo": {
      "command": "node",
      "args": ["/path/to/Pi-Dev-Ops/mcp/pi-ceo-server.js"]
    }
  }
}
```

**Available tools:**

| Tool | Description |
|------|-------------|
| `get_last_analysis` | Full spec + executive summary from last run |
| `generate_board_notes` | Formatted board meeting notes |
| `get_sprint_plan` | Prioritised sprint items |
| `get_feature_list` | Full feature JSON |
| `list_harness_files` | Contents of `.harness/` directory |
| `get_zte_score` | ZTE maturity score and leverage breakdown |

## Security

- Deployed to Railway (HTTPS) — CSP, X-Frame-Options, X-XSS-Protection headers enforced
- HttpOnly, SameSite=None cookies (SameSite=Strict locally) with HMAC-signed tokens
- Rate limiting: 30 req/min per IP
- bcrypt password hashing with SHA-256 migration path
- HMAC verification on all webhook endpoints

## Skills (33)

**Core (7):** tier-architect, tier-orchestrator, tier-worker, tier-evaluator, context-compressor, token-budgeter, auto-generator

**Frameworks (6):** piter-framework, afk-agent, closed-loop-prompt, hooks-system, agent-workflow, agentic-review

**Strategic (5):** zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer

**Pi-SEO (3):** pi-seo-scanner, pi-seo-health-monitor, pi-seo-remediation

**Ship Chain (2):** ship-chain, ship-release

**Foundation + Ops (10):** big-three, claude-max-runtime, pi-integration, ceo-mode, tao-skills, maintenance-manager, scheduled-tasks, security-audit, architecture, define-spec

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, WebSockets
- **Dashboard:** Next.js 16, React 19, TypeScript, Tailwind CSS
- **AI:** Claude Max (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) via `claude_agent_sdk`
- **Integrations:** @anthropic-ai/sdk, @octokit/rest, MCP (stdio), Linear, Supabase, Telegram
- **Deployment:** Vercel (dashboard), Railway (backend, Docker)

## License

Private repository. All rights reserved.
