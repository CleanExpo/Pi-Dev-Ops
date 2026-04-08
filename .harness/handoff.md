# Pi Dev Ops — Cross-Session Handoff

_Last updated: 2026-04-08 | Sprint 3 / Cycle 4 | ZTE Score: 60/60 Zero Touch_

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

The MCP server (`mcp/pi-ceo-server.js`) needs `LINEAR_API_KEY` set in
`%APPDATA%\Claude\claude_desktop_config.json` for its Linear tools to work.
The main Linear MCP (via Composio) handles Linear operations in Claude Code sessions.

---

## What To Do Next (Sprint 4 Candidates)

1. **Smoke test with real build** — trigger a build against Pi-Dev-Ops itself via the web UI to confirm the full Claude Code subprocess execution path
2. **Vercel dashboard sync** — the Next.js dashboard at `dashboard/` may need updating to surface fan-out sessions and evaluator scores
3. **Linear API key for Pi CEO MCP** — add `LINEAR_API_KEY` to `claude_desktop_config.json` so `pi-ceo-server.js` tools can update issues autonomously without falling back to the Composio MCP
4. **E2E regression script** — convert the Sprint 3 smoke test into a standalone `scripts/smoke_test.py` that can be run as a pre-deploy gate
