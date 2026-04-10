# Pi-Dev-Ops — Claude Code Guidance

## Project Context

Pi-Dev-Ops is a Zero Touch Engineering (ZTE) platform that converts a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session. It runs on Claude Max (zero per-token cost via `claude` CLI subprocess).

**ZTE Score:** 60/60 (all 12 leverage points at maximum)

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js 16.2.2, React 19, Tailwind | `dashboard/` |
| Backend | FastAPI, Python 3.11+ | `app/server/` |
| MCP Server | Node.js, @modelcontextprotocol/sdk | `mcp/` |
| TAO Engine | Python (skills, tiers, budget) | `src/tao/` |
| Harness State | YAML/JSON/Markdown | `.harness/` |
| Skills | 28 SKILL.md files | `skills/` |
| Database | Supabase (PostgreSQL) | `supabase/` |
| Deploy (FE) | Vercel | `dashboard/vercel.json` |
| Deploy (BE) | Railway | `railway.toml`, `Dockerfile` |

## Development Setup

```bash
# Backend
cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777

# Frontend
cd dashboard && npm run dev

# MCP server (Claude Desktop picks this up from config)
node mcp/pi-ceo-server.js
```

## Running Tests

```bash
# Smoke test (requires running server)
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD

# Frontend type check
cd dashboard && npx tsc --noEmit

# Frontend build
cd dashboard && npm run build
```

## Code Conventions

- **Python:** snake_case, type hints on all functions, `logging.getLogger()` (no `print()`), structured JSON logging via `_JsonFormatter`
- **TypeScript:** strict mode, no `any`, named exports, interfaces over types for objects
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`, `chore:`)
- **Branches:** `feature/{ticket-id}-{short-desc}` or `fix/{ticket-id}-{short-desc}`
- **Functions:** Under 40 lines. Files under 300 lines. Extract when exceeding.
- **Security:** bcrypt passwords, parameterised queries, CSP headers, no secrets in code

## Key Patterns

- **Password auth:** bcrypt with transparent SHA-256 migration (`app/server/auth.py`)
- **Session secret:** Persisted to `app/data/.session-secret` (survives restarts)
- **SSE streaming:** `dashboard/hooks/useSSE.ts` with exponential backoff reconnection
- **Phase pipeline:** 8 phases in `app/server/sessions.py`, parsed by `dashboard/lib/phases.ts`
- **Settings:** Supabase-backed via `dashboard/lib/supabase/settings.ts`
- **MCP tools:** `mcp/pi-ceo-server.js` — 11 tools for harness reads + Linear operations

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` env var in Claude Desktop config

## Strategic Direction

**Sprint 6:** Agent SDK migration (RA-551). Migrating from `claude -p` subprocess to `claude_agent_sdk` in three phases. Plan: `.harness/agents/sdk-migration-plan.md`. Phase 1 (board_meeting gap audit) complete — `TAO_USE_AGENT_SDK=1` to enable.

## Persistence Guidelines

- `_sessions` is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- Use write-to-.tmp-then-`os.replace()` for JSON file writes. `os.replace()` is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written file.

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
