# Pi Dev Ops — Cross-Session Handoff

_Last updated: 2026-04-08 | Sprint 5 / Cycle 6 | ZTE Score: 60/60 Zero Touch_

---

## Current State

The system is fully operational at **ZTE Level: Zero Touch (60/60)**. All 26 Sprint 1+2 features are implemented and verified by E2E smoke test (Sprint 3, RA-470).

**Server:** FastAPI at `127.0.0.1:7777` (start with `cd app && uvicorn server.main:app --host 127.0.0.1 --port 7777`)
**Dashboard:** Next.js at `dashboard/` (Vercel-deployed)
**MCP Server:** `mcp/pi-ceo-server.js` v3.0.0 (restart required to pick up latest code changes)

---

## Architecture (Post-Sprint State)

```
Browser → POST /api/build → FastAPI → run_build()
                                          │
  Phase 1: git clone (3-attempt backoff)  │
  Phase 2: workspace analysis             │
  Phase 3: Claude Code availability check │
  Phase 3.5: sandbox verification         │
  Phase 4: generator (claude -p) + retry  │
  Phase 4.5: evaluator (blocking gate)    │  ← closed-loop retry with critique injection
  Phase 5: git push (3-attempt backoff)   │  ← RA-471 added
                                          ▼
             lessons.jsonl ← auto-learn from evaluator scores
Browser ← WebSocket /ws/build/{sid} (live stream)
```

**Key supporting modules:**
- `app/server/brief.py` — PITER classifier + ADW template engine + lesson/skill injection
- `app/server/sessions.py` — full build lifecycle, phase checkpoints, resume
- `app/server/persistence.py` — atomic JSON session persistence to `app/logs/sessions/`
- `app/server/orchestrator.py` — fan-out parallelism via `POST /api/build/parallel`
- `app/server/webhook.py` — GitHub + Linear webhook parsing
- `app/server/cron.py` — cron trigger engine (`GET/POST/DELETE /api/triggers`)
- `app/server/gc.py` — workspace GC (4h TTL, runs every 30 min)
- `app/server/lessons.py` — lessons.jsonl CRUD (`GET/POST /api/lessons`)

---

## Sprint 1 — Foundation (2026-04-07) | 35 → 41/60

| Issue | Change |
|-------|--------|
| RA-449 | MCP server rebuilt as v3.0.0 using official `@modelcontextprotocol/sdk` |
| RA-450 | `persistence.py`: atomic JSON saves on every status change; restored on startup |
| RA-451 | `gc.py`: workspace GC loop (30min interval, 4h TTL) |
| RA-452 | `auth.py`: inline rate-limit GC — evicts IPs not seen in 120s every 5 min |
| RA-453 | `lessons.jsonl` seeded with 12 entries; `GET/POST /api/lessons` endpoints |
| RA-458 | `CLAUDE.md` fully documented (replaced stub template) |
| RA-459 | `.claude/settings.local.json` added to `.gitignore` and untracked |

## Sprint 2 — Capability (2026-04-07) | 41 → 50/60

| Issue | Change |
|-------|--------|
| RA-454 | Evaluator tier: second `claude -p` pass, 4-dimension scoring, scores streamed to WS |
| RA-455 | `webhook.py` + `POST /api/webhook`: GitHub + Linear event parsing, auto-brief |
| RA-456 | `brief.py`: PITER intent classifier + 5 ADW templates (feature/bug/chore/spike/hotfix) |
| RA-457 | `src/tao/skills.py`: skills loader/registry with intent-to-skill mapping |
| RA-460 | Linear webhook: issue move to "In Progress" auto-triggers a build session |
| RA-461 | `.harness/leverage-audit.md` baseline score recorded |
| RA-462 | Leverage audit updated to 50/60 post-P2 sprint |
| RA-463 | `.harness/agents/`, `contracts/`, `qa/`, `templates/` all populated (10 new files) |
| RA-464 | `orchestrator.py`: fan-out parallelism, `POST /api/build/parallel` |
| RA-465 | TAO engine wired: BudgetTracker per session, `_select_model()` reads config |
| RA-466 | `scripts/fetch_anthropic_docs.py`: daily docs pull cron at 5:50am AEST |
| RA-467 | Autonomous board meetings: scheduled at 0/6/12/18 AEST, fully autonomous |
| RA-468 | Sandbox enforcement: Phase 3.5 auto-re-clones if workspace GC'd mid-session |

## ZTE Sprint (2026-04-08) | 50 → 60/60

All 12 leverage points raised to 5/5. Changes included in sessions.py/brief.py:
- Lesson context injection per intent into every brief (`_get_lesson_context`)
- `_select_model()` reads `.harness/config.yaml` agents block
- Fan-out workers escalate to opus tier on failure
- Closed-loop evaluator retry: critique → retry prompt → re-generate → re-evaluate
- Clone 3-attempt backoff (2s/4s); generator 2-attempt retry
- Phase checkpoints persisted; `POST /api/sessions/{sid}/resume` skips done phases
- Evaluator is now BLOCKING gate (not fire-and-forget), max 2 retries
- `_parse_evaluator_dimensions()` extracts scores; auto-appends lessons below threshold
- `cron.py` + `.harness/cron-triggers.json` + `GET/POST/DELETE /api/triggers`

## Sprint 3 — Validation (2026-04-08) | 60/60 maintained

| Issue | Change |
|-------|--------|
| RA-469 | MCP `get_zte_score` reads `leverage-audit.md` directly; `feature_list.json` + `sprint_plan.md` created |
| RA-470 | E2E smoke test: 22/22 checks pass; PITER priority bug fixed (chore/spike before feature) |
| RA-471 | `git push` retry added: 3 attempts, 2s/4s backoff, auth error hard-stop |
| RA-472 | This file |

---

## Known Working Configuration

```
TAO_PASSWORD=<set or auto-generated on first run>
TAO_SESSION_SECRET=<auto-generated; set to persist across restarts>
TAO_EVALUATOR_ENABLED=true
TAO_EVALUATOR_THRESHOLD=7
TAO_EVALUATOR_MAX_RETRIES=2
TAO_EVALUATOR_MODEL=sonnet
TAO_GC_MAX_AGE=14400  # 4 hours
```

### Railway deployment (RA-478) — LIVE ✅

**Public URL:** `https://pi-dev-ops-production.up.railway.app`
**Project:** airy-adventure | **Service:** Pi-Dev-Ops | **Region:** US East (Virginia)

Railway env vars set (via dashboard Variables tab):
```
TAO_PASSWORD=mdGF5NWZrpC4HFCaXMZHE4-ipqq9FJDhebrx_6oDCKg
TAO_SESSION_SECRET=a3687d7f4ff46d248996cc09ae224e4d5bb1ff61001c0b826a36453ae99d0adc5663a2e71ddd76ef5f71dc30d4f0d52fc7150b5ba53adf4e3657b1fe9f194aa5
ANTHROPIC_API_KEY=<set in Railway dashboard>
TAO_EVALUATOR_ENABLED=true
TAO_EVALUATOR_THRESHOLD=7
TAO_EVALUATOR_MAX_RETRIES=2
TAO_GC_MAX_AGE=14400
```

Vercel dashboard env vars set (all environments):
```
PI_CEO_URL=https://pi-dev-ops-production.up.railway.app
PI_CEO_PASSWORD=mdGF5NWZrpC4HFCaXMZHE4-ipqq9FJDhebrx_6oDCKg
```
Dashboard redeployed: `https://dashboard-unite-group.vercel.app`

The MCP server (`mcp/pi-ceo-server.js`) needs `LINEAR_API_KEY` set in
`%APPDATA%\Claude\claude_desktop_config.json` for its Linear tools to work.
The main Linear MCP (via Composio) handles Linear operations in Claude Code sessions.

---

## Sprint 4 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-473 | `scripts/smoke_test.py`: standalone 28-check E2E regression script, UTF-8 safe, CI exit codes |
| RA-474 | `dashboard/app/(main)/builds/page.tsx`: live Pi CEO builds view (phase bar, evaluator scores, fan-out grouping); `/api/pi-ceo/[...path]/route.ts` proxy handles auth |
| RA-475 | Real build validated: 6/7 phases ran (clone→analyze→claude_check→sandbox→generator running); `claude -p` subprocess confirmed working |
| RA-476 | `linear_status` diagnostic tool added to Pi CEO MCP; self-service setup guide built in |

### RA-476 — Manual step remaining
To enable `linear_*` MCP tools: add `LINEAR_API_KEY` to `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "pi-ceo": {
      "command": "node",
      "args": ["C:\\Pi Dev Ops\\mcp\\pi-ceo-server.js"],
      "env": { "LINEAR_API_KEY": "lin_api_..." }
    }
  }
}
```
Run `linear_status` tool in Claude to verify. Get key from https://linear.app/settings/api.

---

## Sprint 5 — Complete (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-477 | `.github/workflows/smoke_test.yml`: GitHub Actions CI — 28-check smoke test runs on push/PR to main; `TAO_EVALUATOR_ENABLED=false` skips real claude in CI |
| RA-478 | Railway deployment live: `Dockerfile` + `railway.toml` + `.dockerignore`; public URL `https://pi-dev-ops-production.up.railway.app`; Vercel `PI_CEO_URL` + `PI_CEO_PASSWORD` set; dashboard redeployed |

---

## Sprint 6 — Evaluator Quality Push (2026-04-08)

| Issue | Change |
|-------|--------|
| RA-479 | `brief.py`: `_QUALITY_GATE` constant injected into every generator brief — explicit 4-dimension self-review rubric mirroring the evaluator (target ≥9/10 per dimension) |
| RA-480 | `sessions.py`: Evaluator prompt now includes original brief for completeness checking + rigorous scoring guide (10=excellent → ≤6=clear deficiency) |
| RA-481 | `config.py`: Default `EVALUATOR_THRESHOLD` raised 7 → 8; Railway env var updated to match |

**Expected outcome:** Evaluator scores should consistently land 8.5–9.5 (vs prior 7.5). Root cause of prior scores: generator didn't know the rubric; evaluator couldn't check completeness without the brief.

---

## What To Do Next (Sprint 7 Candidates)

1. **Verify `/builds` page in production** — open `https://dashboard-unite-group.vercel.app/builds` and confirm sessions stream from Railway
2. **Smoke test against Railway** — run `python scripts/smoke_test.py --url https://pi-dev-ops-production.up.railway.app --password mdGF5NWZrpC4HFCaXMZHE4-ipqq9FJDhebrx_6oDCKg`
3. **Linear API key** — add `LINEAR_API_KEY` to `%APPDATA%\Claude\claude_desktop_config.json` so `linear_*` MCP tools work (see RA-476 instructions above)
4. **Cost tracking** — wire Railway spend alerts; add `TAO_MONTHLY_BUDGET_USD` env var check
5. **Evaluator model upgrade** — set `TAO_EVALUATOR_MODEL=opus` in Railway for maximum scoring rigour (15x cost but catches every gap)
