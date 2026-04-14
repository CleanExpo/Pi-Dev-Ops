# Pi-Dev-Ops — Claude Code Guidance

## Project Context

Pi-Dev-Ops converts a GitHub repo URL + plain-English brief into an autonomous Claude Code execution session. Generator and evaluator run via `claude_agent_sdk`. `TAO_USE_AGENT_SDK=1` is mandatory — setting 0 raises `ImportError` at startup.

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js 16.2.2, React 19, Tailwind | `dashboard/` |
| Backend | FastAPI, Python 3.11+ | `app/server/` |
| Routes | 8 focused route modules | `app/server/routes/` |
| MCP Server | Node.js, @modelcontextprotocol/sdk | `mcp/` |
| TAO Engine | Python (skills, tiers, budget) | `src/tao/` |
| Harness State | YAML/JSON/Markdown | `.harness/` |
| Skills | 33 SKILL.md files | `skills/` |
| Database | Supabase (PostgreSQL) | `supabase/` |
| Deploy (FE) | Vercel | `dashboard/vercel.json` |
| Deploy (BE) | Railway | `railway.toml`, `Dockerfile` |

## Backend Module Map (`app/server/`)

| File | Lines | Concern |
|------|-------|---------|
| `main.py` | ~25 | Thin assembler — imports `app`, registers all routers |
| `app_factory.py` | ~130 | `app` object, CORS/security middleware, `_resilient`, startup/shutdown hooks |
| `models.py` | ~126 | All Pydantic request models |
| `routes/auth.py` | ~48 | `POST /api/login`, `POST /api/logout`, `GET /api/me` |
| `routes/sessions.py` | ~122 | `/api/build`, `/api/build/parallel`, session list/kill/logs/resume |
| `routes/webhooks.py` | ~214 | `POST /api/webhook` (GitHub+Linear), morning-intel, Telegram |
| `routes/triggers.py` | ~32 | Trigger CRUD (`GET/POST/DELETE /api/triggers`) |
| `routes/scan_monitor.py` | ~111 | `/api/scan`, `/api/projects/health`, `/api/monitor` |
| `routes/pipeline.py` | ~89 | `/api/spec`, `/api/plan`, `/api/test`, `/api/ship`, `/api/pipeline/{id}` |
| `routes/utils.py` | ~68 | `/api/gc`, `/api/lessons`, `/api/autonomy/status`, WebSocket `/ws/build/{sid}` |
| `routes/health.py` | ~125 | `/health`, `/api/health/vercel`, Claude CLI poll, static mount |

Public contract: `app.server.main:app` is the FastAPI instance — Dockerfile and Railway both reference it. `main.py` re-exports `app` from `app_factory`. Never break this import.

## Development Setup

```bash
cd app && source .env.local && uvicorn server.main:app --host 127.0.0.1 --port 7777
cd dashboard && npm run dev
node mcp/pi-ceo-server.js
```

## Running Tests

```bash
python -m pytest tests/ -x -q                # Gate: import check must pass first
python -c "from app.server.main import app"   # Must print FastAPI
cd dashboard && npx tsc --noEmit
cd dashboard && npm run build
python scripts/smoke_test.py --url http://127.0.0.1:7777 --password $TAO_PASSWORD
```

Expected: 3 pre-existing failures in `test_sdk_phase2.py` (claude_agent_sdk not installed locally). All other tests pass.

## Code Conventions

- **Python:** snake_case, type hints on all functions, `logging.getLogger()`, structured JSON via `_JsonFormatter`
- **TypeScript:** strict mode, no `any`, named exports, interfaces over types
- **Commits:** Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `ci:`, `chore:`)
- **Branches:** `feature/{ticket-id}-{short-desc}` or `fix/{ticket-id}-{short-desc}`
- **Functions:** under 40 lines. Files under 300 lines. Extract when exceeding.
- **Security:** bcrypt passwords, parameterised queries, CSP headers, no secrets in code

## Key Patterns

- **Password auth:** bcrypt with transparent SHA-256 migration (`auth.py`). `TAO_PASSWORD` set → hash regenerated on every startup so Railway env changes take effect immediately.
- **Session secret:** Persisted to `app/data/.session-secret`.
- **SSE streaming:** `dashboard/hooks/useSSE.ts` with exponential backoff reconnection.
- **Phase pipeline:** 5–6 phases in `sessions.py`, parsed by `dashboard/lib/phases.ts`. Phase 5: git push to `pidev/auto-{sid}` feature branch with GITHUB_TOKEN auth (3-attempt backoff; auth failure → hard stop).
- **Settings:** Supabase-backed via `dashboard/lib/supabase/settings.ts`.
- **MCP tools:** `mcp/pi-ceo-server.js` — 21 tools for harness reads + Linear operations.
- **Path traversal:** `_safe_sid()` strips non-alphanumeric from session IDs before file path use.
- **Webhook HMAC:** `hmac.compare_digest()` for GitHub (`x-hub-signature-256`) and Linear (`Linear-Signature`).
- **Analysis mode:** `ANALYSIS_MODE=api` in Vercel forces Max plan subscription token (`sk-ant-oat01-*` from `claude setup-token`).
- **Push auth:** `_phase_push()` injects GITHUB_TOKEN via x-access-token into git remote URL and pushes to `pidev/auto-{sid[:8]}` feature branch. Requires GITHUB_TOKEN + GITHUB_REPO env vars in Railway.
- **Route isolation:** Each `routes/*.py` module owns one concern. `_IS_CLOUD` is re-derived from `os.environ` in `routes/auth.py` (not imported from `app_factory`) to avoid coupling. `_find_active_session_for_repo()` lives in `routes/sessions.py` and is imported into `routes/webhooks.py` one-way.

## SDK Architecture

`TAO_USE_AGENT_SDK=1` is the only supported mode.

| Layer | SDK Path | File |
|-------|----------|------|
| Generator | `_run_claude_via_sdk()` | `sessions.py` |
| Evaluator | `_run_single_eval()` → SDK | `sessions.py` |
| Board Meeting | `_run_prompt_via_sdk()` | `agents/board_meeting.py` |
| Orchestrator | Agent SDK fan-out | `orchestrator.py` |
| Pipeline | Agent SDK per phase | `pipeline.py` |

Every SDK invocation emits a row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. Analyse with `python scripts/sdk_metrics.py`.

**Fallback (Risk Register R-02):** `TAO_USE_FALLBACK=1` activates direct Anthropic Python SDK. Test quarterly via `scripts/fallback_dryrun.py`.

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` in Claude Desktop config and Railway

## Autonomy and Health

- `autonomy.py` polls Linear every 5 min for **Urgent/High Todo** issues and auto-creates sessions. In Progress issues are invisible — reset to Todo to restart a stalled session.
- Kill switch: `TAO_AUTONOMY_ENABLED=0` in Railway.
- **Always-on requirement:** if any step depends on a Mac staying awake or a local process running, the system is not autonomous. Always-on path: Railway + Vercel + GitHub Actions only.
- **`/health` must surface real state:** (1) boolean confirming the loop will fire on next tick, (2) timestamp of last successful tick. Without both, silent-success theatre.
- **Silent failure pattern:** `autonomy.py` skips every poll cycle when `LINEAR_API_KEY` is missing but `/health` still returns 200. Symptom: `sessions.total` stays at 0. Always surface `linear_api_key: bool`.
- **Do-while pattern:** `while True: await asyncio.sleep(interval)` delays first execution by a full interval after Railway restart. Use a 10s `startup_delay` instead. Log every skipped poll.

## Scheduled Tasks

- Scheduled-tasks MCP runs inside the desktop Claude session and does **not** inherit `.claude/settings.json`. Keep every task to a single shell command calling a standalone Python helper.
- Each task runs in a fresh Cowork sandbox at `/sessions/<random-id>/mnt/<folder>`. Discover the repo dynamically: `find /sessions -type d -name <repo>`.
- Never escalate CRITICAL from a Cowork sandbox. `ModuleNotFoundError` inside a watchdog is a sandbox environment issue. Real test truth comes from GitHub Actions.

## Persistence

- `_sessions` is in-memory — server restart loses all running sessions. Persist status to disk atomically after every state change.
- Use write-to-`.tmp`-then-`os.replace()` for JSON writes. Crash-safe on NTFS and POSIX.

## Observability

`supabase_log.py` is the single write path for all server-side Supabase events. Tables: `gate_checks`, `alert_escalations`, `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`. All writes are fire-and-forget — observability failures must never block the build pipeline.

## CI Pipeline

Three jobs: `python` (pytest + ruff), `frontend` (tsc + eslint + build), `smoke-prod` (post-deploy gate against Railway, main-branch only). `smoke-prod` requires `TAO_PROD_PASSWORD` GitHub secret.

## Current Sprint (Sprint 12 — Active 2026-04-15)

**ZTE v2: 85/100 → target 90**

Board activation vote carried unanimously on 15 Apr 2026. Swarm flipped to active mode (`TAO_SWARM_SHADOW=0`). Rate limit: 3 autonomous PRs/day (lifts after 20 consecutive green supervised merges). NotebookLM 5th criterion added: top-3 risks per entity from Linear + Pi-SEO. Next board: 6 May 2026 Enhancement Review (RA-949).

**Open PRs awaiting human merge:** #11 (RA-948 autonomous PR), #12 (swarm active mode + bots), #13 (dashboard redesign), #14 (RA-837/847 CI webhook + docs synthesis).

**Blocker (OPS veto):** RA-950 — carsi `ADMIN_PASSWORD` must be set in DigitalOcean before swarm fires on carsi scope. Other projects (Pi-Dev-Ops, RestoreAssist) unblocked.

**Developer actions required:**
- Merge PRs #11–14
- Set `ADMIN_PASSWORD` in DigitalOcean for carsi (RA-950)
- Set `TAO_USE_AGENT_SDK_CANARY_RATE=0.5` in Railway (RA-838 Phase B)
- Set `TAO_PASSWORD` in `.env.local` for Builder bot to fire `/api/build`
- Add `workflow_run` event to GitHub webhooks on all repos (RA-847)
- Purchase UPS (AUD ≤$500, board approved)

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
