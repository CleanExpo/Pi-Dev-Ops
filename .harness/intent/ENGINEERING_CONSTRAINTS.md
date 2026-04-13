# Pi-Dev-Ops — Engineering Constraints

## Do Not Break

These invariants must hold after every build:

- `GET /health` returns HTTP 200
- `GET /api/sessions` returns HTTP 200 (with valid auth cookie)
- `python -m ruff check app/server/` passes with zero errors
- `npx tsc --noEmit` in `dashboard/` passes with zero errors
- `python scripts/smoke_test.py --url http://127.0.0.1:7777` passes
- All Supabase writes in `supabase_log.py` remain fire-and-forget (never raise)
- `config.py` loads successfully even when all optional env vars are unset
- No secrets or credentials committed to git (verified by scanner)

## Architecture Boundaries

- Backend is FastAPI (Python 3.11+) — do not introduce async frameworks other than asyncio
- Frontend is Next.js 16 / React 19 — do not downgrade Node dependencies
- SDK-only mode: `TAO_USE_AGENT_SDK=1` is required; subprocess fallback paths have been removed (RA-576)
- All Telegram alerts must be fire-and-forget with `timeout=8` — never block the build pipeline
- Linear writes use the MCP or direct GraphQL — do not introduce a supabase-py or linear-py dependency

## File Count Budget

Default session scope: max 8 files modified per autonomous build.
Security patches: max 3 files (targeted fixes only).
Refactors: max 12 files (requires explicit scope declaration).
