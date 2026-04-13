# Pi-Dev-Ops — Claude Code Guidance

## Project Context

Pi-Dev-Ops is a Zero Touch Engineering (ZTE) platform that converts a GitHub repo URL and a plain-English brief into an autonomous Claude Code execution session. The generator and evaluator run via the `claude_agent_sdk` Python SDK. `TAO_USE_AGENT_SDK=1` is mandatory — setting it to 0 raises `ImportError` at startup (deliberate: misconfiguration must be loud).

**ZTE Score:** 73/75 (Sprint 8) | ZTE v2: 81/100 (Sprint 9) — see `.harness/leverage-audit.md`

## Architecture

| Layer | Tech | Location |
|-------|------|----------|
| Frontend | Next.js 16.2.2, React 19, Tailwind | `dashboard/` |
| Backend | FastAPI, Python 3.11+ | `app/server/` |
| MCP Server | Node.js, @modelcontextprotocol/sdk | `mcp/` |
| TAO Engine | Python (skills, tiers, budget) | `src/tao/` |
| Harness State | YAML/JSON/Markdown | `.harness/` |
| Skills | 33 SKILL.md files | `skills/` |
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

- **Password auth:** bcrypt with transparent SHA-256 migration (`app/server/auth.py`). If `TAO_PASSWORD` is set in env, the hash is always regenerated on startup so Railway env var changes take effect immediately.
- **Session secret:** Persisted to `app/data/.session-secret` (survives restarts)
- **SSE streaming:** `dashboard/hooks/useSSE.ts` with exponential backoff reconnection
- **Phase pipeline:** 5-6 phases in `app/server/sessions.py`, parsed by `dashboard/lib/phases.ts`
- **Settings:** Supabase-backed via `dashboard/lib/supabase/settings.ts`
- **MCP tools:** `mcp/pi-ceo-server.js` — 21 tools for harness reads + Linear operations
- **Path traversal:** `_safe_sid()` strips non-alphanumeric from session IDs before file path use
- **Webhook HMAC:** `hmac.compare_digest()` (timing-safe) for both GitHub (`x-hub-signature-256`) and Linear (`Linear-Signature`)
- **Analysis mode:** `dashboard/lib/claude.ts::getAnalysisMode()` — `ANALYSIS_MODE` env var takes priority over `ANTHROPIC_API_KEY`. Set `ANALYSIS_MODE=api` in Vercel to use Max plan subscription token (`sk-ant-oat01-*` from `claude setup-token`).

## SDK Architecture (Sprint 8 Complete — RA-576)

The build pipeline runs **SDK-only**. `TAO_USE_AGENT_SDK=1` is the only supported mode.

| Layer | SDK Path | File |
|-------|----------|------|
| Generator | `_run_claude_via_sdk()` | `sessions.py` |
| Evaluator | `_run_single_eval()` → SDK | `sessions.py` |
| Board Meeting | `_run_prompt_via_sdk()` | `agents/board_meeting.py` |
| Orchestrator | Agent SDK fan-out | `orchestrator.py` |
| Pipeline | Agent SDK per phase | `pipeline.py` |

**Metrics:** Every SDK invocation emits a row to `.harness/agent-sdk-metrics/YYYY-MM-DD.jsonl`. Analyse with `python scripts/sdk_metrics.py`.

**API fallback (Risk Register R-02):** `TAO_USE_FALLBACK=1` activates the direct Anthropic Python SDK path. Test quarterly via `python scripts/fallback_dryrun.py`.

SDK reference: `app/server/agents/board_meeting.py::_run_prompt_via_sdk()`. Version policy: `.harness/agents/sdk-version-policy.md`.

## Linear Integration

- **Team:** RestoreAssist (`a8a52f07-63cf-4ece-9ad2-3e3bd3c15673`)
- **Project:** Pi - Dev -Ops (`f45212be-3259-4bfb-89b1-54c122c939a7`)
- **Ticket format:** RA-xxx
- **MCP:** `LINEAR_API_KEY` env var in Claude Desktop config and Railway

## Autonomy and Health

- `app/server/autonomy.py` polls Linear every 5 min for **Urgent/High unstarted (Todo)** issues and auto-creates sessions. In Progress issues are invisible to the poller — reset to Todo if a stalled session needs restart.
- Kill switch: `TAO_AUTONOMY_ENABLED=0` in Railway env.
- `/health` must report the state of the work, not just process uptime. Every long-running loop needs: (1) a boolean confirming it is armed and will fire on next tick, (2) a timestamp/counter of the last successful tick. Without both, you get silent-success theatre.
- Silent failure pattern: `autonomy.py` skips every poll cycle when `LINEAR_API_KEY` is missing, but `/health` still returns 200. Symptom: `sessions.total` stays at 0. Always surface `linear_api_key: bool` in the health response.
- Do-while pattern for pollers: `while True: await asyncio.sleep(interval)` delays the first execution by the full interval after a Railway restart. Use a short `startup_delay` (10s) instead. Log every skipped poll, not just the first.

## Autonomy Is a Topology Property

"Autonomous" means every component runs on an always-on host. If any step depends on a Mac staying awake, Cowork staying open, or a local process running, the system is a cron job in an editor — not an autonomous agent. Always-on path: Railway (backend) + Vercel (frontend) + GitHub Actions (CI). Never schedule work in Cowork scheduled tasks that must survive overnight.

## Scheduled Tasks

- The scheduled-tasks MCP runs inside the desktop Claude session and does **not** inherit the repo `.claude/settings.json` allowlist. Keep every scheduled task prompt to a single shell command calling a standalone Python helper — this minimises tool-approval surface to Bash alone.
- Each task runs inside a fresh Cowork sandbox at `/sessions/<random-id>/mnt/<folder>`. The session ID changes every run — never hardcode the Mac path. Discover the repo dynamically: `find /sessions -type d -name <repo>` then `cd` into it.
- Never escalate CRITICAL from a Cowork sandbox. The sandbox package set is not guaranteed to match production. `ModuleNotFoundError` inside a watchdog task is a sandbox environment issue, not a real test failure. Real test-green truth comes from GitHub Actions.

## Persistence Guidelines

- `_sessions` is an in-memory dict — any server restart loses all running sessions. Always persist status to disk atomically after every state change.
- Use write-to-.tmp-then-`os.replace()` for JSON file writes. `os.replace()` is atomic on NTFS and POSIX — a crash mid-write leaves the old file intact, not a corrupt half-written file.

## Strategic Direction

**Sprint 9 (complete):** Karpathy enhancement layer — confidence-weighted evaluator, AUTONOMY_BUDGET single-knob, Session Scope Contract, plan variation discovery, progressive brief complexity, layered abstraction, dependency alerting, Vercel drift monitoring, skills manifest. ZTE v2: 81/100.

**Sprint 10 (current):** MARATHON-4 (RA-588) — first 6-hour autonomous self-maintenance run. SDK Canary Phase A running at 10% rate (`AGENT_SDK_CANARY_RATE=0.1`), 24h observation window. Quality gate results persisted to Supabase `gate_checks` table. ZTE target: 90/100.

**Observability:** `supabase_log.py` is the single write path for all server-side Supabase events. Tables: `gate_checks`, `alert_escalations`, `heartbeat_log`, `triage_log`, `workflow_runs`, `claude_api_costs`. All writes are fire-and-forget — observability failures must never block the build pipeline.

**CI pipeline (RA-583):** Three jobs: `python` (pytest + ruff), `frontend` (tsc + eslint + build), `smoke-prod` (post-deploy gate against Railway, main-branch pushes only). `smoke-prod` requires `TAO_PROD_PASSWORD` GitHub secret.

## Content Rules

- No first-person business language (We/Our/I/Us/My)
- No AI filler words (delve, tapestry, landscape, leverage, robust, seamless, elevate)
- Every paragraph answers a specific question
