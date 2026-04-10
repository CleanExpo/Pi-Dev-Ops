# Pi-Dev-Ops — Claude Code Guidance

## Project Context

Pi-Dev-Ops is a Zero Touch Engineering (ZTE) platform that converts a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session. The generator and evaluator can run via the `claude_agent_sdk` Python SDK (preferred) or via `claude -p` subprocess (fallback). Set `TAO_USE_AGENT_SDK=1` to activate the SDK path.

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
- **Phase pipeline:** 5-6 phases in `app/server/sessions.py`, parsed by `dashboard/lib/phases.ts`
- **Settings:** Supabase-backed via `dashboard/lib/supabase/settings.ts`
- **MCP tools:** `mcp/pi-ceo-server.js` — 21 tools for harness reads + Linear operations

## SDK Architecture (Phase 2 — RA-571/572)

The build pipeline supports two invocation modes, selected by `TAO_USE_AGENT_SDK`:

| Path | Flag | Function | File |
|------|------|----------|------|
| SDK (preferred) | `TAO_USE_AGENT_SDK=1` | `_run_claude_via_sdk()` | `sessions.py` |
| Subprocess (fallback) | `TAO_USE_AGENT_SDK=0` (default) | `asyncio.create_subprocess_exec` | `sessions.py` |

**Generator:** `_phase_generate()` tries SDK first; falls back to subprocess on import/runtime error.
**Evaluator:** `_run_single_eval()` tries SDK first; falls back to subprocess on error.
**Retry loop:** `_phase_evaluate()` retry generation uses the same SDK-first pattern.
**Metrics:** Every SDK invocation emits a row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. Analyse with `python scripts/sdk_metrics.py`.

SDK reference implementation: `app/server/agents/board_meeting.py::_run_prompt_via_sdk()` (Phase 1, verified working). Version policy: `.harness/agents/sdk-version-policy.md`.

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` env var in Claude Desktop config

## Strategic Direction

**Sprint 8:** Agent SDK migration Phase 2 complete (RA-571/572). Generator and evaluator in `sessions.py` now try `claude_agent_sdk` first with subprocess fallback. Canary rollout plan: RA-574. Phase 3 (remove subprocess fallback): RA-576 — gated on 7-day canary stability.

**Autonomy:** `app/server/autonomy.py` polls Linear every 5 min for Urgent/High unstarted issues and auto-creates sessions. Kill switch: `TAO_AUTONOMY_ENABLED=0` in Railway env.

## Persistence Guidelines

- `_sessions` is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- Use write-to-.tmp-then-`os.replace()` for JSON file writes. `os.replace()` is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written file.

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
