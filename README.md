# Pi CEO — Solo DevOps Tool

**Private agentic engineering system powered by Claude Harness.**

Pi CEO turns a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session — cloning the repo, running Claude against it, streaming live output to the browser, and pushing the result back to GitHub. Zero API cost on Claude Max.

## Architecture

Pi CEO uses a **Tiered Agent Orchestrator (TAO)** model with three Claude tiers:

| Tier | Model | Role |
|------|-------|------|
| Orchestrator | Opus 4.6 | Plans, decomposes, reviews |
| Specialist | Sonnet 4.6 | Complex features, code review |
| Worker | Haiku 4.5 | Discrete tasks, fast execution |

The system includes **23 skills** organised across 4 layers (Core, Frameworks, Strategic, Foundation) that encode engineering methodology — from tier architecture and agent workflows to ZTE maturity scoring and leverage audits.

## Components

### Backend (FastAPI)

Local Python server (`app/server/`) running on `http://127.0.0.1:7777`. Handles authentication, build session management, and live WebSocket streaming. Delegates all intelligence to `claude -p` subprocess running inside the Claude Max subscription.

### Dashboard (Next.js)

Rich frontend (`dashboard/`) deployed to Vercel. Runs 8 analysis phases against GitHub repos using Claude. Supports dual-mode execution: CLI (Claude Max, zero cost) or SDK (Anthropic API key). Built with Next.js 16, React 19, Tailwind, and Octokit.

### MCP Server

stdio JSON-RPC 2.0 server (`mcp/pi-ceo-server.js`) that connects Claude Desktop and Cowork to Pi CEO analysis outputs. Exposes tools for retrieving analysis results, generating board notes, sprint plans, and ZTE scores.

## Quick Start

### Local Backend (Windows)

```powershell
cd "C:\Pi Dev Ops\app"
$env:TAO_PASSWORD="your-password"
.\run.ps1
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
cd app
docker build -t pi-ceo .
docker run -p 7777:7777 -e TAO_PASSWORD=your-password pi-ceo
```

## Environment Variables

| Variable | Location | Description |
|----------|----------|-------------|
| `TAO_PASSWORD` | Backend | Login password (auto-generated if unset) |
| `SESSION_SECRET` | Backend | HMAC signing key (auto-generated if unset) |
| `TAO_ALLOWED_ORIGINS` | Backend | Extra CORS origins (comma-separated) |
| `NEXT_PUBLIC_API_URL` | Dashboard | Backend URL (default: `http://127.0.0.1:7777`) |
| `ANALYSIS_MODE` | Dashboard | `cli` (Claude Max) or `api` (Anthropic SDK) |
| `ANTHROPIC_API_KEY` | Dashboard | Required when `ANALYSIS_MODE=api` |
| `GITHUB_TOKEN` | Dashboard | GitHub PAT for private repo access |

## Deployment

The **dashboard** is deployed to Vercel. The root `vercel.json` sets `"rootDirectory": "dashboard"`. The Vercel build runs `npm run build` inside the `dashboard/` directory.

The **backend** runs locally or on cloud platforms (Railway, Render, Fly.io detected automatically). Cloud mode enables `SameSite=None` + `Secure` cookies for cross-origin requests from the Vercel dashboard.

CORS is configured to allow requests from `localhost:3000`, `pi-dev-ops.vercel.app`, and `dashboard-unite-group.vercel.app`.

## MCP Server Setup

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pi-ceo": {
      "command": "node",
      "args": ["C:\\Pi Dev Ops\\mcp\\pi-ceo-server.js"]
    }
  }
}
```

**Available tools in Claude Desktop / Cowork:**

| Tool | Description |
|------|-------------|
| `get_last_analysis` | Full spec + executive summary from last run |
| `generate_board_notes` | Formatted board meeting notes |
| `get_sprint_plan` | Prioritised sprint items |
| `get_feature_list` | Full feature JSON |
| `list_harness_files` | Contents of `.harness/` directory |
| `get_zte_score` | ZTE maturity score and leverage breakdown |

## Security

- Localhost-only by default (no external exposure)
- CSP, X-Frame-Options (DENY), X-XSS-Protection headers
- HttpOnly, SameSite=Strict cookies with HMAC-signed tokens
- Rate limiting: 30 req/min per IP
- Password hashed as SHA-256, compared via `hmac.compare_digest` (timing-safe)

## Skills (23)

**Core (7):** tier-architect, tier-orchestrator, tier-worker, tier-evaluator, context-compressor, token-budgeter, auto-generator

**Frameworks (6):** piter-framework, afk-agent, closed-loop-prompt, hooks-system, agent-workflow, agentic-review

**Strategic (5):** zte-maturity, agent-expert, leverage-audit, agentic-loop, agentic-layer

**Foundation (3):** big-three, claude-max-runtime, pi-integration

**Bonus (2):** ceo-mode, tao-skills

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Uvicorn, WebSockets
- **Dashboard:** Next.js 16, React 19, TypeScript, Tailwind CSS
- **AI:** Claude Max (Opus 4.6 / Sonnet 4.6 / Haiku 4.5)
- **Integrations:** @anthropic-ai/sdk, @octokit/rest, MCP (stdio)
- **Deployment:** Vercel (dashboard), Docker (backend)

## License

Private repository. All rights reserved.
