# Pi-Dev-Ops — Claude Code Guidance

## Project Context

Pi-Dev-Ops is a Zero Touch Engineering (ZTE) platform that converts a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session. The generator and evaluator can run via the `claude_agent_sdk` Python SDK (preferred) or via `claude -p` subprocess (fallback). Set `TAO_USE_AGENT_SDK=1` to activate the SDK path.

**ZTE Score:** 73/75 (Sprint 8 — see `.harness/leverage-audit.md` for full breakdown)

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

## SDK Architecture (Phase 3 Complete — RA-576)

The build pipeline runs **SDK-only** as of Sprint 8 (RA-576). The `claude -p` subprocess fallback paths have been removed from `sessions.py`. `TAO_USE_AGENT_SDK=1` is now the only supported mode — setting it to 0 causes an `ImportError` at startup (deliberate: misconfiguration must be loud).

| Layer | SDK Path | File |
|-------|----------|------|
| Generator | `_run_claude_via_sdk()` | `sessions.py` |
| Evaluator | `_run_single_eval()` → SDK | `sessions.py` |
| Board Meeting | `_run_prompt_via_sdk()` | `agents/board_meeting.py` |
| Orchestrator | Agent SDK fan-out | `orchestrator.py` |
| Pipeline | Agent SDK per phase | `pipeline.py` |

**Metrics:** Every SDK invocation emits a row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. Analyse with `python scripts/sdk_metrics.py`.

**API fallback (Risk Register R-02):** `TAO_USE_FALLBACK=1` activates the direct Anthropic Python SDK path (no claude CLI). Test quarterly via `python scripts/fallback_dryrun.py`. See `DEPLOYMENT.md → Contingency: API Fallback`.

SDK reference: `app/server/agents/board_meeting.py::_run_prompt_via_sdk()`. Version policy: `.harness/agents/sdk-version-policy.md`.

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` env var in Claude Desktop config

## Strategic Direction

**Sprint 8 (current):** SDK-only execution confirmed (RA-576). Post-deploy smoke test wired into CI via `scripts/smoke_test.py --target=prod` (RA-583). Quality gate results persisted to Supabase `gate_checks` table (RA-651). Critical alert escalation chain complete: Telegram → 30-min watchdog → escalation page (RA-633). ZTE target: 75/75.

**Autonomy:** `app/server/autonomy.py` polls Linear every 5 min for Urgent/High unstarted issues and auto-creates sessions. Kill switch: `TAO_AUTONOMY_ENABLED=0` in Railway env.

**Observability:** `supabase_log.py` is the single write path for all server-side Supabase events. Tables: `gate_checks`, `alert_escalations`, `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`. All writes are fire-and-forget — observability failures must never block the build pipeline.

**CI pipeline (RA-583):** Three jobs: `python` (pytest + ruff), `frontend` (tsc + eslint + build), `smoke-prod` (post-deploy gate against Railway, main-branch pushes only). `smoke-prod` requires `TAO_PROD_PASSWORD` GitHub secret.

## Persistence Guidelines

- `_sessions` is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- Use write-to-.tmp-then-`os.replace()` for JSON file writes. `os.replace()` is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written file.

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
